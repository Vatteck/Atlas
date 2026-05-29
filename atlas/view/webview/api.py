import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from atlas.commons.view_utils import get_human_size_str
from atlas.view.core.controller import GenericSoftwareManager
from atlas.view.webview.watcher import WebviewWatcher
from atlas.view.webview.activity_log import record_activity, get_activity_log
from atlas.view.webview.export import write_manifest, read_manifest


class BauhApi:

    def __init__(self, manager: GenericSoftwareManager, logger: logging.Logger):
        self.manager = manager
        self.logger = logger
        self.pkg_registry = {}  # opaque_id -> SoftwarePackage
        self._registry_lock = threading.Lock()
        self.window = None
        
        # Prepare the managers in a background thread to prevent GUI lockup using ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._prepare_future = self._executor.submit(self._prepare_manager)

    def set_window(self, window):
        self.window = window
        self.logger.info("pywebview window reference linked in BauhApi")

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

    def _serialize_pkg(self, pkg) -> dict:
        pkg_id = str(id(pkg))
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
        }

    def _get_pkg(self, pkg_id: str):
        with self._registry_lock:
            return self.pkg_registry.get(pkg_id)

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
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Installing {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window)
            result = self.manager.install(pkg, root_password=None, disk_loader=None, handler=watcher)
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
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Uninstalling {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window)
            result = self.manager.uninstall(pkg, root_password=None, handler=watcher)
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
            if self.window:
                self.window.evaluate_js(f"terminalOpen('Updating {pkg.name}')")
            watcher = WebviewWatcher(self.logger, self.window)
            reqs = self.manager.get_upgrade_requirements([pkg], root_password=None, watcher=watcher)
            success = self.manager.upgrade(reqs, root_password=None, handler=watcher)
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
            return {'status': 'ok', 'data': info or {}}
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
            watcher = WebviewWatcher(self.logger, self.window)
            
            success = True
            for idx, pkg in enumerate(pkgs):
                if self.window:
                    self.window.evaluate_js(f"terminalOpen('Uninstalling {pkg.name} ({idx+1}/{len(pkgs)})')")
                
                res = self.manager.uninstall(pkg, root_password=None, handler=watcher)
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
            
            watcher = WebviewWatcher(self.logger, self.window)
            installed_res = self.manager.read_installed()
            upgradable = [p for p in (installed_res.installed or []) if p.update]
            
            if not upgradable:
                self.logger.info("No updates available.")
                if self.window:
                    self.window.evaluate_js("terminalSetStatus('No updates available')")
                    self.window.evaluate_js("terminalSetDone(true)")
                return {'status': 'ok', 'success': True, 'message': 'No updates available'}
            
            self.logger.info(f"Found {len(upgradable)} packages to upgrade: {[p.name for p in upgradable]}")
            if self.window:
                self.window.evaluate_js(f"terminalSetStatus('Upgrading {len(upgradable)} packages...')")
                
            reqs = self.manager.get_upgrade_requirements(upgradable, root_password=None, watcher=watcher)
            success = self.manager.upgrade(reqs, root_password=None, handler=watcher)
            
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
                    self.pkg_registry[str(id(pkg))] = pkg

            for pkg in pkgs:
                pkg_id = str(id(pkg))

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
                
            watcher = WebviewWatcher(self.logger, self.window)
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
                        install_res = self.manager.install(match, root_password=None, disk_loader=None, handler=watcher)
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


