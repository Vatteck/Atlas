"""Correctness of the pure-Python `pacman -Si` parser (pacman._parse_info_output_py)."""

from unittest import TestCase

from atlas.gems.arch.pacman import _parse_info_output_py


# Multi-package `pacman -Si` output: multiline depends, versioned provides, None fields,
# conflicts, sizes in different units, and trailing fields (Build Date / Validated By)
# that the parser relies on to commit each package.
SI_OUTPUT = """Repository      : extra
Name            : yakuake
Version         : 24.02.2-1
Description     : A drop-down terminal emulator based on KDE Konsole technology
Architecture    : x86_64
Provides        : dropdown-terminal  yakuake-abi=24.02
Depends On      : konsole  kcoreaddons  kglobalaccel
                  kdbusaddons  knotifications
Optional Deps   : None
Conflicts With  : None
Download Size   :   1024.50 KiB
Installed Size  :   2048.00 KiB
Build Date      : Tue 01 Jan 2024 10:00:00
Validated By    : SHA-256 Sum

Repository      : extra
Name            : konsole
Version         : 24.02.2-1
Description     : KDE's terminal emulator
Provides        : None
Depends On      : None
Conflicts With  : kdebase  oldkonsole
Download Size   :   512.00 KiB
Installed Size  :   3.50 MiB
Build Date      : Tue 01 Jan 2024 10:00:00
Validated By    : SHA-256 Sum
"""


class ParseInfoOutputTest(TestCase):

    def test_parses_both_packages(self):
        res = _parse_info_output_py(SI_OUTPUT, description=True)
        self.assertEqual(set(res), {'yakuake', 'konsole'})

    def test_yakuake_fields(self):
        res = _parse_info_output_py(SI_OUTPUT, description=True)
        y = res['yakuake']
        self.assertEqual(y['r'], 'extra')
        self.assertEqual(y['v'], '24.02.2-1')
        self.assertEqual(y['des'], 'A drop-down terminal emulator based on KDE Konsole technology')
        self.assertEqual(y['ds'], 1024.50 * 1024)
        self.assertEqual(y['s'], 2048.00 * 1024)
        self.assertEqual(y['d'], {'konsole', 'kcoreaddons', 'kglobalaccel', 'kdbusaddons', 'knotifications'})
        # provides carries the package's own name and name=version plus base of versioned
        self.assertIn('yakuake', y['p'])
        self.assertIn('yakuake=24.02.2-1', y['p'])
        self.assertIn('yakuake-abi', y['p'])

    def test_none_and_conflicts(self):
        res = _parse_info_output_py(SI_OUTPUT, description=True)
        self.assertIsNone(res['konsole']['d'])
        self.assertEqual(res['konsole']['c'], {'kdebase', 'oldkonsole'})

    def test_description_flag_off(self):
        res = _parse_info_output_py(SI_OUTPUT, description=False)
        self.assertIsNone(res['yakuake']['des'])
