from unittest import TestCase
from unittest.mock import MagicMock, patch

from atlas.gems.arch import native


class NativeFlagTest(TestCase):

    def test_flag__truthy_values(self):
        for value in ('1', 'true', 'TRUE', 'Yes', ' on ', 'On'):
            with patch.dict('os.environ', {'ATLAS_TEST_FLAG': value}, clear=False):
                self.assertTrue(native._flag('ATLAS_TEST_FLAG'), value)

    def test_flag__falsy_values(self):
        for value in ('', '0', 'false', 'no', 'off', 'maybe'):
            with patch.dict('os.environ', {'ATLAS_TEST_FLAG': value}, clear=False):
                self.assertFalse(native._flag('ATLAS_TEST_FLAG'), value)

    def test_flag__unset(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertFalse(native._flag('ATLAS_TEST_FLAG'))


class NativeLoadTest(TestCase):

    def test_load__returns_none_when_disabled(self):
        with patch.object(native, '_RS_DISABLED', True):
            self.assertIsNone(native.load())

    def test_load__returns_none_and_logs_on_import_error_when_debug(self):
        logger = MagicMock()
        with patch.object(native, '_RS_DISABLED', False), \
                patch.object(native, '_RS_DEBUG', True), \
                patch.dict('sys.modules', {'atlas_rs': None}):
            # sys.modules[name] = None makes "import atlas_rs" raise ImportError
            self.assertIsNone(native.load(logger))
        logger.warning.assert_called_once()
        self.assertTrue(logger.warning.call_args.kwargs.get('exc_info'))

    def test_load__import_error_is_silent_without_debug(self):
        logger = MagicMock()
        with patch.object(native, '_RS_DISABLED', False), \
                patch.object(native, '_RS_DEBUG', False), \
                patch.dict('sys.modules', {'atlas_rs': None}):
            self.assertIsNone(native.load(logger))
        logger.warning.assert_not_called()


class NativeReportTest(TestCase):

    def test_report_failure__logs_only_when_debug(self):
        logger = MagicMock()
        with patch.object(native, '_RS_DEBUG', False):
            native.report_failure(logger, 'map_missing_deps')
        logger.warning.assert_not_called()

        with patch.object(native, '_RS_DEBUG', True):
            native.report_failure(logger, 'map_missing_deps')
        logger.warning.assert_called_once()
        self.assertTrue(logger.warning.call_args.kwargs.get('exc_info'))

    def test_report_non_success__logs_only_when_debug(self):
        logger = MagicMock()
        with patch.object(native, '_RS_DEBUG', False):
            native.report_non_success(logger, 'map_missing_deps', 'needs_providers')
        logger.info.assert_not_called()

        with patch.object(native, '_RS_DEBUG', True):
            native.report_non_success(logger, 'map_missing_deps', 'needs_providers')
        logger.info.assert_called_once()

    def test_report_helpers__tolerate_missing_logger(self):
        with patch.object(native, '_RS_DEBUG', True):
            native.report_failure(None, 'op')          # must not raise
            native.report_non_success(None, 'op', 'x')  # must not raise
