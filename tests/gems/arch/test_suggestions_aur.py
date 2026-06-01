"""list_suggestions resolves AUR names (not just official-repo packages)."""

from logging import getLogger
from unittest import TestCase
from unittest.mock import Mock, patch

from atlas.gems.arch.controller import ArchManager


def _manager(name_priority, available_packages):
    man = ArchManager.__new__(ArchManager)
    man.logger = getLogger('test')
    man.logger.disabled = True
    man.configman = Mock()
    man.configman.get_config.return_value = {'repositories': True}
    man.aur_client = Mock()
    man.categories = {}
    man.context = Mock()
    man.i18n = {}
    man._fill_suggestions = lambda out: out.update(name_priority)
    man._fill_available_packages = lambda out: out.update(available_packages)
    man._fill_ignored_updates = lambda out: None
    return man


# firefox is an official-repo package; visual-studio-code-bin is AUR-only.
NAME_PRIORITY = {'firefox': 2, 'visual-studio-code-bin': 3}
AVAILABLE_REPO = {'firefox': {'v': '1.0', 'r': 'extra', 'i': False}}


class AurSuggestionsTest(TestCase):

    @patch('atlas.gems.arch.controller.sort_by_priority', side_effect=lambda d: sorted(d, key=lambda k: -d[k]))
    @patch('atlas.gems.arch.controller.pacman')
    @patch('atlas.gems.arch.controller.aur')
    def test_aur_names_are_resolved_and_returned(self, mock_aur, mock_pacman, _sort):
        mock_aur.is_supported.return_value = True
        mock_pacman.fill_ignored_packages.side_effect = lambda out: None
        mock_pacman.map_installed.return_value = {}
        mock_pacman.map_packages.return_value = {'firefox': {'description': 'A web browser'}}

        man = _manager(NAME_PRIORITY, AVAILABLE_REPO)
        man.aur_client.get_info.return_value = [
            {'Name': 'visual-studio-code-bin', 'Version': '1.2-1', 'Description': 'VS Code'}
        ]

        res = man.list_suggestions(limit=-1, filter_installed=True)

        by_name = {s.package.name: s.package for s in res}
        self.assertEqual({'firefox', 'visual-studio-code-bin'}, set(by_name))
        # AUR package carries aur repo + its own version/description
        vscode = by_name['visual-studio-code-bin']
        self.assertEqual('aur', vscode.repository)
        self.assertEqual('1.2-1', vscode.version)
        self.assertEqual('VS Code', vscode.description)
        # repo package keeps its repo + pacman-sourced description
        self.assertEqual('extra', by_name['firefox'].repository)
        self.assertEqual('A web browser', by_name['firefox'].description)
        # AUR was queried only for the non-repo candidate
        man.aur_client.get_info.assert_called_once_with(['visual-studio-code-bin'])

    @patch('atlas.gems.arch.controller.sort_by_priority', side_effect=lambda d: sorted(d, key=lambda k: -d[k]))
    @patch('atlas.gems.arch.controller.pacman')
    @patch('atlas.gems.arch.controller.aur')
    def test_no_aur_resolution_when_unsupported(self, mock_aur, mock_pacman, _sort):
        mock_aur.is_supported.return_value = False
        mock_pacman.fill_ignored_packages.side_effect = lambda out: None
        mock_pacman.map_packages.return_value = {'firefox': {'description': 'A web browser'}}

        man = _manager(NAME_PRIORITY, AVAILABLE_REPO)

        res = man.list_suggestions(limit=-1, filter_installed=True)

        self.assertEqual({'firefox'}, {s.package.name for s in res})
        man.aur_client.get_info.assert_not_called()

    @patch('atlas.gems.arch.controller.sort_by_priority', side_effect=lambda d: sorted(d, key=lambda k: -d[k]))
    @patch('atlas.gems.arch.controller.pacman')
    @patch('atlas.gems.arch.controller.aur')
    def test_installed_aur_filtered_out(self, mock_aur, mock_pacman, _sort):
        mock_aur.is_supported.return_value = True
        mock_pacman.fill_ignored_packages.side_effect = lambda out: None
        mock_pacman.map_installed.return_value = {'visual-studio-code-bin': '1.2-1'}  # already installed
        mock_pacman.map_packages.return_value = {'firefox': {'description': 'A web browser'}}

        man = _manager(NAME_PRIORITY, AVAILABLE_REPO)
        man.aur_client.get_info.return_value = [
            {'Name': 'visual-studio-code-bin', 'Version': '1.2-1', 'Description': 'VS Code'}
        ]

        res = man.list_suggestions(limit=-1, filter_installed=True)
        # filter_installed drops the already-installed AUR package
        self.assertEqual({'firefox'}, {s.package.name for s in res})
