import logging
import unittest

from atlas.view import tray


class FakeWindow:
    def __init__(self):
        self.shown = False
        self.hidden = False
        self.destroyed = False
        self.restored = False
        self.evaluated = []

    def show(self):
        self.shown = True

    def hide(self):
        self.hidden = True

    def restore(self):
        self.restored = True

    def destroy(self):
        self.destroyed = True

    def evaluate_js(self, script):
        self.evaluated.append(script)


class FakePkg:
    def __init__(self, update):
        self.update = update


class FakeResult:
    def __init__(self, installed):
        self.installed = installed


class FakeManager:
    def __init__(self, updatable=0, total_extra=2):
        self._result = FakeResult([FakePkg(True)] * updatable + [FakePkg(False)] * total_extra)
        self.calls = 0

    def read_installed(self):
        self.calls += 1
        return self._result


class FakeMenuItem:
    def __init__(self):
        self.label = None

    def set_label(self, label):
        self.label = label


class FakeIndicator:
    def __init__(self):
        self.label = None
        self.icon = None

    def set_label(self, label, guide):
        self.label = label

    def set_icon_full(self, name, desc):
        self.icon = name


def _tray(minimize_to_tray=False, manager=None, interval=0):
    config = {'ui': {'tray': {'enabled': True, 'minimize_to_tray': minimize_to_tray,
                              'update_check_interval': interval}}}
    return tray.AtlasTray(FakeWindow(), manager, config, logging.getLogger('test'), '/tmp/logo.png')


class ToggleLabelTest(unittest.TestCase):
    def test_label_tracks_visibility(self):
        self.assertEqual('Hide Atlas', tray.toggle_label(True))
        self.assertEqual('Show Atlas', tray.toggle_label(False))


class ShouldCancelCloseTest(unittest.TestCase):
    def test_cancels_only_when_opted_in_with_a_tray_to_restore_from(self):
        self.assertTrue(tray.should_cancel_close(quitting=False, minimize_to_tray=True, has_indicator=True))

    def test_quit_always_allows_close(self):
        self.assertFalse(tray.should_cancel_close(quitting=True, minimize_to_tray=True, has_indicator=True))

    def test_close_to_tray_off_allows_close(self):
        self.assertFalse(tray.should_cancel_close(quitting=False, minimize_to_tray=False, has_indicator=True))

    def test_no_indicator_allows_close(self):
        # never trap the window with no way to bring it back
        self.assertFalse(tray.should_cancel_close(quitting=False, minimize_to_tray=True, has_indicator=False))


class AtlasTrayBehaviourTest(unittest.TestCase):
    def test_minimize_to_tray_read_from_config(self):
        self.assertTrue(_tray(minimize_to_tray=True).minimize_to_tray)
        self.assertFalse(_tray(minimize_to_tray=False).minimize_to_tray)

    def test_toggle_hides_then_shows(self):
        t = _tray()
        self.assertTrue(t._visible)
        t._on_toggle(None)
        self.assertTrue(t.window.hidden)
        self.assertFalse(t._visible)
        t._on_toggle(None)
        self.assertTrue(t.window.shown)
        self.assertTrue(t._visible)

    def test_updates_action_shows_and_navigates(self):
        t = _tray()
        t._visible = False
        t._on_updates(None)
        self.assertTrue(t.window.shown)
        self.assertIn("activateView('updates')", t.window.evaluated)

    def test_quit_destroys_window_and_marks_quitting(self):
        t = _tray(minimize_to_tray=True)
        t._on_quit(None)
        self.assertTrue(t._quitting)
        self.assertTrue(t.window.destroyed)

    def test_on_closing_allows_close_when_not_opted_in(self):
        t = _tray(minimize_to_tray=False)
        t.indicator = object()
        self.assertIsNone(t.on_closing())

    def test_on_closing_cancels_when_opted_in(self):
        t = _tray(minimize_to_tray=True)
        t.indicator = object()  # pretend the indicator built successfully
        self.assertFalse(t.on_closing())

    def test_on_closing_allows_close_after_quit_chosen(self):
        t = _tray(minimize_to_tray=True)
        t.indicator = object()
        t._quitting = True
        self.assertIsNone(t.on_closing())

    def test_quit_stops_the_poller(self):
        t = _tray(manager=FakeManager(updatable=1), interval=60)
        self.assertFalse(t._stop.is_set())
        t._on_quit(None)
        self.assertTrue(t._stop.is_set())


class UpdateCountHelpersTest(unittest.TestCase):
    def test_count_updates_counts_only_updatable(self):
        self.assertEqual(0, tray.count_updates(FakeResult([FakePkg(False), FakePkg(False)])))
        self.assertEqual(2, tray.count_updates(FakeResult([FakePkg(True), FakePkg(False), FakePkg(True)])))

    def test_count_updates_tolerates_empty_or_missing(self):
        self.assertEqual(0, tray.count_updates(FakeResult([])))
        self.assertEqual(0, tray.count_updates(FakeResult(None)))
        self.assertEqual(0, tray.count_updates(object()))  # no .installed attr

    def test_updates_menu_label(self):
        self.assertEqual('Check for updates', tray.updates_menu_label(0))
        self.assertEqual('Updates available: 3', tray.updates_menu_label(3))

    def test_tray_label_text_is_blank_when_zero(self):
        self.assertEqual('', tray.tray_label_text(0))
        self.assertEqual('5', tray.tray_label_text(5))

    def test_badge_text_caps_at_99(self):
        self.assertEqual('', tray.badge_text(0))
        self.assertEqual('', tray.badge_text(-3))
        self.assertEqual('7', tray.badge_text(7))
        self.assertEqual('99', tray.badge_text(99))
        self.assertEqual('99+', tray.badge_text(100))
        self.assertEqual('99+', tray.badge_text(5000))

    def test_poll_interval_minutes_parsing(self):
        self.assertEqual(60, tray.poll_interval_minutes({'ui': {'tray': {'update_check_interval': 60}}}))
        self.assertEqual(0, tray.poll_interval_minutes({'ui': {'tray': {'update_check_interval': 0}}}))
        self.assertEqual(60, tray.poll_interval_minutes({}))  # default
        self.assertEqual(0, tray.poll_interval_minutes({'ui': {'tray': {'update_check_interval': 'x'}}}))


class ApplyCountTest(unittest.TestCase):
    def test_apply_count_sets_badge_and_menu_label(self):
        t = _tray()
        t.indicator = FakeIndicator()
        t._item_updates = FakeMenuItem()
        t._apply_count(4)
        self.assertEqual(4, t._update_count)
        self.assertEqual('4', t.indicator.label)
        self.assertEqual('Updates available: 4', t._item_updates.label)

    def test_apply_count_clears_badge_when_zero(self):
        t = _tray()
        t.indicator = FakeIndicator()
        t._item_updates = FakeMenuItem()
        t._apply_count(0)
        self.assertEqual('', t.indicator.label)
        self.assertEqual('Check for updates', t._item_updates.label)


if __name__ == '__main__':
    unittest.main()
