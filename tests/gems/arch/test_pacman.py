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


_QI_OPTFOR = """Name            : libfoo
Version         : 1.0-1
Required By     : None
Optional For    : appbar  appbaz
Conflicts With  : None

Name            : libbar
Version         : 2.0-1
Required By     : someapp
Optional For    : None
Conflicts With  : None
"""


class OptionalForTest(TestCase):
    """map_optional_for / map_required_by share a parser; verify both fields parse from one block."""

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value=_QI_OPTFOR)
    def test_map_optional_for_parses_field(self, run_cmd: Mock):
        res = pacman.map_optional_for(['libfoo', 'libbar'])
        self.assertEqual({'appbar', 'appbaz'}, res['libfoo'])
        self.assertEqual(set(), res['libbar'])  # 'None' → empty

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value=_QI_OPTFOR)
    def test_map_required_by_still_parses_after_refactor(self, run_cmd: Mock):
        res = pacman.map_required_by(['libfoo', 'libbar'])
        self.assertEqual(set(), res['libfoo'])           # Required By: None
        self.assertEqual({'someapp'}, res['libbar'])

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value="")
    def test_empty_output_falls_back_to_empty_sets(self, run_cmd: Mock):
        self.assertEqual({'x': set()}, pacman.map_optional_for(['x']))


class RepositoryUpdatesTest(TestCase):

    def test_parse_repository_updates(self):
        out = "alsa-lib 1.2.15-2 -> 1.2.16-1\nfirefox 151.0-1 -> 152.0-1\n"
        self.assertEqual({'alsa-lib': '1.2.16-1', 'firefox': '152.0-1'},
                         pacman.parse_repository_updates(out))

    def test_parse_repository_updates_empty_and_junk(self):
        self.assertEqual({}, pacman.parse_repository_updates(''))
        self.assertEqual({}, pacman.parse_repository_updates(None))
        # blank lines are skipped; a lone token still records the name
        self.assertEqual({'pkg': 'pkg'}, pacman.parse_repository_updates('\n  \npkg\n'))

    @patch(f'{__app_name__}.gems.arch.pacman.shutil.which', return_value='/usr/bin/checkupdates')
    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    def test_prefers_checkupdates_when_available(self, new_subprocess: Mock, which: Mock):
        proc = Mock()
        proc.communicate.return_value = (b'firefox 151.0-1 -> 152.0-1\n', b'')
        proc.returncode = 0
        new_subprocess.return_value = proc
        with patch(f'{__app_name__}.gems.arch.pacman.run_cmd') as run_cmd:
            self.assertEqual({'firefox': '152.0-1'}, pacman.list_repository_updates())
            run_cmd.assert_not_called()  # checkupdates won → no fallback to pacman -Qu

    @patch(f'{__app_name__}.gems.arch.pacman.shutil.which', return_value='/usr/bin/checkupdates')
    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    def test_checkupdates_exit2_is_no_updates_not_fallback(self, new_subprocess: Mock, which: Mock):
        proc = Mock()
        proc.communicate.return_value = (b'', b'')
        proc.returncode = 2  # no updates — success, empty
        new_subprocess.return_value = proc
        with patch(f'{__app_name__}.gems.arch.pacman.run_cmd') as run_cmd:
            self.assertEqual({}, pacman.list_repository_updates())
            run_cmd.assert_not_called()

    @patch(f'{__app_name__}.gems.arch.pacman.shutil.which', return_value=None)
    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value='vim 9.2-1 -> 9.3-1\n')
    def test_falls_back_to_pacman_qu_when_checkupdates_absent(self, run_cmd: Mock, which: Mock):
        self.assertEqual({'vim': '9.3-1'}, pacman.list_repository_updates())
        run_cmd.assert_called_once()

    @patch(f'{__app_name__}.gems.arch.pacman.shutil.which', return_value='/usr/bin/checkupdates')
    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd', return_value='vim 9.2-1 -> 9.3-1\n')
    def test_falls_back_on_checkupdates_error(self, run_cmd: Mock, new_subprocess: Mock, which: Mock):
        proc = Mock()
        proc.communicate.return_value = (b'some error', b'')
        proc.returncode = 1  # error (e.g. offline) → fall back to pacman -Qu
        new_subprocess.return_value = proc
        self.assertEqual({'vim': '9.3-1'}, pacman.list_repository_updates())
        run_cmd.assert_called_once()


