from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch, Mock

from atlas import __app_name__
from atlas.gems.flatpak import flatpak, VERSION_1_2


class ParseCommitDateTest(TestCase):

    def test_converts_utc_log_date_to_local_naive(self):
        # `flatpak remote-info --log` emits UTC ('+0000'); we display the user's local time.
        result = flatpak.parse_commit_date('2026-06-09 10:37:20 +0000')
        self.assertIsNone(result.tzinfo, 'returned datetime is naive (clean display, no offset)')
        # tz-independent: the naive local value, re-localized, must equal the original UTC instant
        as_utc = result.astimezone().astimezone(timezone.utc)
        self.assertEqual(as_utc, datetime(2026, 6, 9, 10, 37, 20, tzinfo=timezone.utc))

    def test_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            flatpak.parse_commit_date('not a date')


class FlatpakTest(TestCase):

    @patch(f'{__app_name__}.gems.flatpak.flatpak.SimpleProcess')
    @patch(f'{__app_name__}.gems.flatpak.flatpak.ProcessHandler.handle_simple', return_value=(True, """
    Looking for updates...

    \tID\tArch\tBranch\tRemote\tDownload
    1.\t \torg.xpto.Xnote\tx86_64\tstable\tflathub\t< 4.3 MB

    """))
    def test_map_update_download_size__for_flatpak_1_2(self, SimpleProcess: Mock, handle_simple: Mock):
        download_size = flatpak.map_update_download_size(app_ids={'org.xpto.Xnote'}, installation='user', version=VERSION_1_2)
        SimpleProcess.assert_called_once()
        handle_simple.assert_called_once()

        self.assertEqual({'org.xpto.Xnote': 4300000}, download_size)
