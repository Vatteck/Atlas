import os
import tempfile
import unittest

from atlas.commons.config import YAMLConfigManager


class _TmpConfigManager(YAMLConfigManager):
    """A throwaway manager so we can point at a temp file (ArchConfigManager hard-codes its path)."""

    def get_default_config(self) -> dict:
        return {'optimize': True, 'suggestions_exp': 24}


class YAMLConfigManagerTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix='.yml')
        os.close(fd)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _write(self, text: str):
        with open(self.path, 'w') as f:
            f.write(text)

    # --- the trap that caused the _fill_suggestions crash --------------------------------------
    def test_read_config_returns_none_for_empty_file(self):
        self._write('')  # empty / yaml.safe_load -> None
        self.assertIsNone(_TmpConfigManager(self.path).read_config())

    def test_read_config_returns_none_for_null_file(self):
        self._write('null\n')
        self.assertIsNone(_TmpConfigManager(self.path).read_config())

    # --- get_config() is the safe call: never None, defaults always present --------------------
    def test_get_config_falls_back_to_defaults_for_empty_file(self):
        self._write('')
        config = _TmpConfigManager(self.path).get_config()
        self.assertEqual(24, config['suggestions_exp'])  # would KeyError/TypeError before the fix

    def test_get_config_merges_partial_file_over_defaults(self):
        self._write('suggestions_exp: 5\n')
        config = _TmpConfigManager(self.path).get_config()
        self.assertEqual(5, config['suggestions_exp'])  # user value wins
        self.assertTrue(config['optimize'])              # default still present

    def test_get_config_returns_defaults_when_file_missing(self):
        os.remove(self.path)
        config = _TmpConfigManager(self.path).get_config()
        self.assertEqual(24, config['suggestions_exp'])


if __name__ == '__main__':
    unittest.main()
