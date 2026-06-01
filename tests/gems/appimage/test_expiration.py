from unittest import TestCase

from atlas.gems.appimage.worker import _expiration_hours


class ExpirationHoursTest(TestCase):
    """The suggestions/database downloaders may run before their config is wired up
    (self.config is None) — reading the expiration must fall back, not crash."""

    def test_reads_value(self):
        self.assertEqual(24, _expiration_hours({'suggestions': {'expiration': 24}}, 'suggestions', 99))

    def test_none_config_falls_back(self):
        self.assertEqual(99, _expiration_hours(None, 'suggestions', 99))

    def test_none_section_falls_back(self):
        # the historical crash: {'suggestions': None}['suggestions']['expiration']
        self.assertEqual(24, _expiration_hours({'suggestions': None}, 'suggestions', 24))

    def test_missing_section_falls_back(self):
        self.assertEqual(60, _expiration_hours({}, 'database', 60))

    def test_unparseable_value_falls_back(self):
        self.assertEqual(60, _expiration_hours({'database': {'expiration': 'soon'}}, 'database', 60))

    def test_string_int_parsed(self):
        self.assertEqual(12, _expiration_hours({'database': {'expiration': '12'}}, 'database', 60))
