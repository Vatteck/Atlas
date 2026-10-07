from unittest import TestCase
from unittest.mock import patch, Mock

from atlas import __app_name__
from atlas.commons.system import run_cmd


class RunCmdArgumentListTest(TestCase):

    def test_run_cmd__string_command_still_runs_through_a_shell(self):
        with patch(f'{__app_name__}.commons.system.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout=b'')
            run_cmd('echo hi')

        self.assertTrue(run.call_args.kwargs['shell'])
        self.assertEqual('echo hi', run.call_args.args[0])

    def test_run_cmd__sequence_command_does_not_run_through_a_shell(self):
        with patch(f'{__app_name__}.commons.system.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout=b'')
            run_cmd(['echo', 'hi'])

        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertEqual(['echo', 'hi'], run.call_args.args[0])

    def test_run_cmd__sequence_command_with_custom_user_builds_a_runuser_argument_list(self):
        with patch(f'{__app_name__}.commons.system.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout=b'')
            run_cmd(['pacman', '-Ss', 'firefox'], custom_user='builder')

        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertEqual(['runuser', '-u', 'builder', '--', 'pacman', '-Ss', 'firefox'],
                         run.call_args.args[0])

    def test_run_cmd__sequence_command_passes_shell_metacharacters_as_literal_text(self):
        output = run_cmd(['echo', 'firefox; touch /tmp/atlas-should-not-exist'])

        self.assertEqual('firefox; touch /tmp/atlas-should-not-exist', output.strip())
