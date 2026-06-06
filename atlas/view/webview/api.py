import json
import logging
import os
import re
import shlex
import shutil
import threading
import time
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import List, Optional, Tuple
from urllib.parse import urlsplit


def _json_safe(obj):
    """Make a value JSON-serializable for the pywebview bridge. get_info() payloads can
    carry datetimes (e.g. the Arch gem's first_submitted/last_modified, Flathub release
    dates); pywebview's json.dumps can't encode those, so convert them to ISO strings."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(sep=' ', timespec='minutes') if isinstance(obj, datetime) else obj.isoformat()
    return obj

from atlas.api.abstract.controller import SoftwareAction
from atlas.commons.system import (validate_root_password, run_cmd, new_subprocess,
                                  new_root_subprocess, get_dir_size)
from atlas.commons.view_utils import get_human_size_str
from atlas.view.core.controller import GenericSoftwareManager
from atlas.view.webview.watcher import WebviewWatcher
from atlas.view.webview.activity_log import record_activity, get_activity_log
from atlas.view.webview.export import write_manifest, read_manifest

PACMAN_LOG = '/var/log/pacman.log'
# `[2026-06-05T10:51:12-0400] [ALPM] installed visual-studio-code-bin (1.123.0-4)`
# upgrades carry `(old -> new)`. pacman.log is world-readable, so no root is needed to read it.
_RE_PACMAN_LOG = re.compile(
    r'^\[(?P<ts>[^\]]+)\] \[ALPM\] '
    r'(?P<action>installed|upgraded|downgraded|removed|reinstalled) '
    r'(?P<name>\S+) \((?P<version>[^)]*)\)')


def parse_pacman_log(text: str, pkg_name: str, limit: int = 20) -> List[dict]:
    """Pure: extract a package's transaction lines from pacman.log content, newest first.

    Returns ``[{timestamp, action, version}]`` (version is the raw token, e.g. ``1.0-1`` or
    ``1.0-1 -> 1.1-1`` for an upgrade). Only exact name matches are kept. Best-effort and
    side-effect-free so it's trivially testable; the caller handles file/permission errors."""
    entries = []
    for line in (text or '').splitlines():
        m = _RE_PACMAN_LOG.match(line)
        if m and m.group('name') == pkg_name:
            entries.append({'timestamp': m.group('ts'),
                            'action': m.group('action'),
                            'version': m.group('version')})
    entries.reverse()  # pacman.log is chronological; the page wants newest first
    return entries[:limit]


