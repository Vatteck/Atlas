"""End-to-end parity: native parse_pacman_info vs the pure-Python fallback.

Mocks `run_cmd` so no real pacman is needed, then runs `map_updates_data` once with the
native path enabled and once with it force-disabled (ATLAS_DISABLE_RS), asserting the
results are identical. This is the faithful drop-in check — same public function, real
fallback, real set conversion.
"""

from unittest import TestCase, skipUnless
from unittest.mock import patch

from atlas.gems.arch import pacman, native

try:
    from atlas.gems.arch import atlas_rs  # noqa: F401
    NATIVE_AVAILABLE = True
except ImportError:
    NATIVE_AVAILABLE = False


# Realistic multi-package `pacman -Si` output: multiline depends, versioned provides,
# None fields, conflicts, sizes in different units, and trailing fields (Build Date /
# Validated By) that the Python parser relies on to commit each package.
SI_OUTPUT = """Repository      : extra
Name            : yakuake
Version         : 24.02.2-1
Description     : A drop-down terminal emulator based on KDE Konsole technology
Architecture    : x86_64
URL             : https://kde.org/
Licenses        : GPL-2.0-or-later
Groups          : None
Provides        : dropdown-terminal  yakuake-abi=24.02
Depends On      : konsole  kcoreaddons  kglobalaccel
                  kdbusaddons  knotifications
Optional Deps   : None
Conflicts With  : None
Replaces        : None
Download Size   :   1024.50 KiB
Installed Size  :   2048.00 KiB
Build Date      : Tue 01 Jan 2024 10:00:00
Validated By    : SHA-256 Sum

Repository      : extra
Name            : konsole
Version         : 24.02.2-1
Description     : KDE's terminal emulator
Architecture    : x86_64
URL             : https://kde.org/
Licenses        : GPL-2.0-or-later
Groups          : None
Provides        : None
Depends On      : None
Conflicts With  : kdebase  oldkonsole
Download Size   :   512.00 KiB
Installed Size  :   3.50 MiB
Build Date      : Tue 01 Jan 2024 10:00:00
Validated By    : SHA-256 Sum
"""


@skipUnless(NATIVE_AVAILABLE, "atlas_rs not built; cannot verify native vs python parity")
class PacmanInfoParityTest(TestCase):

    def _run(self, disabled: bool, description: bool):
        with patch.object(native, '_RS_DISABLED', disabled), \
                patch.object(pacman, 'run_cmd', return_value=SI_OUTPUT):
            return pacman.map_updates_data(['yakuake', 'konsole'], description=description)

    def test_parity_with_description(self):
        native_res = self._run(disabled=False, description=True)
        python_res = self._run(disabled=True, description=True)
        self.assertEqual(native_res, python_res)
        # sanity: both parsed both packages with the expected schema
        self.assertEqual(set(native_res), {'yakuake', 'konsole'})
        self.assertEqual(native_res['konsole']['des'], "KDE's terminal emulator")

    def test_parity_without_description(self):
        native_res = self._run(disabled=False, description=False)
        python_res = self._run(disabled=True, description=False)
        self.assertEqual(native_res, python_res)
        self.assertIsNone(native_res['yakuake']['des'])

    def test_expected_values(self):
        """Pin a few concrete values so a regression in either path is caught even if
        both drifted together."""
        res = self._run(disabled=False, description=True)
        yakuake = res['yakuake']
        self.assertEqual(yakuake['r'], 'extra')
        self.assertEqual(yakuake['v'], '24.02.2-1')
        self.assertEqual(yakuake['ds'], 1024.50 * 1024)
        self.assertEqual(yakuake['s'], 2048.00 * 1024)
        self.assertIsInstance(yakuake['d'], set)
        self.assertEqual(yakuake['d'],
                         {'konsole', 'kcoreaddons', 'kglobalaccel', 'kdbusaddons', 'knotifications'})
        # provides carries the package's own name and name=version
        self.assertIn('yakuake', yakuake['p'])
        self.assertIn('yakuake=24.02.2-1', yakuake['p'])
        self.assertIn('yakuake-abi', yakuake['p'])  # base name of versioned provide
        # konsole: None depends, real conflicts
        self.assertIsNone(res['konsole']['d'])
        self.assertEqual(res['konsole']['c'], {'kdebase', 'oldkonsole'})
