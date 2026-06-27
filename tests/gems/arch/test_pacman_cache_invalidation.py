import unittest
from unittest.mock import Mock, MagicMock, patch

from atlas.api.abstract.controller import TransactionResult
from atlas.gems.arch.controller import ArchManager, ArchPackage
from atlas.gems.arch.worker import SyncDatabases


class PacmanCacheInvalidationTest(unittest.TestCase):
    """Verifies that pacman.clear_caches() is correctly called during successful
    operations in ArchManager and the database synchronization worker.
    """

    # --- ArchManager._sync_databases() ---

    @patch('atlas.gems.arch.controller.database.should_sync')
    @patch('atlas.gems.arch.controller.database.register_sync')
    @patch('atlas.gems.arch.controller.pacman.sync_databases')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_sync_databases_clears_cache_on_success(self, mock_clear_caches, mock_sync_db, mock_reg_sync, mock_should_sync):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        mock_should_sync.return_value = True

        handler = MagicMock()
        handler.handle_simple.return_value = (True, 'output')

        arch_config = {'sync_databases': True}
        mgr._sync_databases(arch_config, True, 'root', handler)

        mock_clear_caches.assert_called_once()
        mock_reg_sync.assert_called_once_with(mgr.logger)

    @patch('atlas.gems.arch.controller.database.should_sync')
    @patch('atlas.gems.arch.controller.database.register_sync')
    @patch('atlas.gems.arch.controller.pacman.sync_databases')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_sync_databases_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_sync_db, mock_reg_sync, mock_should_sync):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        mock_should_sync.return_value = True

        handler = MagicMock()
        handler.handle_simple.return_value = (False, 'error')

        arch_config = {'sync_databases': True}
        mgr._sync_databases(arch_config, True, 'root', handler)

        mock_clear_caches.assert_not_called()
        mock_reg_sync.assert_not_called()

    # --- ArchManager.install() ---

    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    @patch('atlas.gems.arch.controller.os.path.exists')
    def test_install_clears_cache_on_success(self, mock_exists, mock_clear_caches):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()
        mgr.aur_client = Mock()
        mgr.configman = Mock()
        mgr.configman.get_config.return_value = {'aur': False, 'edit_aur_pkgbuild': False}

        mgr.check_action_allowed = Mock(return_value=True)
        mgr._is_database_locked = Mock(return_value=False)
        mgr._sync_databases = Mock()

        pkg = MagicMock()
        pkg.repository = 'extra'
        pkg.name = 'test-pkg'
        pkg.installed = False
        pkg.get_disk_data_path.return_value = '/dummy'

        mock_exists.return_value = False
        mgr._install_from_repository = Mock(return_value=True)

        watcher = MagicMock()

        result = mgr.install(pkg, 'root', None, watcher)

        self.assertTrue(result.success)
        mock_clear_caches.assert_called_once()

    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_install_does_not_clear_cache_on_failure(self, mock_clear_caches):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()
        mgr.aur_client = Mock()
        mgr.configman = Mock()
        mgr.configman.get_config.return_value = {'aur': False, 'edit_aur_pkgbuild': False}

        mgr.check_action_allowed = Mock(return_value=True)
        mgr._is_database_locked = Mock(return_value=False)
        mgr._sync_databases = Mock()

        pkg = MagicMock()
        pkg.repository = 'extra'
        pkg.name = 'test-pkg'
        pkg.installed = False

        mgr._install_from_repository = Mock(return_value=False)

        watcher = MagicMock()

        result = mgr.install(pkg, 'root', None, watcher)

        self.assertFalse(result.success)
        mock_clear_caches.assert_not_called()

    # --- ArchManager._uninstall_pkgs() ---

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.SimpleProcess')
    @patch('atlas.gems.arch.controller.pacman.list_installed_names')
    @patch('atlas.gems.arch.controller.ArchPackage.disk_cache_path')
    @patch('atlas.gems.arch.controller.os.path.exists')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_uninstall_pkgs_clears_cache_on_success(self, mock_clear_caches, mock_exists, mock_cache_path, mock_list_installed, mock_simple_proc, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        handler = MagicMock()
        handler.handle_simple.return_value = (True, 'output')

        mock_list_installed.return_value = []
        mock_exists.return_value = False

        status_handler_inst = mock_status_handler.return_value

        res = mgr._uninstall_pkgs(['test-pkg'], 'root', handler)

        self.assertTrue(res)
        mock_clear_caches.assert_called_once()
        status_handler_inst.start.assert_called_once()
        status_handler_inst.stop_working.assert_called_once()

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.SimpleProcess')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_uninstall_pkgs_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_simple_proc, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        handler = MagicMock()
        handler.handle_simple.return_value = (False, 'error')

        res = mgr._uninstall_pkgs(['test-pkg'], 'root', handler)

        self.assertFalse(res)
        mock_clear_caches.assert_not_called()

    # --- ArchManager._upgrade_repo_pkgs() ---

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.pacman.upgrade_several')
    @patch('atlas.gems.arch.controller.pacman.map_repositories')
    @patch('atlas.gems.arch.controller.disk.write_several')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_upgrade_repo_pkgs_clears_cache_on_success(self, mock_clear_caches, mock_write_several, mock_map_repos, mock_upgrade_several, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()
        mgr.categories = {}

        handler = MagicMock()
        handler.handle_simple.return_value = (True, 'output')

        mock_map_repos.return_value = {'pkg1': 'extra'}

        status_handler_inst = mock_status_handler.return_value

        res = mgr._upgrade_repo_pkgs(
            to_upgrade=['pkg1'],
            to_remove=None,
            handler=handler,
            root_password='root',
            multithread_download=False,
            pkgs_data={},
            download=False,
            check_syncfirst=False
        )

        self.assertTrue(res)
        mock_clear_caches.assert_called_once()
        mock_write_several.assert_called_once()

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.pacman.upgrade_several')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_upgrade_repo_pkgs_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_upgrade_several, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        handler = MagicMock()
        handler.handle_simple.return_value = (False, 'error')

        res = mgr._upgrade_repo_pkgs(
            to_upgrade=['pkg1'],
            to_remove=None,
            handler=handler,
            root_password='root',
            multithread_download=False,
            pkgs_data={},
            download=False,
            check_syncfirst=False
        )

        self.assertFalse(res)
        mock_clear_caches.assert_not_called()

    # --- ArchManager._remove_transaction_packages() ---

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.pacman.remove_several')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_remove_transaction_packages_clears_cache_on_success(self, mock_clear_caches, mock_remove_several, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        handler = MagicMock()
        handler.handle_simple.return_value = (True, 'output')

        res = mgr._remove_transaction_packages({'pkg1'}, handler, 'root')

        self.assertTrue(res)
        mock_clear_caches.assert_called_once()

    @patch('atlas.gems.arch.controller.TransactionStatusHandler')
    @patch('atlas.gems.arch.controller.pacman.remove_several')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_remove_transaction_packages_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_remove_several, mock_status_handler):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()

        handler = MagicMock()
        handler.handle_simple.return_value = (False, 'error')

        res = mgr._remove_transaction_packages({'pkg1'}, handler, 'root')

        self.assertFalse(res)
        mock_clear_caches.assert_not_called()

    # --- ArchManager.upgrade_system() ---

    @patch('atlas.gems.arch.controller.database.register_sync')
    @patch('atlas.gems.arch.controller.pacman.upgrade_system')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_upgrade_system_clears_cache_on_success(self, mock_clear_caches, mock_upgrade_sys, mock_reg_sync):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()
        mgr.context = MagicMock()
        mgr.context.internet_checker.is_available.return_value = True

        pkg = MagicMock()
        pkg.repository = 'extra'
        pkg.update = True

        mgr.read_installed = MagicMock()
        mgr.read_installed.return_value.installed = [pkg]
        mgr._is_database_locked = Mock(return_value=False)

        handler = MagicMock()
        handler.handle_simple.return_value = (True, 'success')

        with patch('atlas.gems.arch.controller.ProcessHandler', return_value=handler):
            watcher = MagicMock()
            res = mgr.upgrade_system('root', watcher)

            self.assertTrue(res)
            mock_clear_caches.assert_called_once()
            mock_reg_sync.assert_called_once_with(mgr.logger)

    @patch('atlas.gems.arch.controller.pacman.upgrade_system')
    @patch('atlas.gems.arch.controller.pacman.clear_caches')
    def test_upgrade_system_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_upgrade_sys):
        mgr = ArchManager.__new__(ArchManager)
        mgr.logger = Mock()
        mgr.i18n = MagicMock()
        mgr.context = MagicMock()
        mgr.context.internet_checker.is_available.return_value = True

        pkg = MagicMock()
        pkg.repository = 'extra'
        pkg.update = True

        mgr.read_installed = MagicMock()
        mgr.read_installed.return_value.installed = [pkg]
        mgr._is_database_locked = Mock(return_value=False)

        handler = MagicMock()
        handler.handle_simple.return_value = (False, 'error')

        with patch('atlas.gems.arch.controller.ProcessHandler', return_value=handler):
            watcher = MagicMock()
            res = mgr.upgrade_system('root', watcher)

            self.assertFalse(res)
            mock_clear_caches.assert_not_called()

    # --- SyncDatabases Worker ---

    @patch('atlas.gems.arch.worker.database.register_sync')
    @patch('atlas.gems.arch.worker.pacman.get_databases')
    @patch('atlas.gems.arch.worker.new_root_subprocess')
    @patch('atlas.gems.arch.worker.pacman.clear_caches')
    def test_sync_databases_worker_clears_cache_on_success(self, mock_clear_caches, mock_subproc, mock_get_dbs, mock_reg_sync):
        taskman = MagicMock()
        refresh_mirrors = MagicMock()
        refresh_mirrors.refreshed = True
        create_config = MagicMock()
        create_config.config = {'sync_databases_startup': True}

        with patch('atlas.gems.arch.worker.aur.is_supported', return_value=True):
            worker = SyncDatabases(
                taskman=taskman,
                root_password='root',
                i18n=MagicMock(),
                logger=Mock(),
                refresh_mirrors=refresh_mirrors,
                create_config=create_config
            )

            mock_get_dbs.return_value = ['core']

            p = MagicMock()
            p.stdout = [b'downloading core']
            p.stderr = []
            p.returncode = 0
            mock_subproc.return_value = p

            worker.run()

            mock_clear_caches.assert_called_once()
            mock_reg_sync.assert_called_once_with(worker.logger)
            self.assertTrue(worker.synchronized)

    @patch('atlas.gems.arch.worker.database.register_sync')
    @patch('atlas.gems.arch.worker.pacman.get_databases')
    @patch('atlas.gems.arch.worker.new_root_subprocess')
    @patch('atlas.gems.arch.worker.pacman.clear_caches')
    def test_sync_databases_worker_does_not_clear_cache_on_failure(self, mock_clear_caches, mock_subproc, mock_get_dbs, mock_reg_sync):
        taskman = MagicMock()
        refresh_mirrors = MagicMock()
        refresh_mirrors.refreshed = True
        create_config = MagicMock()
        create_config.config = {'sync_databases_startup': True}

        with patch('atlas.gems.arch.worker.aur.is_supported', return_value=True):
            worker = SyncDatabases(
                taskman=taskman,
                root_password='root',
                i18n=MagicMock(),
                logger=Mock(),
                refresh_mirrors=refresh_mirrors,
                create_config=create_config
            )

            mock_get_dbs.return_value = ['core']

            p = MagicMock()
            p.stdout = []
            p.stderr = [b'error: failed']
            p.returncode = 1
            mock_subproc.return_value = p

            worker.run()

            mock_clear_caches.assert_not_called()
            mock_reg_sync.assert_not_called()
            self.assertFalse(worker.synchronized)


if __name__ == '__main__':
    unittest.main()
