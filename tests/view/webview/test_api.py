import unittest
import json
from datetime import datetime, date
from unittest.mock import Mock, patch, mock_open
from atlas.view.webview.api import AtlasApi, _json_safe


class OpenUrlTest(unittest.TestCase):
    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_opens_http_url(self, mock_open):
        res = self.api.open_url('https://aur.archlinux.org/packages/antigravity')
        self.assertEqual('ok', res['status'])
        mock_open.assert_called_once_with('https://aur.archlinux.org/packages/antigravity')

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_rejects_non_http_scheme(self, mock_open):
        for bad in ['file:///etc/passwd', 'javascript:alert(1)', '', None, 'aur.archlinux.org']:
            res = self.api.open_url(bad)
            self.assertEqual('error', res['status'])
        mock_open.assert_not_called()


class AppSettingsTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())
        # core config
        self.core = {
            'gems': None,
            'suggestions': {'enabled': True, 'by_type': 15},
            'system': {'notifications': True, 'single_dependency_checking': False},
            'updates': {'check_interval': 5, 'ask_for_reboot': True},
            'download': {'icons': True},
            'store_root_password': True,
        }
        self.manager.configman.get_config.return_value = self.core

        # two managers: an arch one (works) and a flatpak one (works) with a config manager
        def mk(modname, enabled, can_work):
            m = Mock()
            m.__module__ = f'atlas.gems.{modname}.controller'
            m.is_enabled.return_value = enabled
            m.can_work.return_value = (can_work, None)
            return m
        self.arch = mk('arch', True, True)
        self.flatpak = mk('flatpak', True, True)
        self.flatpak.configman.get_config.return_value = {'installation_level': 'user'}
        self.manager.managers = [self.arch, self.flatpak]

    def test_get_app_settings_shape(self):
        res = self.api.get_app_settings()
        self.assertEqual('ok', res['status'])
        data = res['data']
        ids = {t['id'] for t in data['types']}
        self.assertEqual({'arch', 'flatpak'}, ids)
        self.assertTrue(data['flatpak_available'])
        self.assertEqual('user', data['flatpak_installation_level'])
        self.assertTrue(data['general']['suggestions_enabled'])

    def test_save_app_settings_writes_gems_and_applies_live(self):
        res = self.api.save_app_settings({'types': {'arch': True, 'flatpak': False},
                                          'general': {'suggestions_enabled': False},
                                          'flatpak_installation_level': 'system'})
        self.assertEqual('ok', res['status'])
        # gems list written (enabled only) + general toggle applied
        self.assertEqual(['arch'], self.core['gems'])
        self.assertFalse(self.core['suggestions']['enabled'])
        self.manager.configman.save_config.assert_called_once_with(self.core)
        # live apply: set_enabled called per manager
        self.arch.set_enabled.assert_called_once_with(True)
        self.flatpak.set_enabled.assert_called_once_with(False)
        # flatpak level persisted
        self.flatpak.configman.save_config.assert_called_once()

    def test_save_app_settings_invalid_flatpak_level_falls_back_to_ask(self):
        self.api.save_app_settings({'flatpak_installation_level': 'bogus'})
        saved = self.flatpak.configman.save_config.call_args[0][0]
        self.assertIsNone(saved['installation_level'])


class JsonSafeTest(unittest.TestCase):
    """get_info() payloads carry datetimes (Arch first_submitted/last_modified, Flathub
    release dates) that pywebview's json.dumps can't encode — _json_safe converts them."""

    def test_converts_datetime_and_date(self):
        out = _json_safe({'08_first_submitted': datetime(2024, 5, 1, 13, 30), 'd': date(2024, 5, 1)})
        self.assertEqual('2024-05-01 13:30', out['08_first_submitted'])
        self.assertEqual('2024-05-01', out['d'])

    def test_recurses_nested_structures(self):
        out = _json_safe({'data': {'items': [{'ts': datetime(2024, 1, 2, 3, 4)}]}})
        self.assertEqual('2024-01-02 03:04', out['data']['items'][0]['ts'])

    def test_passes_through_plain_values_and_is_json_dumpable(self):
        payload = _json_safe({'a': 1, 'b': 'x', 'c': True, 'd': None, 'e': [1, 2.5]})
        self.assertEqual({'a': 1, 'b': 'x', 'c': True, 'd': None, 'e': [1, 2.5]}, payload)
        json.dumps(payload)  # must not raise


class AtlasApiOrphansTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)

    def test_get_orphans_success(self):
        # Prepare mock packages
        pkg_orphan = Mock()
        pkg_orphan.orphan = True
        pkg_orphan.name = "orphan-pkg"
        pkg_orphan.description = "an orphan"
        pkg_orphan.version = "1.0"
        pkg_orphan.latest_version = "1.0"
        pkg_orphan.installed = True
        pkg_orphan.update = False
        pkg_orphan.icon_url = None
        pkg_orphan.publisher = None
        pkg_orphan.size = 100
        pkg_orphan.categories = []
        pkg_orphan.get_publisher = Mock(return_value=None)
        pkg_orphan.get_type = Mock(return_value="Flatpak")

        pkg_regular = Mock()
        pkg_regular.orphan = False
        pkg_regular.name = "regular-pkg"
        
        # Package with no orphan attribute
        pkg_no_attr = Mock(spec=[]) 
        pkg_no_attr.name = "no-attr"

        installed_result = Mock()
        installed_result.installed = [pkg_orphan, pkg_regular, pkg_no_attr]
        self.manager.read_installed.return_value = installed_result

        res = self.api.get_orphans()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(len(res['data']), 1)
        self.assertEqual(res['data'][0]['name'], 'orphan-pkg')
        self.manager.read_installed.assert_called_once()

    def test_get_orphans_error(self):
        self.manager.read_installed.side_effect = Exception("Read failed")
        res = self.api.get_orphans()
        self.assertEqual(res['status'], 'error')
        self.assertIn("Read failed", res['message'])

    def test_serialize_pkg_registry_eviction(self):
        # Setup mock package
        pkg = Mock()
        pkg.name = "test-pkg"
        pkg.description = "desc"
        pkg.version = "1.0"
        pkg.latest_version = "1.0"
        pkg.installed = True
        pkg.update = False
        pkg.icon_url = None
        pkg.publisher = None
        pkg.size = 100
        pkg.categories = []
        pkg.get_publisher = Mock(return_value=None)
        pkg.get_type = Mock(return_value="Flatpak")

        # Populate registry to 2000 elements
        for i in range(2000):
            self.api.pkg_registry[str(i)] = Mock()

        self.assertEqual(len(self.api.pkg_registry), 2000)

        # Serialize one more package (registry size is 2000, not exceeding 2000 yet)
        res = self.api._serialize_pkg(pkg)
        pkg_id = res['id']
        self.assertEqual(len(self.api.pkg_registry), 2001)
        self.assertIn(pkg_id, self.api.pkg_registry)

        # Now force the registry size to 2005 (exceeding 2000)
        for i in range(2000, 2005):
            self.api.pkg_registry[str(i)] = Mock()

        self.assertEqual(len(self.api.pkg_registry), 2006)

        # Serialize one more package, it should trigger eviction (clear) and then add itself
        res2 = self.api._serialize_pkg(pkg)
        pkg_id2 = res2['id']
        self.assertEqual(len(self.api.pkg_registry), 1)
        self.assertIn(pkg_id2, self.api.pkg_registry)


class AtlasApiPinTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        
        self.pkg = Mock()
        self.pkg.name = "test-pin-pkg"
        self.api.pkg_registry["test-id"] = self.pkg

    def test_pin_update_success(self):
        res = self.api.pin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.ignore_update.assert_called_once_with(self.pkg)

    def test_pin_update_not_found(self):
        res = self.api.pin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_pin_update_error(self):
        self.manager.ignore_update.side_effect = Exception("Pin failed")
        res = self.api.pin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Pin failed", res['message'])

    def test_unpin_update_success(self):
        res = self.api.unpin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.revert_ignored_update.assert_called_once_with(self.pkg)

    def test_unpin_update_not_found(self):
        res = self.api.unpin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_unpin_update_error(self):
        self.manager.revert_ignored_update.side_effect = Exception("Unpin failed")
        res = self.api.unpin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unpin failed", res['message'])


class AtlasApiExportImportTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)

    @patch('atlas.view.webview.export.open', new_callable=mock_open)
    @patch('atlas.view.webview.export.os.path.exists', return_value=True)
    def test_read_manifest_success(self, mock_exists, mock_file):
        mock_data = {
            'created': '2026-05-28T16:00:00',
            'version': 1,
            'packages': [{'name': 'Firefox', 'type': 'Flatpak'}]
        }
        mock_file.return_value.read.return_value = json.dumps(mock_data)
        
        from atlas.view.webview.export import read_manifest
        packages = read_manifest()
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]['name'], 'Firefox')

    @patch('atlas.view.webview.export.os.path.exists', return_value=False)
    def test_read_manifest_file_not_found(self, mock_exists):
        from atlas.view.webview.export import read_manifest
        with self.assertRaises(FileNotFoundError):
            read_manifest()

    @patch('atlas.view.webview.export.open', new_callable=mock_open)
    def test_write_manifest_success(self, mock_file):
        from atlas.view.webview.export import write_manifest, MANIFEST_PATH
        pkgs = [{'name': 'Firefox', 'type': 'Flatpak'}]
        path = write_manifest(pkgs)
        self.assertEqual(path, MANIFEST_PATH)
        mock_file.assert_called_once_with(MANIFEST_PATH, 'w', encoding='utf-8')

    @patch('atlas.view.webview.api.write_manifest')
    def test_export_packages_success(self, mock_write):
        mock_write.return_value = "/home/user/atlas-manifest.json"
        
        pkg = Mock()
        pkg.name = "test-pkg"
        pkg.description = "desc"
        pkg.version = "1.0"
        pkg.latest_version = "1.0"
        pkg.installed = True
        pkg.update = False
        pkg.icon_url = None
        pkg.publisher = None
        pkg.size = 100
        pkg.categories = []
        pkg.get_publisher = Mock(return_value=None)
        pkg.get_type = Mock(return_value="Flatpak")
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.export_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['count'], 1)
        self.assertEqual(res['data']['path'], "/home/user/atlas-manifest.json")
        mock_write.assert_called_once()

    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_all_skipped(self, mock_read):
        mock_read.return_value = [{'name': 'test-pkg', 'type': 'Flatpak'}]
        
        pkg = Mock()
        pkg.name = "test-pkg"
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 0)
        self.assertEqual(res['data']['skipped'], 1)
        self.assertEqual(res['data']['failed'], [])

    @patch('atlas.view.webview.api.WebviewWatcher')
    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_install_success(self, mock_read, mock_watcher_cls):
        mock_read.return_value = [{'name': 'missing-pkg', 'type': 'Flatpak'}]
        
        # Installed packages (none matching 'missing-pkg')
        installed_res = Mock()
        installed_res.installed = []
        self.manager.read_installed.return_value = installed_res
        
        # Search candidate
        candidate = Mock()
        candidate.name = "missing-pkg"
        candidate.get_type = Mock(return_value="Flatpak")
        
        search_res = Mock()
        search_res.installed = []
        search_res.new = [candidate]
        self.manager.search.return_value = search_res
        
        # Mock successful installation
        install_res = Mock()
        install_res.success = True
        self.manager.install.return_value = install_res

        # Flatpak (user) install needs no root -> broker returns (True, None)
        self.manager.requires_root.return_value = False

        # Setup self.api.window mock to prevent None error or call js
        self.api.window = Mock()
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 1)
        self.assertEqual(res['data']['skipped'], 0)
        self.assertEqual(res['data']['failed'], [])
        self.manager.install.assert_called_once_with(candidate, root_password=None, disk_loader=None, handler=mock_watcher_cls.return_value)

    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_invalid_entries_skipped(self, mock_read):
        # Manifest list has strings and None, plus one valid entry which is already installed
        mock_read.return_value = ["invalid_str", None, {'name': 'test-pkg', 'type': 'Flatpak'}]
        
        pkg = Mock()
        pkg.name = "test-pkg"
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 0)
        self.assertEqual(res['data']['skipped'], 1)
        self.assertEqual(res['data']['failed'], [])


class AtlasApiRootPasswordTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        self.api.window = Mock()  # evaluate_js -> Mock, harmless

    def test_no_root_needed_returns_none_without_prompt(self):
        from atlas.api.abstract.controller import SoftwareAction
        self.manager.requires_root.return_value = False
        proceed, pwd = self.api.acquire_root_password(SoftwareAction.SEARCH, None)
        self.assertTrue(proceed)
        self.assertIsNone(pwd)
        self.api.window.evaluate_js.assert_not_called()  # no modal shown

    @patch('atlas.view.webview.api.validate_root_password')
    def test_valid_password_is_cached(self, mock_validate):
        from atlas.api.abstract.controller import SoftwareAction
        import threading
        self.manager.requires_root.return_value = True
        mock_validate.side_effect = lambda pwd, **k: pwd == 'secret'

        # Simulate the modal submitting the password once the prompt is shown.
        def poll_and_submit():
            import time
            for _ in range(100):
                if self.api.window.evaluate_js.called:
                    self.api.submit_root_password('secret')
                    return
                time.sleep(0.02)
        threading.Thread(target=poll_and_submit, daemon=True).start()

        proceed, pwd = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertTrue(proceed)
        self.assertEqual(pwd, 'secret')

        # Second call reuses the cache (validate succeeds) without prompting again.
        self.api.window.evaluate_js.reset_mock()
        proceed2, pwd2 = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertTrue(proceed2)
        self.assertEqual(pwd2, 'secret')
        self.api.window.evaluate_js.assert_not_called()

    @patch('atlas.view.webview.api.validate_root_password')
    def test_cancel_returns_false(self, mock_validate):
        from atlas.api.abstract.controller import SoftwareAction
        import threading, time
        self.manager.requires_root.return_value = True
        mock_validate.return_value = False

        def poll_and_cancel():
            for _ in range(50):
                if self.api.window.evaluate_js.called:
                    self.api.submit_root_password(None)
                    return
                time.sleep(0.02)
        threading.Thread(target=poll_and_cancel, daemon=True).start()

        proceed, pwd = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertFalse(proceed)
        self.assertIsNone(pwd)


class AtlasApiDialogTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        self.api.window = Mock()

    def _answer(self, fn):
        import threading, time

        def poll():
            for _ in range(100):
                if self.api.window.evaluate_js.called:
                    fn()
                    return
                time.sleep(0.02)
        threading.Thread(target=poll, daemon=True).start()

    def test_confirmation_accept(self):
        self._answer(lambda: self.api.submit_confirmation(True))
        confirmed, selections = self.api.prompt_confirmation('T', 'body', 'Yes', 'No')
        self.assertTrue(confirmed)
        self.assertIsNone(selections)

    def test_confirmation_deny(self):
        self._answer(lambda: self.api.submit_confirmation(False))
        confirmed, _ = self.api.prompt_confirmation('T', 'body')
        self.assertFalse(confirmed)

    def test_confirmation_no_window_defaults_true(self):
        self.api.window = None
        confirmed, selections = self.api.prompt_confirmation('T', 'body')
        self.assertTrue(confirmed)
        self.assertIsNone(selections)

    def test_confirmation_returns_component_selections(self):
        # the modal hands back per-component selections; prompt_confirmation surfaces them
        self._answer(lambda: self.api.submit_confirmation(True, [[0, 2]]))
        confirmed, selections = self.api.prompt_confirmation(
            'T', 'body', components=[{'kind': 'multiselect', 'options': []}])
        self.assertTrue(confirmed)
        self.assertEqual([[0, 2]], selections)

    def test_message_blocks_until_ack(self):
        self._answer(self.api.submit_message_ack)
        # Returns once acked; if it didn't block/return, the test would hang then time out.
        self.api.prompt_message('Title', 'Body', 'error')
        self.assertTrue(self.api._message_event.is_set())


