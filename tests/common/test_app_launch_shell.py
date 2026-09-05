import subprocess
from unittest import TestCase
from unittest.mock import patch

from atlas import __app_name__
from atlas.gems.flatpak import flatpak
from atlas.gems.snap import snap
from atlas.gems.arch import rebuild_detector


class AppLaunchArgvTest(TestCase):
    """Launchers whose command Atlas constructs itself take an argument list.

    The launchers that run a `.desktop` `Exec=` line (arch and web) keep their shell —
    shell syntax is part of that contract. See docs/plans/2026-09-05-shell-free-execution.md.
    """

    def test_flatpak_run__app_id_is_an_argument_not_a_command_line(self):
        with patch(f'{__app_name__}.gems.flatpak.flatpak.subprocess.Popen') as popen:
            flatpak.run('org.gimp.GIMP')

        self.assertEqual(['flatpak', 'run', 'org.gimp.GIMP'], popen.call_args.args[0])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_snap_run__command_name_is_an_argument_not_a_command_line(self):
        with patch(f'{__app_name__}.gems.snap.snap.subprocess.Popen') as popen:
            snap.run('gimp')

        self.assertEqual(['snap', 'run', 'gimp'], popen.call_args.args[0])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_list_required_rebuild__does_not_use_a_shell(self):
        with patch(f'{__app_name__}.gems.arch.rebuild_detector.system.execute',
                   return_value=(0, '')) as execute:
            rebuild_detector.list_required_rebuild()

        self.assertEqual(['checkrebuild'], execute.call_args.kwargs['cmd'])
        self.assertNotIn('shell', execute.call_args.kwargs)
