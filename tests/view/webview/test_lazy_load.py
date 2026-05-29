import unittest
from unittest.mock import Mock, patch
from concurrent.futures import Future

from atlas.view.core.controller import GenericSoftwareManager
from atlas.view.webview.api import BauhApi
from atlas.api.abstract.handler import TaskManager
from atlas.api.abstract.controller import SearchResult


class TestLazyLoadAndThreadPool(unittest.TestCase):

    def test_lazy_initialization_on_demand(self):
        # Create mock managers
        mock_sub_manager = Mock()
        mock_sub_manager.get_managed_types.return_value = {"Flatpak"}
        mock_sub_manager.is_enabled.return_value = True
        mock_sub_manager.can_work.return_value = (True, None)

        context = Mock()
        context.is_internet_available.return_value = True
        context.i18n = {}

        # Initialize GenericSoftwareManager
        manager = GenericSoftwareManager(
            managers=[mock_sub_manager],
            context=context,
            config={'system': {'single_dependency_checking': False}}
        )

        # Call prepare eagerly (fast config step)
        taskman = TaskManager()
        with patch('atlas.view.core.controller.CreateConfigFile') as mock_create_config_cls:
            mock_config_instance = Mock()
            mock_create_config_cls.return_value = mock_config_instance
            manager.prepare(taskman, "password", True)
            
            # Verify CreateConfigFile was started and joined
            mock_config_instance.start.assert_called_once()
            mock_config_instance.join.assert_called_once()

        # The eager prepare must NOT have prepared mock_sub_manager
        mock_sub_manager.prepare.assert_not_called()

        # Now, call a method that triggers _can_work, e.g., get_working_managers() or _can_work()
        can_work = manager._can_work(mock_sub_manager)
        self.assertTrue(can_work)

        # Verify that mock_sub_manager was prepared lazily/on-demand
        mock_sub_manager.prepare.assert_called_once()

        # Call it again to verify it is NOT prepared multiple times (prepared exactly once)
        mock_sub_manager.prepare.reset_mock()
        manager._can_work(mock_sub_manager)
        mock_sub_manager.prepare.assert_not_called()

    def test_bauh_api_uses_threadpool_executor(self):
        manager = Mock()
        logger = Mock()

        # Initialize BauhApi and verify that ThreadPoolExecutor is used to schedule background tasks
        with patch('atlas.view.webview.api.ThreadPoolExecutor') as mock_executor_cls:
            mock_executor = Mock()
            mock_executor_cls.return_value = mock_executor
            mock_future = Mock(spec=Future)
            mock_executor.submit.return_value = mock_future

            api = BauhApi(manager, logger)

            # Ensure the ThreadPoolExecutor was instantiated and self._prepare_manager was submitted
            mock_executor_cls.assert_called_once_with(max_workers=5)
            mock_executor.submit.assert_called_once_with(api._prepare_manager)
            self.assertEqual(api._prepare_future, mock_future)
