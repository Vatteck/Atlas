"""Window-first startup contract (see docs/plans/2026-06-20-launch-optimization.md).

The window is shown before the backend manager is built; the build runs on a daemon thread and calls
`set_manager()`. `AtlasApi.manager` is a blocking property so any API call that lands early just
waits. If this contract breaks, the app fails to start — so guard it deterministically (no GUI).
"""
import threading
import time
import unittest
from unittest.mock import Mock

from atlas.view.webview.api import AtlasApi


class WindowFirstStartupTest(unittest.TestCase):
    def test_constructs_without_a_manager_and_reports_not_ready(self):
        api = AtlasApi(logger=Mock())
        self.assertFalse(api.is_backend_ready())

    def test_legacy_path_with_manager_is_ready_immediately(self):
        api = AtlasApi(Mock(), Mock())
        self.assertTrue(api.is_backend_ready())

    def test_manager_property_blocks_until_set_then_returns_it(self):
        api = AtlasApi(logger=Mock())
        mgr = Mock()

        def _set_after():
            time.sleep(0.05)
            api.set_manager(mgr)

        t = threading.Thread(target=_set_after)
        t.start()
        got = api.manager  # must block until set_manager() fires
        t.join()
        self.assertIs(got, mgr)
        self.assertTrue(api.is_backend_ready())

    def test_manager_property_does_not_block_once_ready(self):
        api = AtlasApi(logger=Mock())
        mgr = Mock()
        api.set_manager(mgr)
        # A bounded wait proves it returns promptly rather than blocking.
        result = {}

        def _read():
            result['m'] = api.manager
        t = threading.Thread(target=_read)
        t.start()
        t.join(timeout=2)
        self.assertFalse(t.is_alive(), "manager property blocked even though backend is ready")
        self.assertIs(result.get('m'), mgr)


if __name__ == '__main__':
    unittest.main()