class AtlasApi:

    PACMAN_CACHE_DIR = '/var/cache/pacman/pkg'
    MIRRORLIST_PATH = '/etc/pacman.d/mirrorlist'
    ARCH_NEWS_URL = 'https://archlinux.org/feeds/news/'

    # Browse-by-category buckets for the Discovery view. The shipped categories.txt uses many
    # inconsistent raw labels (Browser/browser, Xfce/XFCE, Python, Emulator, Manjaro, …); we
    # merge the synonyms into a small curated, ordered set of top-level buckets. Each raw label
    # maps into at most the buckets that list it. See docs/plans/2026-06-02-browse-by-category.md.
    # Each bucket: (key, label, icon, arch_raw_labels, flathub_category). The 4th element is the
    # set of raw categories.txt labels that fall in the bucket (Arch repo index); the 5th is the
    # matching Flathub top-level category (None if the bucket has no Flatpak equivalent). AUR has
    # no category source — the RPC carries no categories — so Browse stays Arch-repo + Flatpak.
    # (key, label, icon, raw-category-tuple, flathub-category, short-description)
    CATEGORY_BUCKETS = (
        ('games',       'Games',         '🎮', ('Game', 'Emulator'), 'Game',
         'Games, emulators & launchers'),
        ('internet',    'Internet',      '🌐', ('Network', 'Browser', 'browser', 'Torrent', 'P2P', 'IRC'), 'Network',
         'Browsers, chat, torrents & network tools'),
        ('multimedia',  'Audio & Video', '🎵', ('Audio', 'Video', 'AudioVideo'), 'AudioVideo',
         'Players, editors & audio tools'),
        ('graphics',    'Graphics',      '🎨', ('Graphics', 'GTK'), 'Graphics',
         'Image editors, viewers & design'),
        # 💻 (color-default) replaces ⌨, and the gear carries an explicit emoji variation selector
        # (⚙️ = U+2699 U+FE0F) — without it ⌨/⚙ are text-presentation glyphs that render as faint
        # monochrome outlines on the dark theme (the other six icons are color-emoji by default).
        ('development', 'Development',   '💻', ('Development', 'Python', 'Javascript'), 'Development',
         'Editors, languages & dev tools'),
        ('office',      'Office',         '📄', ('Office',), 'Office',
         'Documents, spreadsheets & productivity'),
        ('utilities',   'Utilities',     '🧰', ('Utility',), 'Utility',
         'Handy small tools & accessories'),
        ('system',      'System',        '⚙️',  ('System', 'Settings', 'Security', 'Kernel',
                                                'Printing', 'Bluetooth', 'Qt', 'KDE', 'Gnome',
                                                'Xfce', 'XFCE', 'Manjaro'), 'System',
         'System, settings & desktop integration'),
    )

    # AUR discovery buckets — the feasible alternative to (impossible) AUR categories. The data is
    # precomputed in the atlas-files repo (a daily GH Action turns the AUR meta dump into a small
    # JSON); Atlas just fetches it. Each tuple is (json-key, label, icon). See
    # docs/plans/2026-06-05-aur-discovery-buckets.md.
    AUR_DISCOVERY_URL = 'https://raw.githubusercontent.com/Vatteck/atlas-files/main/arch/aur_discovery.json'
    AUR_BUCKETS = (
        ('popular',          'Popular',          '🔥'),
        ('recently_updated', 'Recently updated', '🆕'),
        ('vcs',              'VCS (-git)',        '🔧'),
        ('bin',              'Binary (-bin)',     '📦'),
    )
    _AUR_DISCOVERY_TTL = 3600  # seconds; the source refreshes daily, so an hour-stale cache is fine

    def __init__(self, manager: GenericSoftwareManager, logger: logging.Logger):
        self.manager = manager
        self.logger = logger
        self.pkg_registry = {}  # opaque_id -> SoftwarePackage
        self._registry_lock = threading.Lock()
        self.window = None

        # AUR discovery buckets: cache the fetched JSON so the landing + a bucket open don't double-
        # fetch (and survive a brief outage). (data, fetched_at) — see _fetch_aur_discovery().
        self._aur_discovery_cache = None
        self._aur_discovery_cache_ts = 0.0

        # Root-password broker (see docs/plans/2026-05-30-root-password-flow-design.md).
        # A validated password is cached for the session so we don't re-prompt for every
        # sub-operation; the modal hands it back via submit_root_password().
        self._root_password = None
        self._pwd_lock = threading.Lock()
        self._pwd_event = threading.Event()
        self._pwd_submitted = None

        # Confirmation / message dialogs (same blocking-modal pattern as the password
        # broker). WebKitGTK has no window.confirm/alert, so these route through HTML
        # modals that call back via submit_confirmation() / submit_message_ack().
        self._dialog_lock = threading.Lock()
        self._confirm_event = threading.Event()
        self._confirm_result = False
        self._confirm_selections = None  # per-component selections from the modal
        self._message_event = threading.Event()

        # Prepare the managers in a background thread to prevent GUI lockup using ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._prepare_future = self._executor.submit(self._prepare_manager)

    def set_window(self, window):
        self.window = window
        self.logger.info("pywebview window reference linked in AtlasApi")

    # ------------------------------------------------------------------ #
    # Root-password broker
    # ------------------------------------------------------------------ #
    def submit_root_password(self, password):
        """js_api callback: the password modal calls this with the entered value
        (or null when the user cancels)."""
        self._pwd_submitted = password
        self._pwd_event.set()
        return {'status': 'ok'}

    def _prompt_root_password_once(self, message: str) -> Optional[str]:
        """Show the modal and block this worker thread until the user submits/cancels.

        pywebview dispatches each js_api call on its own thread, so blocking here is
        safe — submit_root_password() fires from a separate worker and releases us."""
        if not self.window:
            return None

        self._pwd_submitted = None
        self._pwd_event.clear()
        try:
            self.window.evaluate_js(f"showPasswordModal({json.dumps(message)})")
        except Exception as e:
            self.logger.error(f"Could not show password modal: {e}")
            return None

        # Long timeout so a forgotten prompt can't wedge the worker forever.
        if not self._pwd_event.wait(timeout=300):
            self.logger.warning("Root password prompt timed out")
            return None

        return self._pwd_submitted

    def acquire_root_password(self, action: SoftwareAction, pkg) -> Tuple[bool, Optional[str]]:
        """Resolve the root password needed for `action` on `pkg`.

        Returns (proceed, password):
          - (True, None)  → the operation needs no root.
          - (True, pwd)   → a validated password (cached for the session).
          - (False, None) → the user cancelled; the caller must abort.
        """
        try:
            if not self.manager.requires_root(action, pkg):
                return True, None
        except Exception as e:
            self.logger.warning(f"requires_root check failed, assuming root needed: {e}")

        pwd = self.ensure_root_password()
        return (True, pwd) if pwd is not None else (False, None)

    def ensure_root_password(self) -> Optional[str]:
        """Return a validated root password (cached for the session), prompting if
        needed. Returns None if the user cancels or the prompt times out. Used both by
        acquire_root_password() and by WebviewWatcher when a gem requests it directly."""
        with self._pwd_lock:
            if self._root_password is not None and validate_root_password(self._root_password):
                return self._root_password

            message = 'Root privileges are required. Enter your password:'
            for _ in range(3):
                pwd = self._prompt_root_password_once(message)
                if pwd is None:
                    return None  # cancelled / timed out
                if validate_root_password(pwd):
                    self._root_password = pwd
                    return pwd
                message = 'Incorrect password. Try again:'

            return None

    # ------------------------------------------------------------------ #
    # Confirmation / message dialogs
    # ------------------------------------------------------------------ #
    def submit_confirmation(self, confirmed, selections=None):
        """js_api callback: the confirm modal calls this with True/False and, when the
        modal rendered input components, the per-component selections (a list parallel to
        the components that were sent — see WebviewWatcher._serialize_components)."""
        self._confirm_result = bool(confirmed)
        self._confirm_selections = selections
        self._confirm_event.set()
        return {'status': 'ok'}

    def submit_message_ack(self):
        """js_api callback: the message modal's OK button calls this."""
        self._message_event.set()
        return {'status': 'ok'}

    def prompt_confirmation(self, title: str, body: Optional[str],
                            confirmation_label: Optional[str] = None,
                            deny_label: Optional[str] = None,
                            deny_button: bool = True,
                            components: Optional[list] = None,
                            review: Optional[dict] = None) -> Tuple[bool, Optional[list]]:
        """Show a blocking confirmation modal; return ``(confirmed, selections)``.

        `components` is an already-serialized list of input components (checkbox lists,
        single-select combos/radios, forms) produced by
        `WebviewWatcher._serialize_components`. The modal renders them and returns the
        per-component selections, which the watcher applies back onto the original
        component objects. If the modal can't be shown, default to confirmed=True so
        non-critical confirmations don't block work."""
        if not self.window:
            return True, None

        with self._dialog_lock:
            self._confirm_result = False
            self._confirm_selections = None
            self._confirm_event.clear()
            payload = json.dumps({
                'title': title or '',
                'message': body or '',
                'confirmLabel': confirmation_label or 'Yes',
                'denyLabel': deny_label or 'No',
                'showDeny': bool(deny_button),
                'components': components or [],
                'review': review or None,
            })
            try:
                self.window.evaluate_js(f"showConfirmModal({payload})")
            except Exception as e:
                self.logger.error(f"Could not show confirmation modal: {e}")
                return True, None

            if not self._confirm_event.wait(timeout=300):
                self.logger.warning(f"Confirmation '{title}' timed out; defaulting to deny")
                return False, None

            return self._confirm_result, self._confirm_selections

    def prompt_message(self, title: str, body: str, type_: str = 'info'):
        """Show a blocking informational modal; returns once the user dismisses it."""
        if not self.window:
            return

        with self._dialog_lock:
            self._message_event.clear()
            payload = json.dumps({
                'title': title or '',
                'message': body or '',
                'type': type_ or 'info',
            })
            try:
                self.window.evaluate_js(f"showMessageModal({payload})")
            except Exception as e:
                self.logger.error(f"Could not show message modal: {e}")
                return

            # Don't wedge a worker forever if the user never clicks OK.
            self._message_event.wait(timeout=300)

    def _prepare_manager(self):
        try:
            self.logger.info("Initializing software managers in background thread...")
            # prepare(task_manager, root_password, internet_available)
            self.manager.prepare(task_manager=None, root_password=None, internet_available=True)
            self.logger.info("Software managers successfully prepared.")
        except Exception:
            self.logger.error("Error during software managers preparation:")
            traceback.print_exc()

    def _get_valid_icon_url(self, icon_url: Optional[str]) -> str:
        if not icon_url:
            return ''
        if not icon_url.startswith(('data:', 'http://', 'https://')):
            local_path = icon_url[7:] if icon_url.startswith('file://') else icon_url
            import os
            if os.path.isfile(local_path):
                try:
                    import base64
                    import mimetypes
                    mime_type, _ = mimetypes.guess_type(local_path)
                    mime_type = mime_type or 'image/png'
                    with open(local_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                        return f"data:{mime_type};base64,{b64_data}"
                except Exception as e:
                    self.logger.warning(f"Could not load local icon {local_path}: {e}")
            return ''
        return icon_url

    # Standard icon locations searched for an installed app's icon. Plain filesystem search (no
    # Gtk.IconTheme — that isn't safe off the GTK main thread). SVG/mid-size first (small data URIs).
    _ICON_DIRS = (
        '/usr/share/icons/hicolor/scalable/apps',
        '/usr/share/icons/hicolor/128x128/apps',
        '/usr/share/icons/hicolor/256x256/apps',
        '/usr/share/icons/hicolor/64x64/apps',
        '/usr/share/icons/hicolor/512x512/apps',
        '/usr/share/icons/hicolor/48x48/apps',
        '/usr/share/pixmaps',
    )
    _ICON_EXTS = ('.svg', '.png')  # web-renderable only — WebKitGTK can't display .xpm in <img>

    # Base directories an icon theme can live under, in XDG lookup order (user dirs win).
    _ICON_BASE_DIRS = (
        os.path.expanduser('~/.local/share/icons'),
        os.path.expanduser('~/.icons'),
        '/usr/share/icons',
    )

    @staticmethod
    def _desktop_icon_name(desktop_text: str) -> Optional[str]:
        """The `Icon=` value from a .desktop file's first occurrence, or None."""
        for line in (desktop_text or '').splitlines():
            line = line.strip()
            if line.startswith('Icon='):
                return line[5:].strip() or None
        return None

    @staticmethod
    def _read_keyfile_sections(path: str) -> dict:
        """Minimal `[Section] key=value` parser for index.theme (we avoid configparser — some
        index.theme files trip it up, and GKeyFile isn't thread-safe off the GTK loop)."""
        sections, cur = {}, None
        try:
            with open(path, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('[') and line.endswith(']'):
                        cur = line[1:-1]
                        sections[cur] = {}
                    elif cur is not None and '=' in line:
                        k, _, v = line.partition('=')
                        sections[cur][k.strip()] = v.strip()
        except Exception:
            return {}
        return sections

    def _active_icon_theme(self) -> str:
        """The user's active icon theme name (gsettings → gtk-3.0 settings.ini → 'hicolor').
        Cached for the session. Pure subprocess/file reads — safe off the GTK main thread."""
        if hasattr(self, '_icon_theme_name'):
            return self._icon_theme_name
        theme = None
        try:
            out = run_cmd('gsettings get org.gnome.desktop.interface icon-theme',
                          ignore_return_code=True, print_error=False)
            if out:
                theme = out.strip().strip("'\"") or None
        except Exception:
            pass
        if not theme:
            ini = os.path.expanduser('~/.config/gtk-3.0/settings.ini')
            try:
                if os.path.isfile(ini):
                    with open(ini, encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if line.strip().lower().startswith('gtk-icon-theme-name'):
                                theme = line.partition('=')[2].strip().strip('"\'') or None
                                break
            except Exception:
                pass
        self._icon_theme_name = theme or 'hicolor'
        return self._icon_theme_name

    def _theme_app_dirs(self, theme: str, seen: set) -> list:
        """Absolute Applications-context icon directories for `theme` and the themes it
        Inherits, ordered best-first (scalable, then largest size). Filesystem-only — parses
        each index.theme's Directories list rather than walking the (huge) theme trees."""
        if not theme or theme in seen:
            return []
        seen.add(theme)
        result, inherits = [], []
        for base in self._ICON_BASE_DIRS:
            theme_root = os.path.join(base, theme)
            index = os.path.join(theme_root, 'index.theme')
            if not os.path.isfile(index):
                continue
            sections = self._read_keyfile_sections(index)
            header = sections.get('Icon Theme', {})
            scored = []
            for d in (x.strip() for x in header.get('Directories', '').split(',') if x.strip()):
                sec = sections.get(d, {})
                ctx = sec.get('Context', '')
                if (ctx and ctx.lower() != 'applications') or (not ctx and 'apps' not in d.lower()):
                    continue
                try:
                    size = int(sec.get('Size', '0'))
                except ValueError:
                    size = 0
                is_scalable = sec.get('Type', '').lower() == 'scalable' or 'scalable' in d.lower()
                full = os.path.join(theme_root, d)
                if os.path.isdir(full):
                    scored.append((is_scalable, size, full))
            scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
            result.extend(full for _, _, full in scored)
            inherits.extend(p.strip() for p in header.get('Inherits', '').split(',') if p.strip())
        for parent in inherits:
            result.extend(self._theme_app_dirs(parent, seen))
        return result

    def _theme_icon_dirs(self) -> list:
        """The active icon theme's app dirs (+ inherited), resolved once and cached. Empty for
        the bare 'hicolor' theme (already covered by the hardcoded _ICON_DIRS)."""
        if hasattr(self, '_theme_icon_dirs_cache'):
            return self._theme_icon_dirs_cache
        dirs = []
        try:
            theme = self._active_icon_theme()
            if theme and theme != 'hicolor':
                dirs = self._theme_app_dirs(theme, set())
        except Exception as e:
            self.logger.debug(f"theme icon dir resolution failed: {e}")
        self._theme_icon_dirs_cache = dirs
        return dirs

    def _find_icon_file(self, name: str) -> Optional[str]:
        """Resolve an icon name (or absolute path) to a file. Searches the active icon theme's
        dirs first (so theme-specific icons like Papirus/breeze konsole resolve), then falls
        back to the hardcoded hicolor/pixmaps list."""
        if not name:
            return None
        if name.startswith('/'):
            return name if os.path.isfile(name) else None
        candidates = list(dict.fromkeys([name, os.path.splitext(name)[0]]))  # name + stem, deduped
        for d in (*self._theme_icon_dirs(), *self._ICON_DIRS):
            for cand in candidates:
                for ext in self._ICON_EXTS:
                    path = os.path.join(d, cand + ext)
                    if os.path.isfile(path):
                        return path
        return None

    def _resolve_installed_icon(self, pkgname: str) -> str:
        """Find an installed package's icon (via its .desktop `Icon=`, then by package name) and
        return it as a base64 data URI, or '' if none found."""
        import shlex
        names = []
        try:
            out = run_cmd(f'pacman -Ql {shlex.quote(pkgname)}', ignore_return_code=True, print_error=False) or ''
            for line in out.splitlines():
                line = line.strip()
                if line.endswith('.desktop') and '/applications/' in line:
                    path = line.split(' ', 1)[1].strip() if ' ' in line else line
                    try:
                        with open(path) as f:
                            nm = self._desktop_icon_name(f.read())
                        if nm:
                            names.append(nm)
                    except Exception:
                        continue
        except Exception as e:
            self.logger.debug(f"could not read files for '{pkgname}': {e}")
        names.append(pkgname)  # fallback: icon named after the package
        for nm in names:
            path = self._find_icon_file(nm)
            if path:
                return self._get_valid_icon_url(path)  # base64 data URI
        return ''

    def get_pkg_icon(self, pkg_id: str) -> dict:
        """Lazily resolve an *installed* package's icon from the system (.desktop / icon theme dirs),
        for cards that have no icon otherwise. Cached per pkg_id; returns '' when none found."""
        if not hasattr(self, '_installed_icon_cache'):
            self._installed_icon_cache = {}
        if pkg_id in self._installed_icon_cache:
            return {'status': 'ok', 'data': self._installed_icon_cache[pkg_id]}
        data = ''
        pkg = self._get_pkg(pkg_id)
        if pkg is not None and getattr(pkg, 'installed', False):
            try:
                data = self._resolve_installed_icon(pkg.name or '')
            except Exception as e:
                self.logger.debug(f"get_pkg_icon failed for {pkg_id}: {e}")
        self._installed_icon_cache[pkg_id] = data
        return {'status': 'ok', 'data': data}

    def _get_pkg_id(self, pkg) -> str:
        try:
            pkg_type = pkg.get_type() or pkg.gem_name
        except Exception:
            pkg_type = getattr(pkg, 'gem_name', 'unknown') or 'unknown'
        return f"{pkg_type}:{pkg.name}"

    def _serialize_pkg(self, pkg) -> dict:
        pkg_id = self._get_pkg_id(pkg)
        with self._registry_lock:
            if len(self.pkg_registry) > 2000:
                self.pkg_registry.clear()
            self.pkg_registry[pkg_id] = pkg

        
        try:
            publisher = pkg.get_publisher() or ''
        except Exception:
            publisher = ''

        try:
            pkg_type = pkg.get_type() or pkg.gem_name
        except Exception:
            pkg_type = pkg.gem_name

        app_id = getattr(pkg, 'id', None)
        icon_url = self._get_valid_icon_url(pkg.icon_url)
        # Flatpak search results carry no icon (it's only fetched on the detail view). Derive the
        # predictable Flathub CDN icon URL from the app_id so the frontend lazy-loader can show it
        # (it probes silently and falls back to the letter avatar on 404 / non-Flathub remotes).
        if not icon_url and app_id and str(pkg_type).lower() == 'flatpak':
            icon_url = f'https://dl.flathub.org/repo/appstream/x86_64/icons/128x128/{app_id}.png'

        return {
            'id': pkg_id,
            'name': pkg.name or '',
            'description': pkg.description or '',
            'version': pkg.version or '',
            'latest_version': pkg.latest_version or '',
            'type': pkg_type,
            'installed': bool(pkg.installed),
            'update_available': bool(pkg.update),
            'icon_url': icon_url,
            'publisher': publisher,
            'size': pkg.size,
            'download_size': getattr(pkg, 'download_size', None),
            'categories': list(pkg.categories) if pkg.categories else [],
            'can_be_run': pkg.can_be_run() if hasattr(pkg, 'can_be_run') else False,
            'can_be_downgraded': pkg.can_be_downgraded() if hasattr(pkg, 'can_be_downgraded') else False,
            'has_info': pkg.has_info() if hasattr(pkg, 'has_info') else False,
            'has_history': pkg.has_history() if hasattr(pkg, 'has_history') else False,
            'has_screenshots': pkg.has_screenshots() if hasattr(pkg, 'has_screenshots') else False,
            'update_ignored': pkg.is_update_ignored() if hasattr(pkg, 'is_update_ignored') else False,
            'supports_pinning': pkg.supports_ignored_updates() if hasattr(pkg, 'supports_ignored_updates') else False,
            # AUR metadata (None for non-Arch packages) — used to rank/badge AUR variants
            # in the webview. See docs/plans/2026-06-01-source-types-and-multisource-cards.md.
            'votes': getattr(pkg, 'votes', None),
            'popularity': getattr(pkg, 'popularity', None),
            # epoch seconds; populated for AUR (from the AUR RPC). Used by the Sort dropdown's
            # "recently updated" mode — None for non-AUR sources (they sort last there).
            'last_modified': getattr(pkg, 'last_modified', None),
            'maintainer': getattr(pkg, 'maintainer', None),
            'out_of_date': bool(getattr(pkg, 'out_of_date', None)),
            'package_base': getattr(pkg, 'package_base', None),
            # gem-native id (e.g. the Flatpak appstream id 'org.gimp.GIMP') — distinct from
            # the registry 'id' above (type:name); used to build the Flathub page link.
            'app_id': app_id,
        }

    def _get_pkg(self, pkg_id: str):
        with self._registry_lock:
            pkg = self.pkg_registry.get(pkg_id)
            if pkg:
                return pkg
        
        # Self-healing fallback: find package dynamically by name and type if not registered
        if ":" in pkg_id:
            pkg_type, name = pkg_id.split(":", 1)
            try:
                res = self.manager.search(words=name)
                candidates = (res.installed or []) + (res.new or [])
                for candidate in candidates:
                    try:
                        cand_type = candidate.get_type() or candidate.gem_name
                    except Exception:
                        cand_type = getattr(candidate, 'gem_name', 'unknown') or 'unknown'
                    
                    if cand_type == pkg_type and candidate.name == name:
                        with self._registry_lock:
                            self.pkg_registry[pkg_id] = candidate
                        return candidate
            except Exception:
                pass
        return None


    def pin_update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.manager.ignore_update(pkg)
            self.logger.info(f"Pinned package: {pkg.name}")
            return {'status': 'ok', 'success': True}
        except Exception as e:
            self.logger.error(f"Error pinning package {pkg.name}: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def unpin_update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.manager.revert_ignored_update(pkg)
            self.logger.info(f"Unpinned package: {pkg.name}")
            return {'status': 'ok', 'success': True}
        except Exception as e:
            self.logger.error(f"Error unpinning package {pkg.name}: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_suggestions(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info("get_suggestions called")
            suggestions = self.manager.list_suggestions(limit=20, filter_installed=False)
            pkgs = [s.package for s in (suggestions or [])]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching suggestions: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def _category_names(self, raw_labels) -> set:
        """Package names whose category map intersects a bucket's set of raw labels."""
        arch_man = self._manager_by_gem('arch')
        if arch_man is None or not hasattr(arch_man, 'read_categories'):
            return set()

        cat_map = arch_man.read_categories() or {}
        wanted = set(raw_labels)
        return {name for name, cats in cat_map.items() if cats and wanted.intersection(cats)}

    def get_categories(self) -> dict:
        """Top-level browse buckets with the count of distinct repo-indexed packages in each.
        Cheap: reads the (cached) Arch category map and inverts it; no network."""
        try:
            self.logger.info("get_categories called")
            buckets = []
            for key, label, icon, raw, _flathub_cat, description in self.CATEGORY_BUCKETS:
                count = len(self._category_names(raw))
                if count:
                    buckets.append({'key': key, 'label': label, 'icon': icon, 'count': count,
                                    'description': description})
            return {'status': 'ok', 'data': buckets}
        except Exception as e:
            self.logger.error(f"Error listing categories: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_category_packages(self, key: str) -> dict:
        """Packages in a browse bucket. Arch-only: categories.txt is a repo index, so this
        resolves names through the Arch gem's lightweight repo lookup (no AUR/network)."""
        try:
            self.logger.info(f"get_category_packages called: {key}")
            bucket = next((b for b in self.CATEGORY_BUCKETS if b[0] == key), None)
            if bucket is None:
                return {'status': 'error', 'message': f'Unknown category: {key}'}

            names = self._category_names(bucket[3])
            arch_man = self._manager_by_gem('arch')
            pkgs = []
            if arch_man is not None and names:
                pkgs.extend(arch_man.list_category_packages(names))

            # Also list Flathub apps in the matching top-level category (one best-effort HTTP
            # call). The frontend's collapseByName() merges any same-named Arch+Flatpak pair into
            # one multi-source card. Skipped when the gem is disabled/can't work or has no category.
            flathub_cat = bucket[4]
            flatpak_man = self._manager_by_gem('flatpak')
            if flathub_cat and flatpak_man is not None and hasattr(flatpak_man, 'list_category_packages'):
                try:
                    if flatpak_man.is_enabled() and flatpak_man.can_work()[0]:
                        pkgs.extend(flatpak_man.list_category_packages(flathub_cat))
                except Exception:
                    self.logger.warning("Could not list Flatpak category packages", exc_info=True)

            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching category packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    # ---- AUR discovery buckets -----------------------------------------------------------
    # AUR has no category taxonomy and the RPC has no "browse all" endpoint, so we precompute
    # discovery buckets (Popular / Recently updated / VCS / Binary) in the atlas-files repo and
    # fetch the small result here. See docs/plans/2026-06-05-aur-discovery-buckets.md.

    def _fetch_aur_discovery(self) -> Optional[dict]:
        """The precomputed AUR discovery JSON, cached in-memory with a 1 h TTL (it refreshes daily
        server-side). Best-effort via the AUR client's HTTP client; returns the last good cache (or
        None) on any failure so Browse never breaks."""
        now = time.time()
        if self._aur_discovery_cache is not None and (now - self._aur_discovery_cache_ts) < self._AUR_DISCOVERY_TTL:
            return self._aur_discovery_cache
        arch_man = self._manager_by_gem('arch')
        client = getattr(getattr(arch_man, 'aur_client', None), 'http_client', None)
        if client is None:
            return self._aur_discovery_cache
        try:
            data = client.get_json(self.AUR_DISCOVERY_URL)
            if isinstance(data, dict) and data.get('buckets'):
                self._aur_discovery_cache = data
                self._aur_discovery_cache_ts = now
        except Exception as e:
            self.logger.warning(f"Could not fetch AUR discovery data: {e}")
        return self._aur_discovery_cache

    def get_aur_discovery(self) -> dict:
        """Top-level AUR discovery buckets with their entry counts, for the Browse view. Empty when
        the arch/AUR gem is absent or the data can't be fetched (Browse just won't show the row)."""
        try:
            arch_man = self._manager_by_gem('arch')
            if arch_man is None or getattr(arch_man, 'aur_client', None) is None:
                return {'status': 'ok', 'data': []}
            data = self._fetch_aur_discovery()
            buckets = (data or {}).get('buckets') or {}
            out = []
            for key, label, icon in self.AUR_BUCKETS:
                items = buckets.get(key) or []
                if items:
                    out.append({'key': key, 'label': label, 'icon': icon, 'count': len(items)})
            return {'status': 'ok', 'data': out}
        except Exception as e:
            self.logger.error(f"Error listing AUR discovery buckets: {e}")
            return {'status': 'ok', 'data': []}

    def get_aur_bucket_packages(self, key: str) -> dict:
        """Packages in an AUR discovery bucket as installable cards. The precomputed entries are
        AUR-RPC-shaped, so the arch gem maps them to real ArchPackage objects (install / detail /
        preview all work through the normal paths)."""
        try:
            self.logger.info(f"get_aur_bucket_packages called: {key}")
            valid = {k for k, _l, _i in self.AUR_BUCKETS}
            if key not in valid:
                return {'status': 'error', 'message': f'Unknown AUR bucket: {key}'}
            data = self._fetch_aur_discovery()
            entries = ((data or {}).get('buckets') or {}).get(key) or []
            arch_man = self._manager_by_gem('arch')
            pkgs = []
            if arch_man is not None and hasattr(arch_man, 'list_aur_packages'):
                pkgs = arch_man.list_aur_packages(entries)
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching AUR bucket packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_installed(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info("get_installed called")
            result = self.manager.read_installed()
            # Hide Flatpak runtimes / extensions / themes / locales (runtime refs) from the
            # Installed view — users browse apps, not the dozens of low-level deps. They
            # still count toward the Disk view, which has its own read_installed call.
            pkgs = [p for p in (result.installed or []) if not getattr(p, 'runtime', False)]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching installed packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_orphans(self) -> dict:
        try:
            self.logger.info("get_orphans called")

            # Real removable orphans = packages installed as deps that nothing requires
            # (pacman -Qtdq). NOT the ArchPackage.orphan property, which means "AUR package
            # with no maintainer" — a totally different thing that wrongly flagged installed
            # apps for deletion.
            arch_man = self._manager_by_gem('arch')
            orphan_names = set()
            if arch_man is not None and hasattr(arch_man, 'list_orphans'):
                try:
                    orphan_names = set(arch_man.list_orphans() or ())
                except Exception:
                    self.logger.warning("Could not list orphan packages", exc_info=True)

            if not orphan_names:
                return {'status': 'ok', 'data': []}

            result = self.manager.read_installed()
            orphans = []
            for p in (result.installed or []):
                if p.name not in orphan_names:
                    continue
                try:
                    ptype = p.get_type() or p.gem_name
                except Exception:
                    ptype = getattr(p, 'gem_name', None)
                if ptype in ('arch_repo', 'aur'):  # orphan-dep concept is Arch-only
                    orphans.append(p)

            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in orphans]}
        except Exception as e:
            self.logger.error(f"Error fetching orphan packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_orphan_count(self) -> dict:
        """Cheap orphan count for the cleanup button — just `pacman -Qtdq`, no read_installed
        (which is slow). The full list is fetched via get_orphans() only when cleaning up."""
        try:
            arch_man = self._manager_by_gem('arch')
            count = 0
            if arch_man is not None and hasattr(arch_man, 'list_orphans'):
                count = len(arch_man.list_orphans() or ())
            return {'status': 'ok', 'count': count}
        except Exception as e:
            self.logger.error(f"Error counting orphans: {e}")
            return {'status': 'error', 'message': str(e), 'count': 0}

    # ------------------------------------------------------------------ #
    # Maintenance / cleanup (Disk view "Reclaim space" panel)
    # ------------------------------------------------------------------ #
    def get_cleanup_summary(self) -> dict:
        """Cheap, read-only summary for the Maintenance panel: orphan count, total pacman
        cache size, and whether Flatpak unused-runtime cleanup is available. Deliberately
        avoids read_installed() (and anything needing root) so it's fast enough to call on
        view open — the exact reclaimable amount is reported after cleaning instead, since
        `pacman -Sc --print` needs root."""
        data = {
            'orphans': {'count': 0},
            'pacman_cache': {'available': False, 'total_bytes': 0, 'total_human': '0 B'},
            'flatpak': {'available': False},
        }

        try:
            arch_man = self._manager_by_gem('arch')
            if arch_man is not None and hasattr(arch_man, 'list_orphans'):
                data['orphans']['count'] = len(arch_man.list_orphans() or ())
        except Exception:
            self.logger.warning("cleanup summary: orphan count failed", exc_info=True)

        try:
            if os.path.isdir(self.PACMAN_CACHE_DIR):
                total = get_dir_size(self.PACMAN_CACHE_DIR) or 0
                data['pacman_cache'] = {
                    'available': True,
                    'total_bytes': total,
                    'total_human': get_human_size_str(total) or '0 B',
                }
        except Exception:
            self.logger.warning("cleanup summary: pacman cache sizing failed", exc_info=True)

        try:
            flatpak_man = self._manager_by_gem('flatpak')
            if shutil.which('flatpak') and flatpak_man is not None:
                try:
                    enabled = flatpak_man.is_enabled()
                except Exception:
                    enabled = True
                data['flatpak']['available'] = bool(enabled)
        except Exception:
            self.logger.warning("cleanup summary: flatpak availability check failed", exc_info=True)

        return {'status': 'ok', 'data': data}

    def get_dashboard_summary(self) -> dict:
        """Aggregated, best-effort "what needs my attention" signals for the dashboard Attention
        Center. Runs the cheap checks concurrently on the shared executor and fails open per
        field (a failed check → None / default), so the dashboard always renders. Updates are
        intentionally excluded — they need read_installed() (expensive); the frontend fetches
        those separately. See docs/plans/2026-06-04-dashboard-attention-center.md."""
        from datetime import datetime, timezone

        def _safety():
            out = {'pacnew_count': None, 'db_sync_age_hours': None,
                   'pacman_locked': None, 'news_count': None}
            try:
                pn = self.get_pacnew_files()
                if pn.get('status') == 'ok':
                    out['pacnew_count'] = pn['data']['count']
            except Exception:
                pass
            try:
                synced = self._last_db_sync_time()
                if synced is not None:
                    age = (datetime.now(timezone.utc) - synced).total_seconds()
                    out['db_sync_age_hours'] = round(age / 3600.0, 1)
            except Exception:
                pass
            try:
                out['pacman_locked'] = os.path.exists('/var/lib/pacman/db.lck')
            except Exception:
                pass
            try:
                nw = self.check_upgrade_news()
                if nw.get('status') == 'ok':
                    out['news_count'] = nw['data'].get('new_count')
            except Exception:
                pass
            return out

        def _reclaim():
            out = {'orphans': None, 'cache_human': None, 'flatpak_available': False}
            try:
                cs = self.get_cleanup_summary()
                if cs.get('status') == 'ok':
                    d = cs['data']
                    out['orphans'] = d.get('orphans', {}).get('count')
                    pc = d.get('pacman_cache', {})
                    out['cache_human'] = pc.get('total_human') if pc.get('available') else None
                    out['flatpak_available'] = bool(d.get('flatpak', {}).get('available'))
            except Exception:
                pass
            return out

        def _aur():
            out = {'chroot_enabled': False, 'chroot_available': False}
            arch_man = self._manager_by_gem('arch')
            if arch_man is not None:
                try:
                    aconf = arch_man.configman.get_config()
                    out['chroot_enabled'] = bool(aconf.get('aur_build_chroot', False))
                except Exception:
                    pass
                try:
                    from atlas.gems.arch import chroot
                    out['chroot_available'] = bool(chroot.available())
                except Exception:
                    pass
            return out

        def _activity():
            try:
                act = self.get_activity()
                if act.get('status') == 'ok':
                    return (act.get('data') or [])[:3]
            except Exception:
                pass
            return []

        try:
            jobs = {'safety': _safety, 'reclaim': _reclaim, 'aur': _aur, 'activity': _activity}
            futures = {key: self._executor.submit(fn) for key, fn in jobs.items()}
            data = {}
            for key, fut in futures.items():
                try:
                    data[key] = fut.result(timeout=20)
                except Exception:
                    self.logger.warning(f"dashboard summary: {key} check failed", exc_info=True)
                    data[key] = {} if key != 'activity' else []
            data['user'] = self._dashboard_user()  # cheap; for the greeting ("Good morning, X")
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_dashboard_summary failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_system_health(self) -> dict:
        """Package-management health checks for the System Health page. Cheap signals run
        concurrently and fail open per field (a failed probe → None), so the page always renders.
        Overlaps get_dashboard_summary by design (both read-only/cheap). See
        docs/plans/2026-06-04-system-health.md."""
        from datetime import datetime, timezone

        def _db_sync():
            try:
                synced = self._last_db_sync_time()
                if synced is not None:
                    age = (datetime.now(timezone.utc) - synced).total_seconds()
                    return {'age_hours': round(age / 3600.0, 1)}
            except Exception:
                pass
            return {'age_hours': None}

        def _mirrors():
            try:
                return {'tool': (self._mirror_regen_cmd() or [None])[0]}
            except Exception:
                return {'tool': None}

        def _lock():
            try:
                return {'locked': os.path.exists('/var/lib/pacman/db.lck')}
            except Exception:
                return {'locked': None}

        def _pacnew():
            try:
                pn = self.get_pacnew_files()
                return {'count': pn['data']['count'] if pn.get('status') == 'ok' else None}
            except Exception:
                return {'count': None}

        def _reclaim():
            out = {'orphans': None, 'cache': None, 'flatpak': False}
            try:
                cs = self.get_cleanup_summary()
                if cs.get('status') == 'ok':
                    d = cs['data']
                    out['orphans'] = d.get('orphans', {}).get('count')
                    pc = d.get('pacman_cache', {})
                    out['cache'] = pc.get('total_human') if pc.get('available') else None
                    out['flatpak'] = bool(d.get('flatpak', {}).get('available'))
            except Exception:
                pass
            return out

        def _keyring():
            # archlinux-keyring freshness: a stale keyring causes "invalid/corrupted package (PGP
            # signature)" errors. The local-db entry's mtime ≈ when it was last installed/updated.
            try:
                import glob as _glob
                dirs = _glob.glob('/var/lib/pacman/local/archlinux-keyring-*')
                if dirs:
                    mtime = max(os.path.getmtime(d) for d in dirs)
                    age = datetime.now(timezone.utc).timestamp() - mtime
                    return {'age_days': round(age / 86400.0, 1)}
            except Exception:
                pass
            return {'age_days': None}

        def _aur_index():
            # Age of the cached AUR package-name index (used for dependency resolution).
            try:
                from atlas.gems.arch import AUR_INDEX_FILE
                if os.path.exists(AUR_INDEX_FILE):
                    age = datetime.now(timezone.utc).timestamp() - os.path.getmtime(AUR_INDEX_FILE)
                    return {'age_days': round(age / 86400.0, 1)}
            except Exception:
                pass
            return {'age_days': None}

        def _chroot():
            out = {'enabled': False, 'available': False}
            arch_man = self._manager_by_gem('arch')
            if arch_man is not None:
                try:
                    out['enabled'] = bool(arch_man.configman.get_config().get('aur_build_chroot', False))
                except Exception:
                    pass
                try:
                    from atlas.gems.arch import chroot
                    out['available'] = bool(chroot.available())
                except Exception:
                    pass
            return out

        try:
            jobs = {'db_sync': _db_sync, 'mirrors': _mirrors, 'lock': _lock,
                    'pacnew': _pacnew, 'reclaim': _reclaim, 'chroot': _chroot,
                    'keyring': _keyring, 'aur_index': _aur_index}
            futures = {k: self._executor.submit(fn) for k, fn in jobs.items()}
            data = {}
            for k, fut in futures.items():
                try:
                    data[k] = fut.result(timeout=20)
                except Exception:
                    self.logger.warning(f"system health: {k} check failed", exc_info=True)
                    data[k] = {}
            rec = data.pop('reclaim', {}) or {}
            data['orphans'] = {'count': rec.get('orphans')}
            data['cache'] = {'human': rec.get('cache')}
            data['flatpak'] = {'unused_available': bool(rec.get('flatpak'))}
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_system_health failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def remove_pacman_lock(self) -> dict:
        """Remove a stale pacman db lock (`/var/lib/pacman/db.lck`). **Gated:** refuses while a
        pacman process is actually running (the lock is legitimate then). Needs root."""
        lock = '/var/lib/pacman/db.lck'
        try:
            if not os.path.exists(lock):
                return {'status': 'ok', 'removed': False}
            # The lock is legitimate while pacman is actually running — never remove it then.
            try:
                running = run_cmd('pgrep -x pacman', print_error=False)
            except Exception:
                running = None
            if running and running.strip():
                return {'status': 'error',
                        'message': 'A package operation is running (pacman is active) — do not remove the lock.'}
            pwd = self.ensure_root_password()
            if pwd is None:
                return {'status': 'cancelled'}
            proc = new_root_subprocess(['rm', '-f', lock], root_password=pwd)
            _, err = proc.communicate()
            if proc.returncode != 0:
                msg = (err or b'').decode(errors='replace').strip() or 'failed to remove the lock'
                self.logger.error(f"remove_pacman_lock: {msg}")
                return {'status': 'error', 'message': msg}
            self._notify('Removed the stale pacman lock')
            return {'status': 'ok', 'removed': True}
        except Exception as e:
            self.logger.error(f"remove_pacman_lock failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def refresh_aur_index(self) -> dict:
        """Re-download the AUR package-name index (used for dependency resolution). Non-privileged."""
        try:
            arch_man = self._manager_by_gem('arch')
            if arch_man is None or not hasattr(arch_man, '_update_aur_index'):
                return {'status': 'error', 'message': 'AUR support is not available.'}
            arch_man._update_aur_index(None)
            return {'status': 'ok'}
        except Exception as e:
            self.logger.error(f"refresh_aur_index failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def _dashboard_user(self) -> Optional[str]:
        """A friendly name for the dashboard greeting: the user-set name (Settings) if any, else
        the GECOS full name's first part, else the login name. None if nothing resolves (the
        greeting then omits the name)."""
        try:
            custom = (self.manager.configman.get_config().get('ui') or {}).get('greeting_name')
            if custom and custom.strip():
                return custom.strip()
        except Exception:
            pass
        try:
            import pwd
            gecos = (pwd.getpwuid(os.getuid()).pw_gecos or '').split(',')[0].strip()
            if gecos:
                return gecos
        except Exception:
            pass
        try:
            import getpass
            return getpass.getuser() or None
        except Exception:
            return None

    def clean_pacman_cache(self) -> dict:
        """Remove cached tarballs of packages that are no longer installed (`pacman -Sc`).
        Cache for currently-installed packages is kept, so downgrades still work. Needs root."""
        if not os.path.isdir(self.PACMAN_CACHE_DIR):
            return {'status': 'error', 'message': 'pacman cache directory not found'}
        pwd = self.ensure_root_password()
        if pwd is None:
            return {'status': 'cancelled'}
        try:
            before = get_dir_size(self.PACMAN_CACHE_DIR) or 0
            proc = new_root_subprocess(['pacman', '-Sc', '--noconfirm'], root_password=pwd)
            _, err = proc.communicate()
            if proc.returncode != 0:
                msg = (err or b'').decode(errors='replace').strip() or 'pacman -Sc failed'
                self.logger.error(f"clean_pacman_cache: {msg}")
                return {'status': 'error', 'message': msg}
            after = get_dir_size(self.PACMAN_CACHE_DIR) or 0
            freed_bytes = max(0, before - after)
            freed_human = get_human_size_str(freed_bytes) or '0 B'
            self._notify(f"Freed {freed_human} from the package cache")
            return {'status': 'ok', 'freed_bytes': freed_bytes, 'freed_human': freed_human}
        except Exception as e:
            self.logger.error(f"clean_pacman_cache failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def clean_flatpak_unused(self) -> dict:
        """Remove unused Flatpak runtimes/extensions (`flatpak uninstall --unused`), at the
        scope the app installs to: system (needs root) if configured, else user (no root)."""
        if not shutil.which('flatpak'):
            return {'status': 'error', 'message': 'flatpak is not installed'}
        try:
            level = None
            flatpak_man = self._manager_by_gem('flatpak')
            if flatpak_man is not None:
                try:
                    level = flatpak_man.configman.get_config().get('installation_level')
                except Exception:
                    level = None

            cmd = ['flatpak', 'uninstall', '--unused', '--assumeyes']
            if level == 'system':
                cmd.append('--system')
                pwd = self.ensure_root_password()
                if pwd is None:
                    return {'status': 'cancelled'}
                proc = new_root_subprocess(cmd, root_password=pwd)
            else:
                cmd.append('--user')
                proc = new_subprocess(cmd)

            _, err = proc.communicate()
            if proc.returncode != 0:
                msg = (err or b'').decode(errors='replace').strip() or 'flatpak uninstall --unused failed'
                self.logger.error(f"clean_flatpak_unused: {msg}")
                return {'status': 'error', 'message': msg}
            self._notify("Removed unused Flatpak runtimes")
            return {'status': 'ok'}
        except Exception as e:
            self.logger.error(f"clean_flatpak_unused failed: {e}")
            return {'status': 'error', 'message': str(e)}

    # ------------------------------------------------------------------ #
    # Arch safety net (News page + .pacnew detection)
    # ------------------------------------------------------------------ #
    def _http_client(self):
        """The shared HttpClient (via the arch gem's context), or a lazy fallback."""
        arch_man = self._manager_by_gem('arch')
        client = getattr(getattr(arch_man, 'context', None), 'http_client', None)
        if client is not None:
            return client
        if getattr(self, '_fallback_http', None) is None:
            from atlas.api.http import HttpClient
            self._fallback_http = HttpClient(self.logger)
        return self._fallback_http

    @staticmethod
    def _strip_html(text: str) -> str:
        """Crude HTML→text for news summaries: drop tags, unescape entities, collapse space."""
        import re
        import html
        if not text:
            return ''
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        return re.sub(r'\s+', ' ', text).strip()

    def _fetch_arch_news_items(self, limit: int = 12) -> list:
        """Fetch + parse the archlinux.org RSS feed. Single source of truth for news parsing.
        Returns a list of {title, url, date (display str), summary, dt (aware datetime|None)}.
        Raises on network/parse failure (callers decide how to handle)."""
        import xml.etree.ElementTree as ET
        from datetime import timezone
        from email.utils import parsedate_to_datetime

        res = self._http_client().get(self.ARCH_NEWS_URL, single_call=True)
        if res is None or res.status_code >= 300 or not res.text:
            raise RuntimeError('Could not reach the Arch news feed')

        root = ET.fromstring(res.text)
        items = []
        for item in root.iterfind('./channel/item'):
            title = (item.findtext('title') or '').strip()
            url = (item.findtext('link') or '').strip()
            if not title:
                continue
            dt, date_str = None, ''
            raw_date = (item.findtext('pubDate') or '').strip()
            if raw_date:
                try:
                    dt = parsedate_to_datetime(raw_date)
                    if dt.tzinfo is None:          # treat naive dates as UTC for safe comparison
                        dt = dt.replace(tzinfo=timezone.utc)
                    date_str = dt.strftime('%b %d, %Y')
                except Exception:
                    date_str = raw_date
            summary = self._strip_html(item.findtext('description') or '')
            if len(summary) > 280:
                summary = summary[:277].rstrip() + '…'
            items.append({'title': title, 'url': url, 'date': date_str, 'summary': summary, 'dt': dt})
            if len(items) >= limit:
                break
        return items

    def get_arch_news(self, limit: int = 12) -> dict:
        """Recent Arch Linux news (archlinux.org RSS) for the News page. Read-only; the feed
        is the only network call. Returns {status, data:[{title, url, date, summary}]}."""
        try:
            items = [{k: v for k, v in it.items() if k != 'dt'}
                     for it in self._fetch_arch_news_items(limit)]
            return {'status': 'ok', 'data': items}
        except Exception as e:
            self.logger.error(f"get_arch_news failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def _last_db_sync_time(self):
        """When the local pacman databases were last synced = newest mtime among
        /var/lib/pacman/sync/*.db (rewritten by `pacman -Sy`). Aware UTC datetime, or None."""
        import glob
        from datetime import datetime, timezone
        try:
            mtimes = [os.path.getmtime(p) for p in glob.glob('/var/lib/pacman/sync/*.db')]
            if not mtimes:
                return None
            return datetime.fromtimestamp(max(mtimes), tz=timezone.utc)
        except Exception as e:
            self.logger.debug(f"_last_db_sync_time failed: {e}")
            return None

    def check_upgrade_news(self, limit: int = 12) -> dict:
        """News published since the last DB sync — shown as a pre-upgrade warning so the user
        doesn't `-Syu` into a manual-intervention notice. Fail-open: on any error returns an
        empty result so the upgrade is never blocked by the *check* failing.
        Returns {status, data:{since: iso|null, new_count, news:[{title,url,date,summary}]}}."""
        from datetime import datetime, timedelta, timezone
        try:
            reference = self._last_db_sync_time() or (datetime.now(timezone.utc) - timedelta(days=7))
            items = self._fetch_arch_news_items(limit)
            new_items = [it for it in items if it['dt'] is not None and it['dt'] > reference]
            news = [{k: v for k, v in it.items() if k != 'dt'} for it in new_items]
            return {'status': 'ok', 'data': {'since': reference.isoformat(),
                                             'new_count': len(news), 'news': news}}
        except Exception as e:
            self.logger.warning(f"check_upgrade_news failed (proceeding without a gate): {e}")
            return {'status': 'ok', 'data': {'since': None, 'new_count': 0, 'news': []}}

    def get_pacnew_files(self) -> dict:
        """Find .pacnew/.pacsave config files left by pacman that need manual review.
        Lists by filename only (no content reads, no root). Read-only."""
        try:
            out = run_cmd(r"find /etc /boot -type f \( -name '*.pacnew' -o -name '*.pacsave' \)",
                          ignore_return_code=True, print_error=False)
            files = sorted(line.strip() for line in (out or '').split('\n') if line.strip())
            return {'status': 'ok', 'data': {'files': files, 'count': len(files)}}
        except Exception as e:
            self.logger.error(f"get_pacnew_files failed: {e}")
            return {'status': 'error', 'message': str(e), 'data': {'files': [], 'count': 0}}

    def get_pacnew_diff(self, path: str) -> dict:
        """Read-only unified diff between an installed config and its pending .pacnew/.pacsave,
        for the .pacnew center. Whitelisted to paths actually reported by get_pacnew_files() (no
        arbitrary file read), no root. Returns {status, data:{diff, truncated, readable}}."""
        try:
            listed = set((self.get_pacnew_files().get('data') or {}).get('files') or ())
            if path not in listed:
                return {'status': 'error', 'message': 'Unknown .pacnew file'}
            base = path.rsplit('.pac', 1)[0]  # strip .pacnew / .pacsave
            if not os.path.isfile(base):
                return {'status': 'ok', 'data': {'diff': '', 'truncated': False, 'readable': False}}
            if not os.access(base, os.R_OK) or not os.access(path, os.R_OK):
                return {'status': 'ok', 'data': {'diff': '', 'truncated': False, 'readable': False}}
            import shlex
            out = run_cmd(f'diff -u {shlex.quote(base)} {shlex.quote(path)}',
                          ignore_return_code=True, print_error=False) or ''
            lines = out.splitlines()
            truncated = len(lines) > 400
            diff = '\n'.join(lines[:400])
            return {'status': 'ok', 'data': {'diff': diff, 'truncated': truncated, 'readable': True}}
        except Exception as e:
            self.logger.error(f"get_pacnew_diff failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_mirror_status(self) -> dict:
        """Summary of the active pacman mirror list for Settings → Mirrors: number of enabled
        servers, the top few hosts, when the file was last written, the available regen tool, and
        the exact command that would run. Read-only, best-effort."""
        path = self.MIRRORLIST_PATH
        data = {'count': 0, 'servers': [], 'last_modified_iso': None, 'tool': None, 'command': None}
        try:
            cmd = self._mirror_regen_cmd()
            data['tool'] = cmd[0] if cmd else None
            data['command'] = ' '.join(cmd) if cmd else None
        except Exception:
            pass
        try:
            if os.path.isfile(path):
                from datetime import datetime, timezone
                data['last_modified_iso'] = datetime.fromtimestamp(
                    os.path.getmtime(path), tz=timezone.utc).isoformat()
                hosts = []
                with open(path, encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith('Server') and '=' in s:
                            url = s.split('=', 1)[1].strip()
                            data['count'] += 1
                            if len(hosts) < 5:
                                m = re.match(r'https?://([^/]+)', url)
                                hosts.append(m.group(1) if m else url)
                data['servers'] = hosts
        except Exception as e:
            self.logger.debug(f"get_mirror_status read failed: {e}")
        return {'status': 'ok', 'data': data}

    # Terminal emulators whose exec flag takes the command as SEPARATE args (no shell-quoting).
    # Order = preference. `$TERMINAL` is honored first (see _find_terminal).
    _TERMINAL_LAUNCHERS = (
        ('konsole', ['konsole', '-e']),
        ('gnome-terminal', ['gnome-terminal', '--']),
        ('alacritty', ['alacritty', '-e']),
        ('kitty', ['kitty']),
        ('foot', ['foot']),
        ('wezterm', ['wezterm', 'start', '--']),
        ('xfce4-terminal', ['xfce4-terminal', '-x']),
        ('xterm', ['xterm', '-e']),
    )

    def _find_terminal(self):
        """argv prefix of an available terminal emulator (command appended as separate args), or
        None. Honors $TERMINAL first, then the curated priority list."""
        launchers = dict(self._TERMINAL_LAUNCHERS)
        env_term = os.environ.get('TERMINAL')
        if env_term and shutil.which(env_term):
            return list(launchers.get(env_term, [env_term, '-e']))
        for binary, prefix in self._TERMINAL_LAUNCHERS:
            if shutil.which(binary):
                return list(prefix)
        return None

    def launch_pacdiff(self) -> dict:
        """Open `sudo pacdiff` (from pacman-contrib) in a terminal so the user can merge the
        .pacnew/.pacsave files interactively. We just launch the standard tool — no merging or
        removal happens inside Atlas."""
        import subprocess
        if not shutil.which('pacdiff'):
            return {'status': 'error', 'message': 'pacdiff not found — install the "pacman-contrib" package.'}
        term = self._find_terminal()
        if not term:
            return {'status': 'error', 'message': 'No supported terminal emulator found — run "sudo pacdiff" manually.'}
        cmd = term + ['sudo', 'pacdiff']
        try:
            subprocess.Popen(cmd, start_new_session=True)  # detached; owns its own TTY
            self.logger.info(f"Launched pacdiff: {' '.join(cmd)}")
            return {'status': 'ok'}
        except Exception as e:
            self.logger.error(f"Could not launch pacdiff: {e}")
            return {'status': 'error', 'message': str(e)}

    def _mirror_regen_cmd(self):
        """argv to regenerate /etc/pacman.d/mirrorlist with an installed Arch mirror tool, or None.
        reflector (the Arch standard, writes the file via --save) is preferred; rate-mirrors is a
        fallback. NOT cachyos-rate-mirrors — that targets the CachyOS mirrorlist, not this file."""
        if shutil.which('reflector'):
            return ['reflector', '--protocol', 'https', '--latest', '20', '--sort', 'rate',
                    '--download-timeout', '5', '--save', '/etc/pacman.d/mirrorlist']
        if shutil.which('rate-mirrors'):
            return ['rate-mirrors', '--allow-root', '--save=/etc/pacman.d/mirrorlist', 'arch']
        return None

    def regenerate_mirrorlist(self) -> dict:
        """Regenerate the Arch mirror list (/etc/pacman.d/mirrorlist) with reflector/rate-mirrors.
        Needs root. The safe alternative to merging a mirrorlist.pacnew (which wipes your servers).
        Can take up to a minute (it speed-tests mirrors)."""
        cmd = self._mirror_regen_cmd()
        if not cmd:
            return {'status': 'error', 'message': 'No mirror tool found — install "reflector" (or rate-mirrors).'}
        pwd = self.ensure_root_password()
        if pwd is None:
            return {'status': 'cancelled'}
        try:
            self.logger.info(f"Regenerating mirrorlist: {' '.join(cmd)}")
            proc = new_root_subprocess(cmd, root_password=pwd)
            _, err = proc.communicate()
            if proc.returncode != 0:
                msg = (err or b'').decode(errors='replace').strip() or 'mirror refresh failed'
                self.logger.error(f"regenerate_mirrorlist: {msg}")
                return {'status': 'error', 'message': msg[:300]}
            self._notify('Mirror list regenerated')
            return {'status': 'ok', 'tool': cmd[0]}
        except Exception as e:
            self.logger.error(f"regenerate_mirrorlist failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_updates(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info("get_updates called")
            result = self.manager.read_installed()
            pkgs = [p for p in (result.installed or []) if p.update]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching updates: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def search(self, query: str, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info(f"search called for: {query}")
            result = self.manager.search(words=query)
            pkgs = (result.installed or []) + (result.new or [])
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error searching packages for query '{query}': {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def install(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.logger.info(f"Installing package: {pkg.name}")
            proceed, root_password = self.acquire_root_password(SoftwareAction.INSTALL, pkg)
            if not proceed:
                self.logger.info(f"Install of {pkg.name} cancelled (no root password)")
                return {'status': 'cancelled'}
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Installing {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window, self)
            result = self.manager.install(pkg, root_password=root_password, disk_loader=None, handler=watcher)
            success = result.success if result else False
            warnings = (result.warnings if result else None) or []
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()}, {json.dumps(warnings)})")

            # Record Activity
            record_activity('install', pkg.name, pkg.get_type() or pkg.gem_name, success)
            self._notify(f"{pkg.name} installed successfully" if success else f"Failed to install {pkg.name}")

            return {'status': 'ok', 'success': success, 'warnings': warnings}
        except Exception as e:
            self.logger.error(f"Error installing package {pkg.name}: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('install', pkg.name, pkg.get_type() or pkg.gem_name, False, str(e))
            return {'status': 'error', 'message': str(e)}

    def uninstall(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.logger.info(f"Uninstalling package: {pkg.name}")
            proceed, root_password = self.acquire_root_password(SoftwareAction.UNINSTALL, pkg)
            if not proceed:
                self.logger.info(f"Uninstall of {pkg.name} cancelled (no root password)")
                return {'status': 'cancelled'}
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Uninstalling {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window, self)
            result = self.manager.uninstall(pkg, root_password=root_password, handler=watcher)
            success = result.success if result else False
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")
            
            # Record Activity
            record_activity('uninstall', pkg.name, pkg.get_type() or pkg.gem_name, success)
            self._notify(f"{pkg.name} uninstalled" if success else f"Failed to uninstall {pkg.name}")

            return {'status': 'ok', 'success': success}
        except Exception as e:
            self.logger.error(f"Error uninstalling package {pkg.name}: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('uninstall', pkg.name, pkg.get_type() or pkg.gem_name, False, str(e))
            return {'status': 'error', 'message': str(e)}

    def update(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.logger.info(f"Updating package: {pkg.name}")
            proceed, root_password = self.acquire_root_password(SoftwareAction.UPGRADE, pkg)
            if not proceed:
                self.logger.info(f"Update of {pkg.name} cancelled (no root password)")
                return {'status': 'cancelled'}
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Updating {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window, self)
            reqs = self.manager.get_upgrade_requirements([pkg], root_password=root_password, watcher=watcher)
            success = self.manager.upgrade(reqs, root_password=root_password, handler=watcher)
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(bool(success)).lower()})")
            
            # Record Activity
            record_activity('update', pkg.name, pkg.get_type() or pkg.gem_name, bool(success))
            self._notify(f"{pkg.name} updated" if success else f"Failed to update {pkg.name}")

            return {'status': 'ok', 'success': bool(success)}
        except Exception as e:
            self.logger.error(f"Error updating package {pkg.name}: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('update', pkg.name, pkg.get_type() or pkg.gem_name, False, str(e))
            return {'status': 'error', 'message': str(e)}

    def downgrade(self, pkg_id: str) -> dict:
        """Roll a package back to a previous version. The gem picks the target version
        (and may prompt through the watcher); we just drive the privileged transaction,
        mirroring update()/uninstall()."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.logger.info(f"Downgrading package: {pkg.name}")
            proceed, root_password = self.acquire_root_password(SoftwareAction.DOWNGRADE, pkg)
            if not proceed:
                self.logger.info(f"Downgrade of {pkg.name} cancelled (no root password)")
                return {'status': 'cancelled'}
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Downgrading {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window, self)
            success = bool(self.manager.downgrade(pkg, root_password=root_password, handler=watcher))
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")

            record_activity('downgrade', pkg.name, pkg.get_type() or pkg.gem_name, success)
            self._notify(f"{pkg.name} downgraded" if success else f"Failed to downgrade {pkg.name}")

            return {'status': 'ok', 'success': success}
        except Exception as e:
            self.logger.error(f"Error downgrading package {pkg.name}: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('downgrade', pkg.name, pkg.get_type() or pkg.gem_name, False, str(e))
            return {'status': 'error', 'message': str(e)}

    def get_info(self, pkg_id: str) -> dict:
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            self.logger.info(f"get_info requested for package: {pkg.name}")
            info = self.manager.get_info(pkg)
            return {'status': 'ok', 'data': _json_safe(info or {})}
        except Exception as e:
            self.logger.error(f"Error getting info for package {pkg.name}: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_dependency_summary(self, pkg_id: str) -> dict:
        """A scannable dependency picture for the detail page: ``{direct, optional, required_by,
        makedepends, checkdepends, conflicts, replaces, provides, install_reason, orphan, note}``.
        Reuses the same cheap pacman/AUR signals as the transaction preview and **fails open per
        field** (a failed probe → empty list), so it never blocks the modal. Flatpak has no
        pacman-style deps (runtime-based) → empty + a note; we don't fake it."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        data = {'direct': [], 'optional': [], 'required_by': [], 'note': '',
                'install_reason': None, 'orphan': False,
                'makedepends': [], 'checkdepends': [], 'conflicts': [], 'replaces': [], 'provides': []}
        try:
            ptype = self._preview_ptype(pkg)
            repository = (getattr(pkg, 'repository', None) or '').lower()
            installed = bool(getattr(pkg, 'installed', False))
            if ptype == 'flatpak':
                data['note'] = "Flatpaks bundle their dependencies in a runtime, so there's no per-package dependency list."
                return {'status': 'ok', 'data': data}

            from atlas.gems.arch import pacman
            name = pkg.name
            if repository == 'aur' or ptype == 'aur':
                arch_man = self._manager_by_gem('arch')
                aur_client = getattr(arch_man, 'aur_client', None)
                info = {}
                if aur_client is not None:
                    try:
                        infos = aur_client.get_info((name,))
                        info = (infos[0] if infos else {}) or {}
                    except Exception as e:
                        self.logger.debug(f"dep summary: AUR get_info failed for {name}: {e}")
                data['direct'] = sorted(set(info.get('Depends') or []))
                # AUR OptDepends are "dep: description" strings; keep them as {name, detail}.
                data['optional'] = [self._split_optdep(o) for o in (info.get('OptDepends') or [])]
                data['makedepends'] = sorted(set(info.get('MakeDepends') or []))
                data['checkdepends'] = sorted(set(info.get('CheckDepends') or []))
                data['conflicts'] = sorted(set(info.get('Conflicts') or []))
                data['replaces'] = sorted(set(info.get('Replaces') or []))
                data['provides'] = sorted(set(info.get('Provides') or []))
                data['note'] = "Direct requirements from the PKGBUILD; pacman/makepkg resolves the full set at build time."
            else:
                try:
                    info = (pacman.map_updates_data([name]) or {}).get(name) or {}
                    data['direct'] = sorted(info.get('d') or [])
                    data['conflicts'] = sorted(info.get('c') or [])
                    data['provides'] = sorted(info.get('p') or [])
                except Exception as e:
                    self.logger.debug(f"dep summary: map_updates_data failed for {name}: {e}")
                try:
                    opt = (pacman.map_optional_deps([name], remote=True, not_installed=False) or {}).get(name) or {}
                    data['optional'] = [{'name': k, 'detail': v or ''} for k, v in sorted(opt.items())]
                except Exception as e:
                    self.logger.debug(f"dep summary: optional deps failed for {name}: {e}")
                try:
                    rep = (pacman.map_conflicts_with([name], remote=True) or {}).get(name) or {}
                    data['replaces'] = sorted(rep.get('r') or [])
                except Exception as e:
                    self.logger.debug(f"dep summary: replaces failed for {name}: {e}")
                # makedepends/checkdepends aren't recorded for binary repo packages (build-time only).
                data['note'] = "Direct requirements; pacman resolves the full set at install time."

            # Reverse deps + "why is this installed?" only make sense for an installed package
            # (both queried from the local db).
            if installed:
                try:
                    req = (pacman.map_required_by([name]) or {}).get(name) or set()
                    data['required_by'] = sorted(req)
                except Exception as e:
                    self.logger.debug(f"dep summary: required_by failed for {name}: {e}")
                try:
                    data['install_reason'] = pacman.get_install_reason(name)
                except Exception as e:
                    self.logger.debug(f"dep summary: install reason failed for {name}: {e}")
                # An orphan candidate: pulled in as a dependency, but now nothing requires it.
                data['orphan'] = data['install_reason'] == 'dependency' and not data['required_by']
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_dependency_summary failed for {pkg_id}: {e}")
            return {'status': 'ok', 'data': data}  # fail open — never block the modal

    def get_subdeps(self, name: str) -> dict:
        """Direct requirements of a single package **by name** — for lazy drill-down in the
        dependency tree. Repo-resolved (one cheap `pacman -Si`); returns ``{direct:[str]}``. Fails
        open → ``{direct:[]}`` (an AUR-only/unknown name or any error → a leaf node, no RPC storm)."""
        try:
            from atlas.gems.arch import pacman
            info = (pacman.map_updates_data([name]) or {}).get(name) or {}
            return {'status': 'ok', 'data': {'direct': sorted(info.get('d') or [])}}
        except Exception as e:
            self.logger.debug(f"get_subdeps failed for {name}: {e}")
            return {'status': 'ok', 'data': {'direct': []}}

    def get_command(self, pkg_id: str, action: str = 'install') -> dict:
        """The equivalent terminal command for a transaction, so nothing feels hidden from CLI users
        ("copy exact command"). Per source/action: pacman for repo, makepkg (or an AUR helper) for
        AUR, flatpak for Flatpak. Returns ``{command, note}`` (`command` '' when there's no clean
        one-liner, e.g. downgrade — the frontend then hides the affordance). Never raises."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            ptype = self._preview_ptype(pkg)
            repository = (getattr(pkg, 'repository', None) or '').lower()
            name = pkg.name or ''
            q = shlex.quote(name)
            command, note = '', ''
            if ptype == 'flatpak':
                app = shlex.quote(getattr(pkg, 'id', None) or name)
                if action == 'uninstall':
                    command = f'flatpak uninstall {app}'
                elif action == 'update':
                    command = f'flatpak update {app}'
                elif action == 'install':
                    command = f'flatpak install flathub {app}'
            elif repository == 'aur' or ptype == 'aur':
                if action == 'uninstall':
                    command = f'sudo pacman -Rns {q}'
                elif action in ('install', 'update'):
                    base = shlex.quote(getattr(pkg, 'package_base', None) or name)
                    command = (f'git clone https://aur.archlinux.org/{base}.git && '
                               f'cd {base} && makepkg -si')
                    note = f'Or with an AUR helper: paru -S {name}'
            else:  # official Arch repositories
                if action == 'uninstall':
                    command = f'sudo pacman -Rns {q}'
                elif action in ('install', 'update'):
                    command = f'sudo pacman -S {q}'
            return {'status': 'ok', 'data': {'command': command, 'note': note}}
        except Exception as e:
            self.logger.error(f"get_command failed for {pkg_id}: {e}")
            return {'status': 'ok', 'data': {'command': '', 'note': ''}}

    @staticmethod
    def _split_optdep(token: str) -> dict:
        """Split an AUR/pacman optdep token 'name: why it's useful' into {name, detail}."""
        s = str(token or '')
        if ':' in s:
            n, d = s.split(':', 1)
            return {'name': n.strip(), 'detail': d.strip()}
        return {'name': s.strip(), 'detail': ''}

    def get_flatpak_meta(self, pkg_id: str) -> dict:
        """Flathub metadata for the detail-view badges (license FOSS/proprietary, developer
        verification, downloads/month). Returns empty data for non-Flatpak packages. Best-effort —
        never raises into the UI."""
        try:
            pkg = self._get_pkg(pkg_id)
            ptype = ''
            try:
                ptype = str(pkg.get_type() or '').lower()
            except Exception:
                pass
            app_id = getattr(pkg, 'id', None)
            if pkg is None or ptype != 'flatpak' or not app_id:
                return {'status': 'ok', 'data': {}}
            flatpak_man = self._manager_by_gem('flatpak')
            if flatpak_man is None or not hasattr(flatpak_man, 'get_flathub_metadata'):
                return {'status': 'ok', 'data': {}}
            return {'status': 'ok', 'data': flatpak_man.get_flathub_metadata(app_id) or {}}
        except Exception as e:
            self.logger.error(f"get_flatpak_meta failed: {e}")
            return {'status': 'ok', 'data': {}}

    def get_flatpak_card_meta(self, pkg_id: str) -> dict:
        """Lightweight Flathub metadata for grid cards. Only fetches verification status."""
        try:
            pkg = self._get_pkg(pkg_id)
            ptype = ''
            try:
                ptype = str(pkg.get_type() or '').lower()
            except Exception:
                pass
            app_id = getattr(pkg, 'id', None)
            if pkg is None or ptype != 'flatpak' or not app_id:
                return {'status': 'ok', 'data': {}}
            flatpak_man = self._manager_by_gem('flatpak')
            if flatpak_man is None or not hasattr(flatpak_man, 'get_flathub_card_metadata'):
                return {'status': 'ok', 'data': {}}
            return {'status': 'ok', 'data': flatpak_man.get_flathub_card_metadata(app_id) or {}}
        except Exception as e:
            self.logger.error(f"get_flatpak_card_meta failed: {e}")
            return {'status': 'ok', 'data': {}}

    def get_aur_meta(self, pkg_id: str) -> dict:
        """On-demand AUR detail-view metadata: current maintainer, whether the maintainer changed
        since install (advisory supply-chain signal), the latest AUR version, and whether an update
        is available (compared with `vercmp`). data: {maintainer, changed:{old,new}|None,
        latest_version, update_available}. Empty for non-AUR. One best-effort RPC; never raises."""
        try:
            pkg = self._get_pkg(pkg_id)
            if pkg is None or getattr(pkg, 'repository', None) != 'aur':
                return {'status': 'ok', 'data': {}}
            arch_man = self._manager_by_gem('arch')
            aur_client = getattr(arch_man, 'aur_client', None)
            if aur_client is None:
                return {'status': 'ok', 'data': {}}
            baseline = getattr(pkg, 'maintainer', None)  # maintainer cached at install (the baseline)
            infos = aur_client.get_info((pkg.name,))
            info = infos[0] if infos else {}
            current = info.get('Maintainer')
            latest = info.get('Version')
            # Only a real change when we have a baseline to compare against (older installs lack one).
            changed = {'old': baseline, 'new': current} if (getattr(pkg, 'installed', False) and baseline and current != baseline) else None

            # Search results don't run the update check, so reflect it here: vercmp installed vs AUR.
            update_available = False
            installed_v = getattr(pkg, 'version', None)
            if getattr(pkg, 'installed', False) and installed_v and latest:
                try:
                    out = run_cmd(f'vercmp {shlex.quote(installed_v)} {shlex.quote(latest)}', print_error=False)
                    update_available = out is not None and int(out.strip()) < 0
                except (ValueError, AttributeError):
                    update_available = False

            return {'status': 'ok', 'data': {'maintainer': current, 'changed': changed,
                                             'latest_version': latest, 'update_available': update_available}}
        except Exception as e:
            self.logger.error(f"get_aur_meta failed: {e}")
            return {'status': 'ok', 'data': {}}

    def get_pkgbuild(self, pkg_id: str) -> dict:
        """On-demand PKGBUILD for the first-class viewer (AUR only). Fetches the current published
        PKGBUILD from AUR's cgit, runs the advisory heuristic scan, and parses metadata. Shape:
        ``{text, findings, summary, metadata, base, url, disclaimer}``. Non-AUR → ``{}`` + note.
        Fails open (any failure → ``{}``); never raises into the UI — it's advisory, not a gate."""
        try:
            pkg = self._get_pkg(pkg_id)
            if pkg is None or getattr(pkg, 'repository', None) != 'aur':
                return {'status': 'ok', 'data': {}}
            from atlas.gems.arch import pkgbuild, pkgbuild_audit
            arch_man = self._manager_by_gem('arch')
            if arch_man is None or not hasattr(arch_man, 'fetch_pkgbuild'):
                return {'status': 'ok', 'data': {}}

            # The PKGBUILD lives under the package *base*, not the package name (split packages share
            # one). Resolve it cheaply; fall back to the package name.
            base = getattr(pkg, 'base', None) or pkg.name
            aur_client = getattr(arch_man, 'aur_client', None)
            if aur_client is not None:
                try:
                    infos = aur_client.get_info((pkg.name,))
                    info = (infos[0] if infos else {}) or {}
                    base = info.get('PackageBase') or base
                except Exception as e:
                    self.logger.debug(f"get_pkgbuild: base lookup failed for {pkg.name}: {e}")

            text = arch_man.fetch_pkgbuild(base)
            if not text:
                return {'status': 'ok', 'data': {}}

            findings = list(pkgbuild_audit.scan(text))
            url = f'https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h={base}'

            # The PKGBUILD is the primary file; .install scriptlets (which run as root on install/
            # upgrade/remove) get their own tab. Best-effort: a scriptlet that 404s is skipped.
            files = [{'name': 'PKGBUILD', 'text': text, 'findings': findings}]
            all_findings = list(findings)
            for fname in pkgbuild.parse_install_files(text, base):
                ftext = None
                try:
                    ftext = arch_man.fetch_aur_file(base, fname)
                except Exception as e:
                    self.logger.debug(f"get_pkgbuild: could not fetch '{fname}': {e}")
                if not ftext:
                    continue
                ffindings = list(pkgbuild_audit.scan(ftext))
                files.append({'name': fname, 'text': ftext, 'findings': ffindings})
                all_findings.extend(ffindings)

            # "Changed since your build" — for an installed AUR package whose built commit we cached,
            # diff the PKGBUILD you built against the current published one (the compromised-release
            # signal). Best-effort: no baseline / unchanged / fetch failure → empty.
            diff = []
            commit = getattr(pkg, 'commit', None)
            if getattr(pkg, 'installed', False) and commit:
                try:
                    old_text = arch_man.fetch_aur_file(base, 'PKGBUILD', commit)
                    if old_text and old_text != text:
                        diff = pkgbuild_audit.diff_lines(old_text, text)
                except Exception as e:
                    self.logger.debug(f"get_pkgbuild: diff vs commit {commit} failed: {e}")

            return {'status': 'ok', 'data': {
                'text': text,
                'findings': findings,
                'files': files,
                'diff': diff,
                'summary': pkgbuild_audit.summarize(all_findings),  # combined across PKGBUILD + .install
                'metadata': pkgbuild.parse_metadata(text),
                'base': base,
                'url': url,
                'disclaimer': pkgbuild_audit.DISCLAIMER,
            }}
        except Exception as e:
            self.logger.error(f"get_pkgbuild failed: {e}")
            return {'status': 'ok', 'data': {}}

    # ---- Transaction preview (pre-flight) ------------------------------------------------
    # A "here's what will happen — proceed?" summary shown before an install. Increment 1 of the
    # universal transaction preview (see docs/plans/2026-06-04-transaction-preview.md). Shows only
    # what's cheaply knowable up front (direct deps + cheap size/badges) — pacman/makepkg resolves
    # the full dependency set at install time. Fails open per field so a failed probe never blocks.

    def _source_label(self, pkg, ptype: str) -> str:
        repository = (getattr(pkg, 'repository', None) or '')
        if ptype == 'flatpak':
            return 'Flatpak'
        if repository.lower() == 'aur':
            return 'AUR'
        if ptype == 'appimage':
            return 'AppImage'
        if repository and repository.lower() != 'aur':
            return f'Arch · {repository}'
        return 'Arch'

    def _preview_ptype(self, pkg) -> str:
        try:
            return str(pkg.get_type() or pkg.gem_name or '').lower()
        except Exception:
            return str(getattr(pkg, 'gem_name', '') or '').lower()

    def _preview_base(self, pkg, ptype: str, action: str, version) -> dict:
        """The common transaction-preview envelope shared by install / uninstall / downgrade.
        The frontend keys the modal title, description, proceed button, and size-row label off
        `action`; the rest of the payload is filled per-source/per-action by the callers."""
        return {
            'action': action,
            'name': pkg.name or '',
            'source': ptype,
            'source_label': self._source_label(pkg, ptype),
            'version': version or '',
            'sizes': None,
            'deps': {'direct': [], 'optional': []},
            'permissions': None,
            'warnings': [],
            'notes': [],
        }

    def get_install_preview(self, pkg_id: str) -> dict:
        """Pre-flight summary for an install: source, version, a size estimate, direct + optional
        dependencies, and advisory warnings (AUR community/maintainer/PKGBUILD, Flatpak permissions/
        verification). The full dependency set is resolved by pacman/makepkg at install time — this
        shows only what's cheaply knowable up front. Fails open per field (a failed probe → None/[]
        + a note), never blocks the install. Shape:
            {action, name, source, source_label, version, sizes:{download,installed}|None,
             deps:{direct:[str], optional:[{name,detail}]}, permissions:[{title,detail,level}]|None,
             warnings:[{level,title,detail}], notes:[str]}"""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            return {'status': 'ok', 'data': self._assemble_acquire_preview(pkg, 'install')}
        except Exception as e:
            self.logger.error(f"get_install_preview failed: {e}")
            traceback.print_exc()
            # Fail open: a minimal payload still lets the user confirm.
            return {'status': 'ok', 'data': self._preview_failopen(pkg, 'install')}

    def get_update_preview(self, pkg_id: str) -> dict:
        """Pre-flight summary for updating a single package: current → new version, the update's
        download size, and the same per-source advisories as install (AUR maintainer change /
        out-of-date / community, Flatpak permissions). Reuses the install assembler — an update is an
        acquire of a newer version — and adds `from_version`. Fails open, never blocks."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            data = self._assemble_acquire_preview(pkg, 'update')
            data['from_version'] = getattr(pkg, 'version', None) or ''
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_update_preview failed: {e}")
            traceback.print_exc()
            return {'status': 'ok', 'data': self._preview_failopen(pkg, 'update')}

    def _assemble_acquire_preview(self, pkg, action: str) -> dict:
        """Shared assembler for the install/update preview (both acquire a package version). Picks the
        per-source filler; each fails open per field. Raises only on a top-level error (caller fails
        open)."""
        ptype = self._preview_ptype(pkg)
        version = getattr(pkg, 'latest_version', None) or getattr(pkg, 'version', None) or ''
        data = self._preview_base(pkg, ptype, action, version)
        repository = (getattr(pkg, 'repository', None) or '').lower()
        if ptype == 'flatpak':
            self._preview_flatpak(pkg, data)
        elif repository == 'aur' or ptype == 'aur':
            self._preview_aur(pkg, data)
        elif repository or ptype in ('arch', 'arch_repo'):
            self._preview_arch_repo(pkg, data)
        else:
            data['notes'].append("Details for this source aren't available beforehand.")
        return data

    def _preview_failopen(self, pkg, action: str) -> dict:
        """Minimal payload returned when preview assembly raises — never blocks the action."""
        return {
            'action': action, 'name': getattr(pkg, 'name', ''), 'source': '', 'source_label': '',
            'version': getattr(pkg, 'version', '') or '', 'sizes': None,
            'deps': {'direct': [], 'optional': []}, 'permissions': None, 'warnings': [],
            'notes': ["Couldn't gather full details for this package; proceed with care."]}

    def _preview_arch_repo(self, pkg, data: dict) -> None:
        from atlas.gems.arch import pacman
        name = pkg.name
        try:
            info = (pacman.map_updates_data([name]) or {}).get(name) or {}
        except Exception as e:
            self.logger.debug(f"preview: map_updates_data failed for {name}: {e}")
            info = {}
        if info.get('v'):
            data['version'] = info['v']
        ds, s = info.get('ds'), info.get('s')
        if ds is not None or s is not None:
            data['sizes'] = {'download': ds, 'installed': s}
        else:
            data['notes'].append("Size estimate unavailable.")
        deps = info.get('d')
        if deps:
            data['deps']['direct'] = sorted(deps)
        try:
            opt = (pacman.map_optional_deps([name], remote=True, not_installed=False) or {}).get(name) or {}
            data['deps']['optional'] = [{'name': k, 'detail': v or ''} for k, v in sorted(opt.items())]
        except Exception as e:
            self.logger.debug(f"preview: optional deps failed for {name}: {e}")
        data['notes'].append("Dependencies shown are direct requirements; pacman resolves the full set at install time.")

    def _preview_aur(self, pkg, data: dict) -> None:
        arch_man = self._manager_by_gem('arch')
        aur_client = getattr(arch_man, 'aur_client', None)
        info = {}
        if aur_client is not None:
            try:
                infos = aur_client.get_info((pkg.name,))
                info = (infos[0] if infos else {}) or {}
            except Exception as e:
                self.logger.debug(f"preview: AUR get_info failed for {pkg.name}: {e}")
        if info.get('Version'):
            data['version'] = info['Version']
        deps = info.get('Depends') or []
        if deps:
            data['deps']['direct'] = sorted(set(deps))
        makedeps = info.get('MakeDepends') or []
        if makedeps:
            data['notes'].append("Build-time dependencies: " + ", ".join(sorted(set(makedeps))) + ".")
        data['notes'].append("AUR packages are built from source — download/install size isn't known until the build runs.")
        data['notes'].append("Dependencies are the PKGBUILD's direct requires; the full set is resolved at build time.")

        maintainer = info.get('Maintainer')
        baseline = getattr(pkg, 'maintainer', None)
        if aur_client is not None and maintainer is None:
            data['warnings'].append({'level': 'warn', 'title': 'Orphaned package',
                                     'detail': 'This AUR package currently has no maintainer.'})
        if getattr(pkg, 'installed', False) and baseline and maintainer and maintainer != baseline:
            data['warnings'].append({'level': 'warn', 'title': 'Maintainer changed',
                                     'detail': f'Maintainer changed since you installed: {baseline} → {maintainer}.'})
        if info.get('OutOfDate'):
            data['warnings'].append({'level': 'warn', 'title': 'Flagged out of date',
                                     'detail': 'The AUR community has flagged this package out of date.'})
        data['warnings'].append({'level': 'info', 'title': 'Community-maintained (AUR)',
                                 'detail': 'AUR packages are user-submitted and not vetted by Arch. Atlas scans the PKGBUILD before building.'})

    def _preview_flatpak(self, pkg, data: dict) -> None:
        app_id = getattr(pkg, 'id', None)
        flatpak_man = self._manager_by_gem('flatpak')
        badges = {}
        if app_id and flatpak_man is not None and hasattr(flatpak_man, 'get_flathub_metadata'):
            try:
                badges = flatpak_man.get_flathub_metadata(app_id) or {}
            except Exception as e:
                self.logger.debug(f"preview: Flathub metadata failed for {app_id}: {e}")
        ds, s = getattr(pkg, 'download_size', None), getattr(pkg, 'size', None)
        if ds is not None or s is not None:
            data['sizes'] = {'download': ds, 'installed': s}
        perms = badges.get('permissions')
        if perms:
            data['permissions'] = perms
        tier = (badges.get('safety') or {}).get('level')
        if tier == 'unsafe':
            data['warnings'].append({'level': 'danger', 'title': 'Potentially unsafe permissions',
                                     'detail': 'This app requests broad access (filesystem, devices, or session bus). Review the permissions below.'})
        elif tier == 'moderate':
            data['warnings'].append({'level': 'warn', 'title': 'Some sensitive permissions',
                                     'detail': 'This app requests a few sensitive permissions. Review them below.'})
        if badges.get('is_free') is False:
            data['warnings'].append({'level': 'info', 'title': 'Proprietary',
                                     'detail': 'This app uses a proprietary (non-free) license.'})
        if badges.get('verified') is False:
            data['warnings'].append({'level': 'info', 'title': 'Unverified on Flathub',
                                     'detail': 'Not published by the original developer (community-packaged).'})
        data['notes'].append("Flatpak permissions can be adjusted after install on the Permissions page.")

    def get_uninstall_preview(self, pkg_id: str) -> dict:
        """Pre-flight summary for an uninstall: what depends on this package (the safety signal),
        the disk space it would free, and an orphan-cleanup note. Reuses pacman's cheap `Required By`
        + installed-size fields; no transitive removal simulation. Fails open, never blocks."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            ptype = self._preview_ptype(pkg)
            data = self._preview_base(pkg, ptype, 'uninstall', getattr(pkg, 'version', None))
            repository = (getattr(pkg, 'repository', None) or '').lower()
            if ptype == 'flatpak':
                s = getattr(pkg, 'size', None)
                if s is not None:
                    data['sizes'] = {'download': None, 'installed': s}
                data['notes'].append("Runtimes pulled in only for this app can be reclaimed later from System Health.")
            elif repository or ptype in ('arch', 'arch_repo', 'aur'):
                self._preview_uninstall_arch(pkg, data)
            else:
                data['notes'].append("Details for this source aren't available before removal.")
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_uninstall_preview failed: {e}")
            traceback.print_exc()
            return {'status': 'ok', 'data': self._preview_failopen(pkg, 'uninstall')}

    def _preview_uninstall_arch(self, pkg, data: dict) -> None:
        from atlas.gems.arch import pacman
        name = pkg.name
        try:
            s = (pacman.get_installed_size([name]) or {}).get(name)
            if s:
                data['sizes'] = {'download': None, 'installed': s}
        except Exception as e:
            self.logger.debug(f"preview: installed size failed for {name}: {e}")
        try:
            req_by = (pacman.map_required_by([name]) or {}).get(name) or set()
        except Exception as e:
            self.logger.debug(f"preview: required-by failed for {name}: {e}")
            req_by = None
        if req_by:
            ordered = sorted(req_by)
            listed = ", ".join(ordered[:12])
            more = "" if len(ordered) <= 12 else f" (+{len(ordered) - 12} more)"
            n = len(ordered)
            data['warnings'].append({'level': 'danger',
                                     'title': f"{n} installed package{'s' if n != 1 else ''} depend on this",
                                     'detail': f"Removing it may also remove or break: {listed}{more}."})
        elif req_by is not None:
            data['notes'].append("Nothing else installed depends on this package.")
        data['notes'].append("Dependencies installed only for this package may be left as orphans — clean them up later from System Health.")

    def get_downgrade_preview(self, pkg_id: str) -> dict:
        """Pre-flight summary for a downgrade. The target version is chosen interactively by the gem
        afterward (and isn't cheaply knowable up front), so this is advisory: the current version plus
        what rolling back implies. Fails open, never blocks."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            ptype = self._preview_ptype(pkg)
            data = self._preview_base(pkg, ptype, 'downgrade', getattr(pkg, 'version', None))
            data['warnings'].append({'level': 'warn', 'title': 'Rolling back a version',
                                     'detail': 'Downgrading can reintroduce bugs or security issues that the newer version fixed.'})
            data['notes'].append("You'll choose which previous version to roll back to next.")
            data['notes'].append("Dependencies are not downgraded automatically; the older version may expect different dependency versions.")
            if (getattr(pkg, 'repository', None) or '').lower() == 'aur':
                data['notes'].append("AUR downgrades rebuild the package from its previous source.")
            return {'status': 'ok', 'data': data}
        except Exception as e:
            self.logger.error(f"get_downgrade_preview failed: {e}")
            traceback.print_exc()
            return {'status': 'ok', 'data': self._preview_failopen(pkg, 'downgrade')}

    def _flatpak_pkg_and_manager(self, pkg_id: str):
        """(pkg, flatpak_manager) for an installed Flatpak, else (None, None)."""
        pkg = self._get_pkg(pkg_id)
        try:
            ptype = str(pkg.get_type() or '').lower()
        except Exception:
            ptype = ''
        if pkg is None or ptype != 'flatpak':
            return None, None
        man = self._manager_by_gem('flatpak')
        return (pkg, man) if man is not None else (None, None)

    def get_flatpak_overrides(self, pkg_id: str) -> dict:
        """Editable Flatseal-style permission toggles for an installed Flatpak. Non-installed /
        non-Flatpak → editable:false."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man or not hasattr(man, 'get_permission_toggles'):
                return {'status': 'ok', 'data': {'editable': False, 'toggles': []}}
            return {'status': 'ok', 'data': man.get_permission_toggles(pkg)}
        except Exception as e:
            self.logger.error(f"get_flatpak_overrides failed: {e}")
            return {'status': 'ok', 'data': {'editable': False, 'toggles': []}}

    def get_flatpak_grouped_permissions(self, pkg_id: str) -> dict:
        """Full grouped permission toggles (Flatseal-style) for the dedicated Permissions page."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man or not hasattr(man, 'get_grouped_permissions'):
                return {'status': 'ok', 'data': {'editable': False, 'groups': []}}
            return {'status': 'ok', 'data': man.get_grouped_permissions(pkg)}
        except Exception as e:
            self.logger.error(f"get_flatpak_grouped_permissions failed: {e}")
            return {'status': 'ok', 'data': {'editable': False, 'groups': []}}

    def set_flatpak_override(self, pkg_id: str, key: str, enabled: bool) -> dict:
        """Toggle one permission via `flatpak override --user` (no root)."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man:
                return {'status': 'error', 'message': 'Not a Flatpak package'}
            ok = man.set_permission(pkg, key, bool(enabled))
            return {'status': 'ok'} if ok else {'status': 'error', 'message': 'Could not apply the permission change'}
        except Exception as e:
            self.logger.error(f"set_flatpak_override failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def set_flatpak_filesystem(self, pkg_id: str, name: str, enabled: bool, mode: str = 'rw') -> dict:
        """Add/remove/re-mode a filesystem override for an installed Flatpak (no root)."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man or not hasattr(man, 'set_filesystem_permission'):
                return {'status': 'error', 'message': 'Not a Flatpak package'}
            ok = man.set_filesystem_permission(pkg, name, bool(enabled), mode or 'rw')
            return {'status': 'ok'} if ok else {'status': 'error', 'message': 'Could not apply the filesystem change'}
        except Exception as e:
            self.logger.error(f"set_flatpak_filesystem failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def set_flatpak_bus(self, pkg_id: str, scope: str, name: str, policy: str, enabled: bool) -> dict:
        """Add/remove a D-Bus name grant (session or system bus) for an installed Flatpak (no root)."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man or not hasattr(man, 'set_bus_permission'):
                return {'status': 'error', 'message': 'Not a Flatpak package'}
            ok = man.set_bus_permission(pkg, scope, name, policy, bool(enabled))
            return {'status': 'ok'} if ok else {'status': 'error', 'message': 'Could not apply the bus change'}
        except Exception as e:
            self.logger.error(f"set_flatpak_bus failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def set_flatpak_env(self, pkg_id: str, var: str, value: str, enabled: bool) -> dict:
        """Set/remove an environment-variable override for an installed Flatpak (no root)."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man or not hasattr(man, 'set_env_permission'):
                return {'status': 'error', 'message': 'Not a Flatpak package'}
            ok = man.set_env_permission(pkg, var, value or '', bool(enabled))
            return {'status': 'ok'} if ok else {'status': 'error', 'message': 'Could not apply the variable change'}
        except Exception as e:
            self.logger.error(f"set_flatpak_env failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def reset_flatpak_overrides(self, pkg_id: str) -> dict:
        """Clear all user permission overrides for an installed Flatpak."""
        try:
            pkg, man = self._flatpak_pkg_and_manager(pkg_id)
            if not man:
                return {'status': 'error', 'message': 'Not a Flatpak package'}
            ok = man.reset_permissions(pkg)
            return {'status': 'ok'} if ok else {'status': 'error', 'message': 'Could not reset permissions'}
        except Exception as e:
            self.logger.error(f"reset_flatpak_overrides failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_screenshots(self, pkg_id: str) -> dict:
        """Screenshot URLs for the detail modal (Flatpak/AppImage have them; Arch doesn't).
        Returns {status, data:[url, ...]}; an empty list is a valid 'ok' result."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            urls = [u for u in (self.manager.get_screenshots(pkg) or ()) if u]
            return {'status': 'ok', 'data': urls}
        except Exception as e:
            self.logger.error(f"Error getting screenshots for {pkg.name}: {e}")
            return {'status': 'error', 'message': str(e), 'data': []}

    def get_history(self, pkg_id: str) -> dict:
        """Version history for the detail modal. Returns
        {status, data:{history:[{...}], current_index:int}}; current_index marks the
        installed version (-1 if unknown)."""
        pkg = self._get_pkg(pkg_id)
        if not pkg:
            return {'status': 'error', 'message': f"Unknown package id: {pkg_id}"}
        try:
            hist = self.manager.get_history(pkg)
            entries = _json_safe(getattr(hist, 'history', None) or [])
            current = getattr(hist, 'pkg_status_idx', -1)
            return {'status': 'ok', 'data': {'history': entries, 'current_index': current}}
        except Exception as e:
            self.logger.error(f"Error getting history for {pkg.name}: {e}")
            return {'status': 'error', 'message': str(e), 'data': {'history': [], 'current_index': -1}}

    def open_url(self, url: str) -> dict:
        """Open an external URL in the user's browser. Routed through Python because a
        plain link would navigate the pywebview window instead. Only http(s) is allowed."""
        if not isinstance(url, str):
            return {'status': 'error', 'message': 'Invalid URL'}

        if re.search(r'[\x00-\x20\x7f]', url):
            return {'status': 'error', 'message': 'Invalid URL'}

        try:
            parsed = urlsplit(url)
        except Exception:
            return {'status': 'error', 'message': 'Invalid URL'}

        if parsed.scheme.lower() not in {'http', 'https'} or not parsed.netloc:
            return {'status': 'error', 'message': 'Invalid URL'}

        try:
            webbrowser.open(url)
            return {'status': 'ok'}
        except Exception as e:
            self.logger.error(f"Could not open URL '{url}': {e}")
            return {'status': 'error', 'message': str(e)}

    def _notify(self, message: str):
        """Fire a desktop notification for a finished operation, if the user has enabled
        system notifications. Never let a notification failure affect the operation."""
        try:
            if not self.manager.configman.get_config()['system']['notifications']:
                return
            from atlas.view.util.util import notify_user
            notify_user(message)
        except Exception:
            self.logger.debug("Desktop notification failed", exc_info=True)

    # ------------------------------------------------------------------ #
    # Settings (focused, webview-native — see plans/2026-06-01-webview-settings.md)
    # ------------------------------------------------------------------ #
    _TYPE_LABELS = {'arch': 'Arch & AUR', 'flatpak': 'Flatpak', 'appimage': 'AppImage',
                    'snap': 'Snap', 'debian': 'Debian', 'web': 'Web apps'}

    @staticmethod
    def _gem_name(man) -> str:
        return man.__module__.split('.')[-2]

    def _manager_by_gem(self, gem: str):
        for man in getattr(self.manager, 'managers', []) or []:
            if self._gem_name(man) == gem:
                return man
        return None

    def get_app_settings(self) -> dict:
        """Current settings for the webview Settings page: which package types are enabled
        (with whether each can work on this system), the Flatpak install level, and a few
        general toggles — read straight from the config managers."""
        try:
            core = self.manager.configman.get_config()
            types = []
            for man in getattr(self.manager, 'managers', []) or []:
                gem = self._gem_name(man)
                try:
                    can_work = bool(man.can_work()[0])
                except Exception:
                    can_work = False
                types.append({'id': gem,
                              'label': self._TYPE_LABELS.get(gem, gem.capitalize()),
                              'enabled': bool(man.is_enabled()),
                              'can_work': can_work})
            types.sort(key=lambda t: t['label'].lower())

            flatpak_man = self._manager_by_gem('flatpak')
            flatpak_level = ''
            if flatpak_man is not None:
                try:
                    flatpak_level = flatpak_man.configman.get_config().get('installation_level') or ''
                except Exception:
                    flatpak_level = ''

            tray_cfg = (core.get('ui') or {}).get('tray') or {}
            try:
                from atlas.view.tray import TRAY_AVAILABLE
            except Exception:
                TRAY_AVAILABLE = False

            arch_man = self._manager_by_gem('arch')
            arch_check_pkgbuild = True
            arch_build_chroot = False
            arch_chroot_available = False
            if arch_man is not None:
                try:
                    aconf = arch_man.configman.get_config()
                    arch_check_pkgbuild = bool(aconf.get('aur_check_pkgbuild', True))
                    arch_build_chroot = bool(aconf.get('aur_build_chroot', False))
                except Exception:
                    arch_check_pkgbuild = True
                try:
                    from atlas.gems.arch import chroot
                    arch_chroot_available = chroot.available()
                except Exception:
                    arch_chroot_available = False

            return {'status': 'ok', 'data': {
                'types': types,
                'flatpak_available': flatpak_man is not None,
                'flatpak_installation_level': flatpak_level,
                'general': {
                    'suggestions_enabled': bool(core['suggestions']['enabled']),
                    'system_notifications': bool(core['system']['notifications']),
                    'ask_for_reboot': bool(core['updates']['ask_for_reboot']),
                    'download_icons': bool(core['download']['icons']),
                    'store_root_password': bool(core['store_root_password']),
                    'greeting_name': (core.get('ui') or {}).get('greeting_name') or '',
                },
                'tray': {
                    'available': bool(TRAY_AVAILABLE),
                    'enabled': bool(tray_cfg.get('enabled', True)),
                    'minimize_to_tray': bool(tray_cfg.get('minimize_to_tray', False)),
                    'update_check_interval': int(tray_cfg.get('update_check_interval', 60) or 0),
                },
                'arch': {
                    'available': arch_man is not None,
                    'check_pkgbuild': arch_check_pkgbuild,
                    'build_chroot': arch_build_chroot,
                    'chroot_available': arch_chroot_available,
                    'mirror_tool': (self._mirror_regen_cmd() or [None])[0],
                },
            }}
        except Exception as e:
            self.logger.error(f"Error reading settings: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def save_app_settings(self, settings: dict) -> dict:
        """Persist the focused settings. Enabled package types are written to the core
        config's `gems` list and applied live (set_enabled) so the change takes effect
        without a restart; Flatpak install level + general toggles are written to their
        config files."""
        try:
            settings = settings or {}
            core = self.manager.configman.get_config()
            managers = getattr(self.manager, 'managers', []) or []

            # Package types -> core_config['gems'] (list of enabled gem dir names) + live apply.
            type_states = settings.get('types')
            if isinstance(type_states, dict):
                enabled = sorted([gem for gem, on in type_states.items() if on])
                core['gems'] = enabled
                for man in managers:
                    man.set_enabled(self._gem_name(man) in enabled)

            general = settings.get('general') or {}
            if 'suggestions_enabled' in general:
                core['suggestions']['enabled'] = bool(general['suggestions_enabled'])
            if 'system_notifications' in general:
                core['system']['notifications'] = bool(general['system_notifications'])
            if 'ask_for_reboot' in general:
                core['updates']['ask_for_reboot'] = bool(general['ask_for_reboot'])
            if 'download_icons' in general:
                core['download']['icons'] = bool(general['download_icons'])
            if 'store_root_password' in general:
                core['store_root_password'] = bool(general['store_root_password'])
            if 'greeting_name' in general:
                # Custom name for the dashboard greeting; '' clears it (falls back to the OS name).
                name = (general.get('greeting_name') or '').strip()[:40]
                core.setdefault('ui', {})['greeting_name'] = name

            # System tray (takes effect on next launch — the indicator is built at startup).
            tray = settings.get('tray')
            if isinstance(tray, dict):
                ui_tray = core.setdefault('ui', {}).setdefault('tray', {})
                if 'enabled' in tray:
                    ui_tray['enabled'] = bool(tray['enabled'])
                if 'minimize_to_tray' in tray:
                    ui_tray['minimize_to_tray'] = bool(tray['minimize_to_tray'])
                if 'update_check_interval' in tray:
                    try:
                        ui_tray['update_check_interval'] = max(0, int(tray['update_check_interval']))
                    except (TypeError, ValueError):
                        pass

            self.manager.configman.save_config(core)

            if 'flatpak_installation_level' in settings:
                flatpak_man = self._manager_by_gem('flatpak')
                if flatpak_man is not None:
                    fconf = flatpak_man.configman.get_config()
                    level = settings.get('flatpak_installation_level') or None
                    fconf['installation_level'] = level if level in ('system', 'user') else None
                    flatpak_man.configman.save_config(fconf)

            arch = settings.get('arch')
            if isinstance(arch, dict) and ('check_pkgbuild' in arch or 'build_chroot' in arch):
                arch_man = self._manager_by_gem('arch')
                if arch_man is not None:
                    aconf = arch_man.configman.get_config()
                    if 'check_pkgbuild' in arch:
                        aconf['aur_check_pkgbuild'] = bool(arch['check_pkgbuild'])
                    if 'build_chroot' in arch:
                        aconf['aur_build_chroot'] = bool(arch['build_chroot'])
                    arch_man.configman.save_config(aconf)

            return {'status': 'ok'}
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def batch_uninstall(self, pkg_ids: List[str]) -> dict:
        try:
            self.logger.info(f"Batch uninstall triggered for packages: {pkg_ids}")
            pkgs = []
            for pid in pkg_ids:
                p = self._get_pkg(pid)
                if p:
                    pkgs.append(p)
            
            if not pkgs:
                return {'status': 'error', 'message': 'No valid packages specified for uninstall'}
                
            self.logger.info(f"Prepared batch uninstall for: {[p.name for p in pkgs]}")

            # Acquire a password if any of the selected packages needs root; cache covers the rest.
            root_password = None
            for pkg in pkgs:
                proceed, pwd = self.acquire_root_password(SoftwareAction.UNINSTALL, pkg)
                if not proceed:
                    self.logger.info("Batch uninstall cancelled (no root password)")
                    return {'status': 'cancelled'}
                if pwd is not None:
                    root_password = pwd
                    break

            watcher = WebviewWatcher(self.logger, self.window, self)

            success = True
            for idx, pkg in enumerate(pkgs):
                if self.window:
                    self.window.evaluate_js(f"terminalOpen('Uninstalling {pkg.name} ({idx+1}/{len(pkgs)})')")
                
                res = self.manager.uninstall(pkg, root_password=root_password, handler=watcher)
                pkg_success = res.success if res else False
                
                # Record individual activity
                record_activity('uninstall', pkg.name, pkg.get_type() or pkg.gem_name, pkg_success)
                
                if not pkg_success:
                    self.logger.error(f"Failed to uninstall {pkg.name}")
                    success = False
                    break
                    
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")

            self._notify(f"Uninstalled {len(pkgs)} package(s)" if success else "Batch uninstall failed")

            return {'status': 'ok', 'success': success}
        except Exception as e:
            self.logger.error(f"Error in batch uninstall: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            return {'status': 'error', 'message': str(e)}

    def batch_install(self, pkg_ids: List[str]) -> dict:
        try:
            self.logger.info(f"Batch install triggered for packages: {pkg_ids}")
            pkgs = []
            for pid in pkg_ids:
                p = self._get_pkg(pid)
                if p:
                    pkgs.append(p)
            
            if not pkgs:
                return {'status': 'error', 'message': 'No valid packages specified for install'}
                
            self.logger.info(f"Prepared batch install for: {[p.name for p in pkgs]}")

            # Acquire a password if any of the selected packages needs root; cache covers the rest.
            root_password = None
            for pkg in pkgs:
                proceed, pwd = self.acquire_root_password(SoftwareAction.INSTALL, pkg)
                if not proceed:
                    self.logger.info("Batch install cancelled (no root password)")
                    return {'status': 'cancelled'}
                if pwd is not None:
                    root_password = pwd
                    break

            watcher = WebviewWatcher(self.logger, self.window, self)

            success = True
            for idx, pkg in enumerate(pkgs):
                if self.window:
                    self.window.evaluate_js(f"terminalOpen('Installing {pkg.name} ({idx+1}/{len(pkgs)})')")
                
                res = self.manager.install(pkg, root_password=root_password, disk_loader=None, handler=watcher)
                pkg_success = res.success if res else False
                
                # Record individual activity
                record_activity('install', pkg.name, pkg.get_type() or pkg.gem_name, pkg_success)
                
                if not pkg_success:
                    self.logger.error(f"Failed to install {pkg.name}")
                    success = False
                    break
                    
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")

            self._notify(f"Installed {len(pkgs)} package(s)" if success else "Batch install failed")

            return {'status': 'ok', 'success': success}
        except Exception as e:
            self.logger.error(f"Error in batch install: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            return {'status': 'error', 'message': str(e)}

    def update_all(self) -> dict:
        try:
            self.logger.info("Update All triggered")
            if self.window:
                self.window.evaluate_js("terminalOpen('Checking for system updates...')")
            
            watcher = WebviewWatcher(self.logger, self.window, self)
            installed_res = self.manager.read_installed()
            upgradable = [p for p in (installed_res.installed or []) if p.update]

            if not upgradable:
                self.logger.info("No updates available.")
                if self.window:
                    self.window.evaluate_js("terminalSetStatus('No updates available')")
                    self.window.evaluate_js("terminalSetDone(true)")
                return {'status': 'ok', 'success': True, 'message': 'No updates available'}

            # Acquire a password if any upgradable package needs root; cache covers the rest.
            root_password = None
            for pkg in upgradable:
                proceed, pwd = self.acquire_root_password(SoftwareAction.UPGRADE, pkg)
                if not proceed:
                    self.logger.info("Update All cancelled (no root password)")
                    if self.window:
                        self.window.evaluate_js("terminalSetDone(false)")
                    return {'status': 'cancelled'}
                if pwd is not None:
                    root_password = pwd
                    break

            self.logger.info(f"Found {len(upgradable)} packages to upgrade: {[p.name for p in upgradable]}")
            if self.window:
                self.window.evaluate_js(f"terminalSetStatus('Upgrading {len(upgradable)} packages...')")

            reqs = self.manager.get_upgrade_requirements(upgradable, root_password=root_password, watcher=watcher)
            success = self.manager.upgrade(reqs, root_password=root_password, handler=watcher)
            
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(bool(success)).lower()})")
            
            # Record activity for the bulk operation
            record_activity('update_all', f"{len(upgradable)} packages", 'system', bool(success))
            self._notify("System upgrade finished" if success else "System upgrade failed")

            return {'status': 'ok', 'success': bool(success)}
        except Exception as e:
            self.logger.error(f"Error in Update All: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('update_all', "System updates", 'system', False, str(e))
            return {'status': 'error', 'message': str(e)}

    def get_activity(self) -> dict:
        try:
            # A wider window than the dashboard card needs: the Activity page filters/groups this
            # client-side, so give it enough history to be useful (the JSONL is tiny).
            logs = get_activity_log(limit=200)
            return {'status': 'ok', 'data': logs}
        except Exception as e:
            self.logger.error(f"Error fetching activity log: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_pacman_log(self, pkg_name: str) -> dict:
        """The matching `/var/log/pacman.log` transaction lines for a package (newest first), so an
        Arch/AUR activity entry can show what pacman actually recorded. Fails open (no log / not
        readable / non-Arch system → empty); the file is world-readable, so no root is needed."""
        try:
            if not pkg_name or not os.path.exists(PACMAN_LOG):
                return {'status': 'ok', 'data': []}
            with open(PACMAN_LOG, 'r', encoding='utf-8', errors='replace') as f:
                entries = parse_pacman_log(f.read(), pkg_name)
            return {'status': 'ok', 'data': entries}
        except Exception as e:
            self.logger.error(f"Error reading pacman log for {pkg_name}: {e}")
            return {'status': 'ok', 'data': []}

    def get_disk_usage(self) -> dict:
        try:
            self.logger.info("get_disk_usage called")

            result = self.manager.read_installed()
            pkgs = result.installed or []
            self.manager.fill_sizes(pkgs)

            pkg_sizes = []
            by_type = {}

            with self._registry_lock:
                for pkg in pkgs:
                    self.pkg_registry[self._get_pkg_id(pkg)] = pkg

            for pkg in pkgs:
                pkg_id = self._get_pkg_id(pkg)


                try:
                    pkg_type = pkg.get_type() or pkg.gem_name
                except Exception:
                    pkg_type = pkg.gem_name or 'unknown'

                size_bytes = pkg.size if pkg.size is not None else 0
                size_human = get_human_size_str(size_bytes) or '0 B'

                pkg_sizes.append({
                    'id': pkg_id,
                    'name': pkg.name or '',
                    'type': pkg_type,
                    'size_bytes': size_bytes,
                    'size_human': size_human,
                })

                by_type[pkg_type] = by_type.get(pkg_type, 0) + size_bytes

            # Sort packages descending by size in bytes
            pkg_sizes.sort(key=lambda p: p['size_bytes'], reverse=True)

            # Sort package types descending by total bytes
            type_summary = []
            for t, total_bytes in by_type.items():
                type_summary.append({
                    'type': t,
                    'total_bytes': total_bytes,
                    'total_human': get_human_size_str(total_bytes) or '0 B'
                })
            type_summary.sort(key=lambda x: x['total_bytes'], reverse=True)

            return {
                'status': 'ok',
                'data': {
                    'packages': pkg_sizes,
                    'by_type': type_summary
                }
            }
        except Exception as e:
            self.logger.error(f"Error fetching disk usage: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def export_packages(self) -> dict:
        try:
            self.logger.info("export_packages called")
            result = self.manager.read_installed()
            pkgs = result.installed or []
            serialized_packages = [self._serialize_pkg(p) for p in pkgs]
            path = write_manifest(serialized_packages)
            return {'status': 'ok', 'data': {'path': path, 'count': len(serialized_packages)}}
        except Exception as e:
            self.logger.error(f"Error exporting packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def import_packages(self) -> dict:
        try:
            self.logger.info("import_packages called")
            manifest_pkgs = read_manifest()
            
            installed_res = self.manager.read_installed()
            installed_pkgs = installed_res.installed or []
            installed_names_lower = {p.name.lower() for p in installed_pkgs if p.name}
            
            to_install = []
            skipped_count = 0
            for p in manifest_pkgs:
                if not isinstance(p, dict):
                    continue
                name = p.get('name')
                if not name:
                    continue
                if name.lower() in installed_names_lower:
                    skipped_count += 1
                else:
                    to_install.append(p)
                    
            if not to_install:
                return {
                    'status': 'ok',
                    'data': {
                        'installed': 0,
                        'skipped': skipped_count,
                        'failed': []
                    }
                }
                
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Importing {len(to_install)} packages from manifest...')")
                
            watcher = WebviewWatcher(self.logger, self.window, self)
            installed_count = 0
            failed_list = []

            for p in to_install:
                name = p.get('name')
                pkg_type = p.get('type', 'unknown')
                search_res = self.manager.search(words=name)
                
                match = None
                if search_res:
                    candidates = (search_res.installed or []) + (search_res.new or [])
                    for candidate in candidates:
                        if candidate.name and candidate.name.lower() == name.lower():
                            match = candidate
                            break
                            
                if match:
                    try:
                        self.logger.info(f"Import installing: {match.name}")
                        proceed, root_password = self.acquire_root_password(SoftwareAction.INSTALL, match)
                        if not proceed:
                            self.logger.info("Import cancelled (no root password)")
                            if self.window:
                                self.window.evaluate_js("terminalSetDone(false)")
                            return {'status': 'cancelled',
                                    'data': {'installed': installed_count,
                                             'skipped': skipped_count,
                                             'failed': failed_list}}
                        install_res = self.manager.install(match, root_password=root_password, disk_loader=None, handler=watcher)
                        success = install_res.success if install_res else False
                        if success:
                            installed_count += 1
                            try:
                                t = match.get_type() or match.gem_name
                            except Exception:
                                t = getattr(match, 'gem_name', 'unknown')
                            record_activity('install', match.name, t, True)
                        else:
                            failed_list.append(name)
                            try:
                                t = match.get_type() or match.gem_name
                            except Exception:
                                t = getattr(match, 'gem_name', 'unknown')
                            record_activity('install', name, t, False, 'import failed')
                    except Exception as e:
                        failed_list.append(name)
                        record_activity('install', name, pkg_type, False, f'import failed: {e}')
                else:
                    failed_list.append(name)
                    
            if self.window:
                self.window.evaluate_js("terminalSetDone(true)")
                
            return {
                'status': 'ok',
                'data': {
                    'installed': installed_count,
                    'skipped': skipped_count,
                    'failed': failed_list
                }
            }
        except Exception as e:
            self.logger.error(f"Error importing packages: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            return {'status': 'error', 'message': str(e)}


