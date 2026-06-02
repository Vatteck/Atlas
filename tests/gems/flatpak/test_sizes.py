from unittest import TestCase
from unittest.mock import patch

from atlas.gems.flatpak import flatpak

# `flatpak list --columns=application,size` output: tab-separated columns, and the size
# column is "<number><NBSP><unit>" (a non-breaking space, U+00A0).
_LIST_OUTPUT = (
    "com.discordapp.Discord\t287.9 MB\n"
    "org.gimp.GIMP\t1.2 GB\n"
    "com.github.tchx84.Flatseal\t1.4 MB\n"
)


class FlatpakInstalledSizesTest(TestCase):

    @patch('atlas.gems.flatpak.flatpak.run_cmd', return_value=_LIST_OUTPUT)
    def test_parses_sizes_to_bytes(self, _run):
        sizes = flatpak.map_installed_sizes()
        self.assertEqual(287.9 * 10**6, sizes['com.discordapp.Discord'])
        self.assertEqual(1.2 * 10**9, sizes['org.gimp.GIMP'])
        self.assertEqual(1.4 * 10**6, sizes['com.github.tchx84.Flatseal'])

    @patch('atlas.gems.flatpak.flatpak.run_cmd', return_value='')
    def test_empty_output(self, _run):
        self.assertEqual({}, flatpak.map_installed_sizes())

    @patch('atlas.gems.flatpak.flatpak.run_cmd', return_value='broken-line-no-tab\n')
    def test_malformed_line_skipped(self, _run):
        self.assertEqual({}, flatpak.map_installed_sizes())
