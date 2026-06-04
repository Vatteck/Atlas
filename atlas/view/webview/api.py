import json
import logging
import os
import shlex
import shutil
import threading
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import List, Optional, Tuple


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


class AtlasApi:

    PACMAN_CACHE_DIR = '/var/cache/pacman/pkg'
    ARCH_NEWS_URL = 'https://archlinux.org/feeds/news/'

    # Browse-by-category buckets for the Discovery view. The shipped categories.txt uses many
    # inconsistent raw labels (Browser/browser, Xfce/XFCE, Python, Emulator, Manjaro, …); we
    # merge the synonyms into a small curated, ordered set of top-level buckets. Each raw label
    # maps into at most the buckets that list it. See docs/plans/2026-06-02-browse-by-category.md.
    CATEGORY_BUCKETS = (
        ('games',       'Games',         '🎮', ('Game', 'Emulator')),
        ('internet',    'Internet',      '🌐', ('Network', 'Browser', 'browser', 'Torrent', 'P2P', 'IRC')),
        ('multimedia',  'Audio & Video', '🎵', ('Audio', 'Video', 'AudioVideo')),
        ('graphics',    'Graphics',      '🎨', ('Graphics', 'GTK')),
        ('development', 'Development',    '⌨',  ('Development', 'Python', 'Javascript')),
        ('office',      'Office',         '📄', ('Office',)),
        ('utilities',   'Utilities',     '🧰', ('Utility',)),
        ('system',      'System',        '⚙',  ('System', 'Settings', 'Security', 'Kernel',
                                                'Printing', 'Bluetooth', 'Qt', 'KDE', 'Gnome',
                                                'Xfce', 'XFCE', 'Manjaro')),
    )

    def __init__(self, manager: GenericSoftwareManager, logger: logging.Logger):
        self.manager = manager
        self.logger = logger
        self.pkg_registry = {}  # opaque_id -> SoftwarePackage
        self._registry_lock = threading.Lock()
        self.window = None

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

    @staticmethod
    def _desktop_icon_name(desktop_text: str) -> Optional[str]:
        """The `Icon=` value from a .desktop file's first occurrence, or None."""
        for line in (desktop_text or '').splitlines():
            line = line.strip()
            if line.startswith('Icon='):
                return line[5:].strip() or None
        return None

    def _find_icon_file(self, name: str) -> Optional[str]:
        """Resolve an icon name (or absolute path) to a file under the standard icon dirs."""
        if not name:
            return None
        if name.startswith('/'):
            return name if os.path.isfile(name) else None
        candidates = list(dict.fromkeys([name, os.path.splitext(name)[0]]))  # name + stem, deduped
        for d in self._ICON_DIRS:
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
            for key, label, icon, raw in self.CATEGORY_BUCKETS:
                count = len(self._category_names(raw))
                if count:
                    buckets.append({'key': key, 'label': label, 'icon': icon, 'count': count})
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
            if arch_man is None or not names:
                return {'status': 'ok', 'data': []}

            pkgs = arch_man.list_category_packages(names)
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching category packages: {e}")
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
            if self.window:
                self.window.evaluate_js(f"terminalSetDone({str(success).lower()})")
            
            # Record Activity
            record_activity('install', pkg.name, pkg.get_type() or pkg.gem_name, success)
            self._notify(f"{pkg.name} installed successfully" if success else f"Failed to install {pkg.name}")

            return {'status': 'ok', 'success': success}
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
            changed = {'old': baseline, 'new': current} if (baseline and current != baseline) else None

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
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
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
            logs = get_activity_log()
            return {'status': 'ok', 'data': logs}
        except Exception as e:
            self.logger.error(f"Error fetching activity log: {e}")
            return {'status': 'error', 'message': str(e)}

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


