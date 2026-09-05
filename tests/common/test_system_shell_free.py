import inspect
from unittest import TestCase
from unittest.mock import patch, Mock

from atlas import __app_name__
from atlas.commons import system
from atlas.commons.system import SimpleProcess, execute, new_root_subprocess
from atlas.gems.arch import pacman


class SimpleProcessArgvTest(TestCase):

    def test_simple_process__passes_the_argument_list_to_popen_unjoined(self):
        with patch(f'{__app_name__}.commons.system.subprocess.Popen') as popen:
            SimpleProcess(['pacman', '-S', 'firefox'])

        self.assertEqual(['pacman', '-S', 'firefox'], popen.call_args.kwargs['args'])
        self.assertFalse(popen.call_args.kwargs['shell'])

    def test_simple_process__no_longer_accepts_a_shell_argument(self):
        self.assertNotIn('shell', inspect.signature(SimpleProcess.__init__).parameters)

    def test_new_root_subprocess__no_longer_accepts_a_shell_argument(self):
        self.assertNotIn('shell', inspect.signature(new_root_subprocess).parameters)


class PacmanTransactionArgvTest(TestCase):

    def _popen_args(self, call):
        with patch(f'{__app_name__}.commons.system.subprocess.Popen') as popen:
            call()
        return popen.call_args.kwargs['args']

    def test_remove_several__malicious_package_name_stays_one_argument(self):
        args = self._popen_args(lambda: pacman.remove_several(['evil; touch /tmp/pwned'], None))

        self.assertEqual(['pacman', '-R', 'evil; touch /tmp/pwned', '--noconfirm'], args)

    def test_download__malicious_package_name_stays_one_argument(self):
        args = self._popen_args(lambda: pacman.download(None, 'evil; touch /tmp/pwned'))

        self.assertIn('evil; touch /tmp/pwned', args)
        self.assertEqual('pacman', args[0])

    def test_upgrade_several__overwrite_glob_is_not_handed_to_a_shell(self):
        args = self._popen_args(
            lambda: pacman.upgrade_several(['firefox'], None, overwrite_conflicting_files=True))

        self.assertIn('--overwrite=*', args)


class ExecuteArgvTest(TestCase):

    def test_execute__sequence_command_does_not_use_a_shell(self):
        with patch(f'{__app_name__}.commons.system.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout=b'')
            execute(['pacman', '-Rc', 'evil; touch /tmp/pwned'])

        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertEqual(['pacman', '-Rc', 'evil; touch /tmp/pwned'], run.call_args.kwargs['args'])

    def test_execute__sequence_command_with_custom_user_builds_a_runuser_argument_list(self):
        with patch(f'{__app_name__}.commons.system.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout=b'')
            execute(['mkdir', '-p', '/tmp/a b'], custom_user='builder')

        self.assertEqual(['runuser', '-u', 'builder', '--', 'mkdir', '-p', '/tmp/a b'],
                         run.call_args.kwargs['args'])


class DeadShellHelperTest(TestCase):

    def test_commons_system__no_longer_ships_an_os_system_notifier(self):
        self.assertFalse(hasattr(system, 'notify_user'))
