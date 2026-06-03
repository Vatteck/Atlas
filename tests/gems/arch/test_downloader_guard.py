import unittest
from unittest.mock import Mock

from atlas.gems.arch.controller import ArchManager


class FileDownloaderGuardTest(unittest.TestCase):
    """The webview builds its ApplicationContext with file_downloader=None; the AUR install path
    must not crash on it (regression for the tuxracer install AttributeError)."""

    def setUp(self):
        self.mgr = ArchManager.__new__(ArchManager)  # skip heavy __init__
        self.mgr.logger = Mock()
        self.mgr.context = Mock()
        self.mgr.context.root_user = False
        self.mgr.context.file_downloader = None  # as the webview sets it

    def test_pre_download_source_skips_when_no_downloader(self):
        # Should return True (skip the optimization) without touching .SRCINFO or crashing.
        self.assertTrue(self.mgr._pre_download_source('tuxracer', '/nonexistent', Mock()))

    def test_multithreaded_download_disabled_when_no_downloader(self):
        # Even if the user enabled the config toggle, a missing downloader must not crash.
        self.assertFalse(self.mgr._multithreaded_download_enabled({'repositories_mthread_download': True}))


if __name__ == '__main__':
    unittest.main()
