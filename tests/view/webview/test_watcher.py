import unittest
from unittest.mock import Mock

from atlas.api.abstract.view import (MultipleSelectComponent, SingleSelectComponent, FormComponent,
                                     InputOption, SelectViewType, TextComponent)
from atlas.view.webview.watcher import WebviewWatcher


def _opt(name):
    return InputOption(label=name, value=name)


class WatcherComponentSerializationTest(unittest.TestCase):
    """The confirm modal renders input components and returns option-index selections;
    WebviewWatcher serializes them and applies the selections back onto the originals so
    the arch flows (request_optional_deps, confirm_missing_deps, request_providers) work."""

    def test_serialize_multiselect_marks_default_selected(self):
        a, b, c = _opt('a'), _opt('b'), _opt('c')
        comp = MultipleSelectComponent(label='', options=[a, b, c], default_options={b})

        serialized = WebviewWatcher._serialize_components([comp])

        self.assertEqual(1, len(serialized))
        self.assertEqual('multiselect', serialized[0]['kind'])
        sel = [o['selected'] for o in serialized[0]['options']]
        self.assertEqual([False, True, False], sel)

    def test_multiselect_roundtrip_writes_back_chosen_values(self):
        a, b, c = _opt('a'), _opt('b'), _opt('c')
        comp = MultipleSelectComponent(label='', options=[a, b, c], default_options={a})

        # modal returns: for the single component, options 0 and 2 checked
        WebviewWatcher._apply_selections([comp], [[0, 2]])

        self.assertEqual({a, c}, comp.values)
        self.assertEqual({'a', 'c'}, set(comp.get_selected_values()))

    def test_multiselect_roundtrip_empty_selection_clears_values(self):
        a, b = _opt('a'), _opt('b')
        comp = MultipleSelectComponent(label='', options=[a, b], default_options={a, b})

        WebviewWatcher._apply_selections([comp], [[]])

        self.assertEqual(set(), comp.values)

    def test_singleselect_roundtrip_sets_value(self):
        a, b = _opt('a'), _opt('b')
        comp = SingleSelectComponent(type_=SelectViewType.COMBO, label='dep', options=[a, b],
                                     default_option=a)

        WebviewWatcher._apply_selections([comp], [1])

        self.assertEqual('b', comp.get_selected())

    def test_form_roundtrip_applies_to_nested_components(self):
        a, b = _opt('a'), _opt('b')
        x, y = _opt('x'), _opt('y')
        s1 = SingleSelectComponent(type_=SelectViewType.COMBO, label='d1', options=[a, b], default_option=a)
        s2 = SingleSelectComponent(type_=SelectViewType.COMBO, label='d2', options=[x, y], default_option=x)
        form = FormComponent([s1, s2], label='')

        serialized = WebviewWatcher._serialize_components([form])
        self.assertEqual('form', serialized[0]['kind'])
        self.assertEqual(2, len(serialized[0]['components']))

        # pick second option in the first select, first option in the second
        WebviewWatcher._apply_selections([form], [[1, 0]])

        self.assertEqual('b', s1.get_selected())
        self.assertEqual('x', s2.get_selected())

    def test_apply_ignores_out_of_range_indices(self):
        a = _opt('a')
        comp = MultipleSelectComponent(label='', options=[a], default_options=None)

        WebviewWatcher._apply_selections([comp], [[0, 5, -1]])

        self.assertEqual({a}, comp.values)

    def test_apply_none_selection_is_noop(self):
        a = _opt('a')
        comp = MultipleSelectComponent(label='', options=[a], default_options={a})
        WebviewWatcher._apply_selections([comp], [None])
        self.assertEqual({a}, comp.values)

    def test_serialize_text_component(self):
        serialized = WebviewWatcher._serialize_components([TextComponent(html='<b>hi</b>')])
        self.assertEqual({'kind': 'text', 'html': '<b>hi</b>'}, serialized[0])

    def test_option_icon_inlined_as_data_uri(self):
        from atlas.commons import resource
        from atlas.gems.arch import ROOT_DIR
        opt = _opt('repo-pkg')
        opt.icon_path = resource.get_path('img/repo.svg', ROOT_DIR)
        comp = MultipleSelectComponent(label='', options=[opt], default_options=None)
        serialized = WebviewWatcher._serialize_components([comp])
        icon = serialized[0]['options'][0]['icon']
        self.assertTrue(icon and icon.startswith('data:image/svg+xml;base64,'))

    def test_option_without_icon_is_none(self):
        comp = MultipleSelectComponent(label='', options=[_opt('a')], default_options=None)
        serialized = WebviewWatcher._serialize_components([comp])
        self.assertIsNone(serialized[0]['options'][0]['icon'])


class WatcherRequestConfirmationTest(unittest.TestCase):

    def test_request_confirmation_applies_selections_on_accept(self):
        a, b = _opt('a'), _opt('b')
        comp = MultipleSelectComponent(label='', options=[a, b], default_options=None)

        api = Mock()
        api.prompt_confirmation.return_value = (True, [[1]])  # confirmed, option 1 chosen
        watcher = WebviewWatcher(Mock(), window=Mock(), api=api)

        result = watcher.request_confirmation(title='t', body='b', components=[comp])

        self.assertTrue(result)
        self.assertEqual({b}, comp.values)
        # the serialized components were forwarded to the modal
        _, kwargs = api.prompt_confirmation.call_args
        self.assertEqual('multiselect', kwargs['components'][0]['kind'])

    def test_request_confirmation_does_not_apply_on_deny(self):
        a, b = _opt('a'), _opt('b')
        comp = MultipleSelectComponent(label='', options=[a, b], default_options={a})

        api = Mock()
        api.prompt_confirmation.return_value = (False, None)
        watcher = WebviewWatcher(Mock(), window=Mock(), api=api)

        result = watcher.request_confirmation(title='t', body='b', components=[comp])

        self.assertFalse(result)
        self.assertEqual({a}, comp.values)  # unchanged

    def test_request_confirmation_no_api_defaults_true(self):
        watcher = WebviewWatcher(Mock(), window=None, api=None)
        self.assertTrue(watcher.request_confirmation(title='t', body='b'))


class WatcherStatusCleaningTest(unittest.TestCase):
    """Gem status/substatus messages use HTML markup (bauh's bold() → <span style=…>); the webview
    renders them as text, so the watcher strips tags. Raw command output (print) stays verbatim."""

    def _watcher_and_window(self):
        window = Mock()
        return WebviewWatcher(Mock(), window=window, api=None), window

    def test_change_status_strips_html(self):
        watcher, window = self._watcher_and_window()
        watcher.change_status('Building package <span style="font-weight: bold">vesktop-bin</span>')
        call = window.evaluate_js.call_args[0][0]
        self.assertIn('Building package vesktop-bin', call)
        self.assertNotIn('<span', call)

    def test_change_substatus_strips_html(self):
        watcher, window = self._watcher_and_window()
        watcher.change_substatus('Synchronizing <b>chroot</b>')
        call = window.evaluate_js.call_args[0][0]
        self.assertIn('Synchronizing chroot', call)
        self.assertNotIn('<b>', call)

    def test_print_keeps_raw_output_verbatim(self):
        watcher, window = self._watcher_and_window()
        # Raw output can legitimately contain angle brackets (template errors, redirects).
        watcher.print('error: std::vector<int> not found 2>&1')
        call = window.evaluate_js.call_args[0][0]
        self.assertIn('std::vector<int>', call)


if __name__ == '__main__':
    unittest.main()
