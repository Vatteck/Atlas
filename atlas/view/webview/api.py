import json
import logging
import threading
import traceback
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
from atlas.commons.system import validate_root_password
from atlas.commons.view_utils import get_human_size_str
from atlas.view.core.controller import GenericSoftwareManager
from atlas.view.webview.watcher import WebviewWatcher
from atlas.view.webview.activity_log import record_activity, get_activity_log
from atlas.view.webview.export import write_manifest, read_manifest


class AtlasApi:

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
                            components: Optional[list] = None) -> Tuple[bool, Optional[list]]:
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

        return {
            'id': pkg_id,
            'name': pkg.name or '',
            'description': pkg.description or '',
            'version': pkg.version or '',
            'latest_version': pkg.latest_version or '',
            'type': pkg_type,
            'installed': bool(pkg.installed),
            'update_available': bool(pkg.update),
            'icon_url': self._get_valid_icon_url(pkg.icon_url),
            'publisher': publisher,
            'size': pkg.size,
            'categories': list(pkg.categories) if pkg.categories else [],
            'can_be_run': pkg.can_be_run() if hasattr(pkg, 'can_be_run') else False,
            'can_be_downgraded': pkg.can_be_downgraded() if hasattr(pkg, 'can_be_downgraded') else False,
            'has_info': pkg.has_info() if hasattr(pkg, 'has_info') else False,
            'has_history': pkg.has_history() if hasattr(pkg, 'has_history') else False,
            'update_ignored': pkg.is_update_ignored() if hasattr(pkg, 'is_update_ignored') else False,
            'supports_pinning': pkg.supports_ignored_updates() if hasattr(pkg, 'supports_ignored_updates') else False,
            # AUR metadata (None for non-Arch packages) — used to rank/badge AUR variants
            # in the webview. See docs/plans/2026-06-01-source-types-and-multisource-cards.md.
            'votes': getattr(pkg, 'votes', None),
            'popularity': getattr(pkg, 'popularity', None),
            'maintainer': getattr(pkg, 'maintainer', None),
            'out_of_date': bool(getattr(pkg, 'out_of_date', None)),
            'package_base': getattr(pkg, 'package_base', None),
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

    def get_installed(self, pkg_type: str = 'all') -> dict:
        try:
            self.logger.info("get_installed called")
            result = self.manager.read_installed()
            pkgs = result.installed or []
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in pkgs]}
        except Exception as e:
            self.logger.error(f"Error fetching installed packages: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}

    def get_orphans(self) -> dict:
        try:
            self.logger.info("get_orphans called")
            result = self.manager.read_installed()
            pkgs = result.installed or []
            orphans = [p for p in pkgs if hasattr(p, 'orphan') and p.orphan]
            return {'status': 'ok', 'data': [self._serialize_pkg(p) for p in orphans]}
        except Exception as e:
            self.logger.error(f"Error fetching orphan packages: {e}")
            traceback.print_exc()
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
            
            return {'status': 'ok', 'success': bool(success)}
        except Exception as e:
            self.logger.error(f"Error updating package {pkg.name}: {e}")
            traceback.print_exc()
            if self.window:
                self.window.evaluate_js("terminalSetDone(false)")
            record_activity('update', pkg.name, pkg.get_type() or pkg.gem_name, False, str(e))
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
                
            return {'status': 'ok', 'success': success}
        except Exception as e:
            self.logger.error(f"Error in batch uninstall: {e}")
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


