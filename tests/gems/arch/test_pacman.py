import os
import warnings
from unittest import TestCase
from unittest.mock import patch, Mock

from atlas import __app_name__
from atlas.gems.arch import pacman

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class PacmanTest(TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    def test_list_ignored_packages(self):
        ignored = pacman.list_ignored_packages(FILE_DIR + '/resources/pacman_ign_pkgs.conf')

        self.assertIsNotNone(ignored)
        self.assertEqual(2, len(ignored))
        self.assertIn('google-chrome', ignored)
        self.assertIn('firefox', ignored)

    def test_list_ignored_packages__no_ignored_packages(self):
        ignored = pacman.list_ignored_packages(FILE_DIR + '/resources/pacman.conf')

        self.assertIsNotNone(ignored)
        self.assertEqual(0, len(ignored))

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : lib32-vulkan-icd-loader: Vulkan support [installed]
Required By     : None
            """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_installed_with_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : lib32-vulkan-icd-loader: Vulkan support
Required By     : None
        """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_not_installed_with_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {'lib32-vulkan-icd-loader': 'Vulkan support'}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : pipewire-alsa
Required By     : None
            """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_not_installed_no_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {'pipewire-alsa': ''}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd
Optional Deps   : pipewire-alsa [installed]
Required By     : None
                """)
    def test_map_optional_deps__no_remote_and_not_installed__only_one_installed_no_description(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {}}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="""
Name            : package-test
Version         : 3.4.4-1
Description     : Test
Depends On      : embree  freetype2  libglvnd  libtheora
Optional Deps   : pipewire-alsa
                  pipewire-pulse [installed]
                  pipewire
                  lib32-vulkan-icd-loader: Vulkan support [installed]
Required By     : None
    """)
    def test_map_optional_deps__no_remote_and_not_installed__several(self, run_cmd: Mock):
        res = pacman.map_optional_deps(('package-test',), remote=False, not_installed=True)
        run_cmd.assert_called_once_with('pacman -Qi package-test')
        self.assertEqual({'package-test': {'pipewire-alsa': '', 'pipewire': ''}}, res)

    # `pacman -Si <names>` prints one block per matching package. A package present in
    # more than one enabled repo yields multiple blocks, so the number of size lines can
    # exceed the number of requested names. The old positional pkgs[idx] pairing raised
    # IndexError in that case (the gimp-optdeps crash); map by Name block instead.
    _SI_OUTPUT_MORE_BLOCKS_THAN_NAMES = """Repository      : extra
Name            : gutenprint
Version         : 5.3.4-5
Installed Size  : 34.20 MiB
Download Size   : 6.50 MiB

Repository      : extra
Name            : ghostscript
Version         : 10.04.0-1
Installed Size  : 44.03 MiB
Download Size   : 16.00 MiB

Repository      : extra-testing
Name            : ghostscript
Version         : 10.05.0-1
Installed Size  : 44.10 MiB
Download Size   : 16.10 MiB
"""

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value=_SI_OUTPUT_MORE_BLOCKS_THAN_NAMES)
    def test_map_update_sizes__more_blocks_than_names_does_not_raise(self, run_cmd: Mock):
        # two names requested, three blocks returned (ghostscript in two repos)
        sizes = pacman.map_update_sizes(['gutenprint', 'ghostscript'])

        self.assertEqual({'gutenprint', 'ghostscript'}, set(sizes.keys()))
        self.assertEqual(pacman.size_to_byte('34.20', 'MiB'), sizes['gutenprint'])
        # last matching block wins; either ghostscript size is acceptable, just not a crash
        self.assertEqual(pacman.size_to_byte('44.10', 'MiB'), sizes['ghostscript'])

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value=_SI_OUTPUT_MORE_BLOCKS_THAN_NAMES)
    def test_map_download_sizes__maps_by_name_block(self, run_cmd: Mock):
        sizes = pacman.map_download_sizes(['gutenprint', 'ghostscript'])

        self.assertEqual(pacman.size_to_byte('6.50', 'MiB'), sizes['gutenprint'])
        self.assertEqual(pacman.size_to_byte('16.10', 'MiB'), sizes['ghostscript'])

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="")
    def test_map_update_sizes__empty_output(self, run_cmd: Mock):
        self.assertEqual({}, pacman.map_update_sizes(['gutenprint']))
