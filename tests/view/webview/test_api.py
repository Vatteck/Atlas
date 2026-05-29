import unittest
import json
from unittest.mock import Mock, patch, mock_open
from atlas.view.webview.api import BauhApi


class BauhApiOrphansTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = BauhApi(self.manager, self.logger)

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


class BauhApiPinTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = BauhApi(self.manager, self.logger)
        
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


class BauhApiExportImportTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = BauhApi(self.manager, self.logger)

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