class PacmanCacheTest(TestCase):

    def setUp(self):
        pacman.clear_caches()

    def tearDown(self):
        pacman.clear_caches()

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd')
    def test_list_installed_names_caching(self, run_cmd: Mock):
        run_cmd.return_value = "pkg1\npkg2\n"

        # First call, should call run_cmd
        res1 = pacman.list_installed_names()
        self.assertEqual({"pkg1", "pkg2"}, res1)
        run_cmd.assert_called_once_with('pacman -Qq', print_error=False)

        # Second call, should return cached value and not call run_cmd again
        run_cmd.reset_mock()
        res2 = pacman.list_installed_names()
        self.assertEqual({"pkg1", "pkg2"}, res2)
        run_cmd.assert_not_called()

        # Clear caches, should query again
        pacman.clear_caches()
        run_cmd.reset_mock()
        res3 = pacman.list_installed_names()
        self.assertEqual({"pkg1", "pkg2"}, res3)
        run_cmd.assert_called_once_with('pacman -Qq', print_error=False)

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd')
    def test_list_explicit_names_caching(self, run_cmd: Mock):
        run_cmd.return_value = "pkg1\n"

        res1 = pacman.list_explicit_names()
        self.assertEqual({"pkg1"}, res1)
        run_cmd.assert_called_once_with('pacman -Qeq', print_error=False)

        run_cmd.reset_mock()
        res2 = pacman.list_explicit_names()
        self.assertEqual({"pkg1"}, res2)
        run_cmd.assert_not_called()

    @patch(f'{__app_name__}.gems.arch.pacman.run_cmd')
    def test_map_provided_caching(self, run_cmd: Mock):
        run_cmd.return_value = """Name            : pkg1
Version         : 1.0
Provides        : prov1  prov2
"""

        # Full query, should query and cache (local)
        res1 = pacman.map_provided(remote=False, pkgs=None)
        self.assertIn("pkg1", res1)
        run_cmd.assert_called_once_with('pacman -Qi')

        # Second full query, should hit cache
        run_cmd.reset_mock()
        res2 = pacman.map_provided(remote=False, pkgs=None)
        self.assertEqual(res1, res2)
        run_cmd.assert_not_called()

        # Query with pkgs specified should query directly and bypass cache, and not touch cache
        run_cmd.reset_mock()
        run_cmd.return_value = """Name            : pkg2
Version         : 2.0
Provides        : None
"""
        res_specific = pacman.map_provided(remote=False, pkgs=["pkg2"])
        run_cmd.assert_called_once_with('pacman -Qi pkg2')
        self.assertIn("pkg2", res_specific)

        # Next full query should still hit cache and return original
        run_cmd.reset_mock()
        res3 = pacman.map_provided(remote=False, pkgs=None)
        self.assertEqual(res1, res3)
        run_cmd.assert_not_called()



class MapDesktopFilesTest(TestCase):
    """map_desktop_files streams `pacman -Ql` line by line (the full output over every
    installed package is tens of MB — buffering it drove the cold-start memory spike,
    see docs/plans/2026-07-17-memory-baseline.md)."""

    class _FakeStdout:
        """Like a Popen stdout pipe: its own context manager, iterable by line."""
        def __init__(self, lines):
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            return iter(self._lines)

    @classmethod
    def _proc_with_lines(cls, lines):
        proc = Mock()
        proc.stdout = cls._FakeStdout(lines)
        proc.wait = Mock(return_value=0)
        return proc

    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    def test_map_desktop_files__maps_only_desktop_lines(self, new_subprocess: Mock):
        new_subprocess.return_value = self._proc_with_lines([
            b'firefox /usr/bin/firefox\n',
            b'firefox /usr/share/applications/firefox.desktop\n',
            b'zlib /usr/lib/libz.so\n',
            b'gimp /usr/share/applications/gimp.desktop\n',
            b'gimp /usr/share/applications/gimp-extra.desktop\n',
        ])
        res = pacman.map_desktop_files('firefox', 'zlib', 'gimp')
        new_subprocess.assert_called_once_with(['pacman', '-Ql', 'firefox', 'zlib', 'gimp'])
        self.assertEqual({'firefox': ['/usr/share/applications/firefox.desktop'],
                          'gimp': ['/usr/share/applications/gimp.desktop',
                                   '/usr/share/applications/gimp-extra.desktop']}, res)

    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    def test_map_desktop_files__no_args_no_subprocess(self, new_subprocess: Mock):
        self.assertEqual({}, pacman.map_desktop_files())
        new_subprocess.assert_not_called()

    @patch(f'{__app_name__}.gems.arch.pacman.new_subprocess')
    def test_map_desktop_files__undecodable_bytes_do_not_crash(self, new_subprocess: Mock):
        new_subprocess.return_value = self._proc_with_lines([
            b'bad \xff\xfe line\n',
            b'ok /usr/share/applications/ok.desktop\n',
        ])
        self.assertEqual({'ok': ['/usr/share/applications/ok.desktop']}, pacman.map_desktop_files('ok', 'bad'))
