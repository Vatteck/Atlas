import json
import os
import tempfile
import unittest
from unittest.mock import patch

from atlas.view.webview import activity_log


class ActivityLogClearExportTest(unittest.TestCase):
    """The History page's Clear/Export actions operate on the local activity JSONL."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp.name, 'activity.jsonl')
        self.export_path = os.path.join(self.tmp.name, 'export.json')
        self._patches = [
            patch.object(activity_log, 'LOG_FILE', self.log_path),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def _seed(self, n=3):
        with open(self.log_path, 'w', encoding='utf-8') as f:
            for i in range(n):
                f.write(json.dumps({'timestamp': f'2026-06-0{i+1}T00:00:00', 'action': 'install',
                                    'pkg_name': f'p{i}', 'pkg_type': 'arch_repo', 'success': True,
                                    'error': None}) + '\n')

    def test_clear_removes_file(self):
        self._seed()
        self.assertTrue(os.path.exists(self.log_path))
        self.assertTrue(activity_log.clear_activity_log())
        self.assertFalse(os.path.exists(self.log_path))
        self.assertEqual([], activity_log.get_activity_log())

    def test_clear_missing_file_is_ok(self):
        # Nothing to clear is still success (idempotent).
        self.assertFalse(os.path.exists(self.log_path))
        self.assertTrue(activity_log.clear_activity_log())

    def test_export_writes_all_entries_newest_first(self):
        self._seed(3)
        path = activity_log.export_activity_log(self.export_path)
        self.assertEqual(self.export_path, path)
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(1, payload['version'])
        self.assertEqual(3, payload['count'])
        self.assertEqual(3, len(payload['activity']))
        # get_activity_log returns newest-first; the export preserves that order.
        self.assertEqual('p2', payload['activity'][0]['pkg_name'])

    def test_export_empty_log(self):
        path = activity_log.export_activity_log(self.export_path)
        with open(path, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(0, payload['count'])
        self.assertEqual([], payload['activity'])


if __name__ == '__main__':
    unittest.main()

class ActivityLogCapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp.name, 'activity.jsonl')
        self._patches = [
            patch.object(activity_log, 'LOG_FILE', self.log_path),
            patch.object(activity_log, 'MAX_ACTIVITY_ENTRIES', 3),
            patch.object(activity_log, 'COMPACT_EVERY_WRITES', 1),
        ]
        for p in self._patches:
            p.start()
        activity_log._write_count = 0

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def test_record_activity_caps_newest_entries(self):
        for i in range(5):
            activity_log.record_activity('install', f'p{i}', 'arch_repo', True)
        entries = activity_log.get_activity_log(limit=10)
        self.assertEqual(['p4', 'p3', 'p2'], [e['pkg_name'] for e in entries])
        with open(self.log_path, encoding='utf-8') as f:
            self.assertEqual(3, len([ln for ln in f if ln.strip()]))
