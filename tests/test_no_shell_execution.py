import os
import re
from unittest import TestCase

import atlas

ATLAS_DIR = os.path.dirname(os.path.abspath(atlas.__file__))

RE_SHELL = re.compile(r'shell\s*=\s*True|os\.system\(|os\.popen\(')

# The only places Atlas may hand a command line to a shell. Each entry is a module path
# relative to the atlas package, with the reason it is allowed.
#
# Both remaining cases run a command line that is *already* a shell command line by
# specification — a `.desktop` `Exec=` entry, or the Debian gem's aptitude wrappers, which
# build command strings rather than argument lists. Everything Atlas constructs itself must
# use an argument list so its values can never be parsed as shell syntax.
# See docs/plans/2026-09-05-shell-free-execution.md.
ALLOWED = {
    'gems/arch/controller.py',       # launch(): the package's .desktop Exec= line
    'gems/web/controller.py',        # launch(): the web app's generated command line
    'gems/debian/controller.py',     # launch() + apt front-end handoff (gem off by default)
    'gems/debian/aptitude.py',       # builds command strings, not argv (gem off by default)
    'gems/debian/index.py',          # static dpkg-query line (gem off by default)
}


class NoShellExecutionTest(TestCase):

    def _violations(self):
        found = []
        for root, _, files in os.walk(ATLAS_DIR):
            for name in files:
                if not name.endswith('.py'):
                    continue

                path = os.path.join(root, name)
                rel = os.path.relpath(path, ATLAS_DIR)

                if rel in ALLOWED:
                    continue

                with open(path, encoding='utf-8') as f:
                    for number, line in enumerate(f, start=1):
                        if RE_SHELL.search(line):
                            found.append(f'{rel}:{number}: {line.strip()}')
        return found

    def test_atlas_never_runs_a_constructed_command_through_a_shell(self):
        violations = self._violations()

        self.assertEqual([], violations,
                         'These lines run a command through a shell. Pass an argument list to '
                         'run_cmd/execute/SimpleProcess instead, or add the file to ALLOWED '
                         'with a reason if a shell command line is genuinely what is being run.'
                         f'\n\n' + '\n'.join(violations))
