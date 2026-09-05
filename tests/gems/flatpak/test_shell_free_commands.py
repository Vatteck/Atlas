from unittest import TestCase
from unittest.mock import patch

from atlas import __app_name__
from atlas.gems.flatpak import flatpak


class FlatpakArgvTest(TestCase):

    def test_search__query_is_passed_as_an_argument_list(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.search(('1', '12'), 'gimp', 'user')

        self.assertEqual(['flatpak', 'search', 'gimp', '--user'], run_cmd.call_args.args[0])

    def test_search__shell_metacharacters_become_literal_argument_text(self):
        """The query is split on whitespace, as the shell already did (flatpak searches on the
        first term and ignores the rest), but every term is a literal argv element."""
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.search(('1', '12'), 'gimp; touch /tmp/pwned', 'user')

        self.assertEqual(['flatpak', 'search', 'gimp;', 'touch', '/tmp/pwned', '--user'],
                         run_cmd.call_args.args[0])

    def test_get_app_info__app_id_and_branch_are_separate_arguments(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.get_app_info('org.gimp.GIMP', 'stable', 'user')

        self.assertEqual(['flatpak', 'info', 'org.gimp.GIMP', 'stable', '--user'],
                         run_cmd.call_args.args[0])

    def test_get_commit__app_id_and_branch_are_separate_arguments(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.get_commit('org.gimp.GIMP', 'stable', 'user')

        self.assertEqual(['flatpak', 'info', 'org.gimp.GIMP', 'stable', '--user'],
                         run_cmd.call_args.args[0])

    def test_show_permissions__builds_an_argument_list(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.show_permissions('org.gimp.GIMP', 'stable', 'user')

        self.assertEqual(['flatpak', 'info', '--show-permissions', 'org.gimp.GIMP', 'stable',
                          '--user'], run_cmd.call_args.args[0])

    def test_show_permissions__omits_a_missing_branch_and_installation(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='') as run_cmd:
            flatpak.show_permissions('org.gimp.GIMP', '', None)

        self.assertEqual(['flatpak', 'info', '--show-permissions', 'org.gimp.GIMP'],
                         run_cmd.call_args.args[0])

    def test_get_app_commits_data__ref_and_origin_are_separate_arguments(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.run_cmd', return_value='Commit: x') as run_cmd:
            flatpak.get_app_commits_data('app/org.gimp.GIMP/x86_64/stable', 'flathub', 'user')

        self.assertEqual(['flatpak', 'remote-info', '--log', 'flathub',
                          'app/org.gimp.GIMP/x86_64/stable', '--user'], run_cmd.call_args.args[0])
