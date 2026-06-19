import unittest
from unittest.mock import patch

from atlas import self_check


class SelfCheckTest(unittest.TestCase):
    def test_gather_returns_expected_keys_and_never_raises(self):
        info = self_check.gather()
        self.assertIsInstance(info, dict)
        for key in ('Atlas version', 'Python', 'Platform', 'Desktop', 'Session type',
                    'Tray (AppIndicator/SNI)', 'Terminal (pacdiff)', 'pacman'):
            self.assertIn(key, info)
        self.assertTrue(all(isinstance(v, str) for v in info.values()))

    def test_which_any_picks_first_present(self):
        with patch('atlas.self_check.shutil.which', side_effect=lambda n: '/usr/bin/yay' if n == 'yay' else None):
            self.assertEqual('yay (/usr/bin/yay)', self_check._which_any('paru', 'yay'))

    def test_which_any_none_present(self):
        with patch('atlas.self_check.shutil.which', return_value=None):
            self.assertEqual('', self_check._which_any('paru', 'yay'))

    def test_run_prints_and_returns_zero(self):
        with patch('builtins.print') as p:
            rc = self_check.run()
        self.assertEqual(0, rc)
        self.assertTrue(p.called)


if __name__ == '__main__':
    unittest.main()
