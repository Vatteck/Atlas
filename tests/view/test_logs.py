import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from atlas.view.util import logs


class NewLoggerTest(TestCase):

    def _fresh_logger(self, name, enabled, logdir):
        logfile = os.path.join(logdir, 'logs', 'atlas.log')
        with patch.object(logs, 'APP_LOG_DIR', os.path.dirname(logfile)), \
                patch.object(logs, 'APP_LOG_FILE', logfile):
            return logs.new_logger(name, enabled=enabled), logfile

    def test_persists_to_rotating_file_even_without_logs_flag(self):
        with tempfile.TemporaryDirectory() as d:
            logger, logfile = self._fresh_logger('atlastest', enabled=False, logdir=d)
            try:
                # not disabled: the file handler keeps the logger live even with --logs off
                self.assertFalse(logger.disabled)
                logger.error('hello-from-test')
                for h in logger.handlers:
                    h.flush()
                with open(logfile, encoding='utf-8') as f:
                    self.assertIn('hello-from-test', f.read())
            finally:
                for h in list(logger.handlers):
                    h.close()
                    logger.removeHandler(h)

    def test_disabled_only_when_no_file_handler_and_not_enabled(self):
        # If the file handler can't be created and --logs is off, stay silent (old behaviour);
        # but with --logs on, the stream handler keeps it enabled.
        with patch.object(logs, '_file_handler', return_value=None):
            self.assertTrue(logs.new_logger('atlastest_off', enabled=False).disabled)
            self.assertFalse(logs.new_logger('atlastest_on', enabled=True).disabled)
