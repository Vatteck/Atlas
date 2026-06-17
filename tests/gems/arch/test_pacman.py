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


class FindExplicitRootsTest(TestCase):
    """find_explicit_roots: attribute a pulled-in dependency to the explicit package(s) that
    dragged it in (the "Why is this installed?" backend walk). Pure via injected deps."""

    @staticmethod
    def _rb(adj):
        # required_by_fn: given a list of names, return {name: reverse-dep set} from the adjacency.
        return lambda names: {n: set(adj.get(n, set())) for n in names}

    def test_single_explicit_root(self):
        adj = {'libfoo': {'libbar'}, 'libbar': {'app'}}
        roots = pacman.find_explicit_roots('libfoo', self._rb(adj), explicit={'app'})
        self.assertEqual(['app'], roots)

    def test_multiple_roots_sorted(self):
        adj = {'libfoo': {'a', 'b'}, 'b': {'c'}}
        roots = pacman.find_explicit_roots('libfoo', self._rb(adj), explicit={'a', 'c'})
        self.assertEqual(['a', 'c'], roots)

    def test_stops_at_first_explicit(self):
        # mid is explicit; the walk must not climb past it to 'higher'.
        adj = {'libfoo': {'mid'}, 'mid': {'higher'}}
        roots = pacman.find_explicit_roots('libfoo', self._rb(adj), explicit={'mid', 'higher'})
        self.assertEqual(['mid'], roots)

    def test_no_parents_returns_empty(self):
        roots = pacman.find_explicit_roots('libfoo', self._rb({'libfoo': set()}), explicit={'app'})
        self.assertEqual([], roots)

    def test_cycle_terminates(self):
        adj = {'libfoo': {'x'}, 'x': {'libfoo'}}  # nothing explicit, mutual requirement
        roots = pacman.find_explicit_roots('libfoo', self._rb(adj), explicit=set())
        self.assertEqual([], roots)

    def test_max_visited_bounds_the_walk(self):
        # a long chain; cap visited so we never run away
        adj = {f'n{i}': {f'n{i+1}'} for i in range(100)}
        roots = pacman.find_explicit_roots('n0', self._rb(adj), explicit={'n99'}, max_visited=5)
        self.assertEqual([], roots)  # 'n99' is beyond the cap → not reached

    def test_fail_open_on_error(self):
        def boom(_names):
            raise RuntimeError('pacman exploded')
        self.assertEqual([], pacman.find_explicit_roots('libfoo', boom, explicit={'app'}))

    def test_empty_name(self):
        self.assertEqual([], pacman.find_explicit_roots('', self._rb({}), explicit={'app'}))
