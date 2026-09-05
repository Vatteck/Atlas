import warnings
from unittest import TestCase
from unittest.mock import patch, Mock

from atlas import __app_name__
from atlas.gems.arch import pacman, sshell, git


class ArchExecuteArgvTest(TestCase):

    @classmethod
    def setUpClass(cls):
        warnings.filterwarnings('ignore', category=DeprecationWarning)

    def test_list_hard_requirements__package_name_is_a_single_argument(self):
        with patch(f'{__app_name__}.gems.arch.pacman.system.execute',
                   return_value=(0, '')) as execute:
            pacman.list_hard_requirements('evil; touch /tmp/pwned')

        self.assertEqual(['pacman', '-Rc', 'evil; touch /tmp/pwned', '--print-format=%n'],
                         execute.call_args.args[0])

    def test_list_hard_requirements__assume_installed_providers_are_separate_arguments(self):
        with patch(f'{__app_name__}.gems.arch.pacman.system.execute',
                   return_value=(0, '')) as execute:
            pacman.list_hard_requirements('firefox', assume_installed={'libfoo'})

        self.assertEqual(['pacman', '-Rc', 'firefox', '--print-format=%n',
                          '--assume-installed=libfoo'], execute.call_args.args[0])

    def test_map_packages__package_names_are_separate_arguments(self):
        with patch(f'{__app_name__}.gems.arch.pacman.system.execute',
                   return_value=(0, '')) as execute:
            pacman.map_packages(names={'evil; touch /tmp/pwned'}, remote=False, skip_ignored=True)

        self.assertEqual(['pacman', '-Qi', 'evil; touch /tmp/pwned'], execute.call_args.args[0])

    def test_mkdir__directory_path_is_a_single_argument(self):
        with patch(f'{__app_name__}.gems.arch.sshell.execute',
                   return_value=(0, '')) as execute:
            sshell.mkdir('/tmp/a b/$(touch /tmp/pwned)')

        self.assertEqual(['mkdir', '-p', '/tmp/a b/$(touch /tmp/pwned)'], execute.call_args.args[0])

    def test_mkdir__without_parent_drops_the_flag(self):
        with patch(f'{__app_name__}.gems.arch.sshell.execute',
                   return_value=(0, '')) as execute:
            sshell.mkdir('/tmp/a', parent=False)

        self.assertEqual(['mkdir', '/tmp/a'], execute.call_args.args[0])

    def test_list_commits__runs_without_a_shell(self):
        with patch(f'{__app_name__}.gems.arch.git.system.execute',
                   return_value=(0, '')) as execute:
            git.list_commits('/tmp/proj', limit=5)

        self.assertEqual(['git', 'log', '--format=%H %ct', '-5'], execute.call_args.args[0])
        self.assertNotIn('shell', execute.call_args.kwargs)
