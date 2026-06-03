import unittest

from atlas.gems.flatpak import permissions as perms

# Real Dropbox permission set (from Flathub's summary endpoint).
DROPBOX = {
    'sockets': ['x11', 'pulseaudio'],
    'filesystems': ['home', '/tmp'],
    'shared': ['network', 'ipc'],
    'session-bus': {'own': ['org.kde.*'], 'talk': ['org.freedesktop.Notifications']},
}

# A well-sandboxed app: Wayland, portals, GPU only, FOSS.
SANDBOXED = {'sockets': ['wayland'], 'devices': ['dri'], 'shared': []}


class DescribeTest(unittest.TestCase):
    def _titles(self, p, is_free=True):
        return {i['title'] for i in perms.describe(p, is_free)}

    def test_dropbox_high_risk_items(self):
        items = perms.describe(DROPBOX, is_free=False)
        titles = {i['title'] for i in items}
        self.assertIn('Home folder access', titles)
        self.assertIn('Legacy windowing (X11)', titles)
        self.assertIn('Network access', titles)
        self.assertIn('Audio & microphone', titles)
        self.assertIn('Uses non-portal services', titles)
        self.assertIn('Proprietary code', titles)         # is_free=False
        self.assertIn('Filesystem path /tmp', titles)
        # danger items sort first
        self.assertEqual('danger', items[0]['level'])

    def test_home_and_host_are_danger(self):
        self.assertEqual('danger', perms.describe({'filesystems': ['home']})[0]['level'])
        self.assertEqual('danger', perms.describe({'filesystems': ['host']})[0]['level'])

    def test_wayland_and_gpu_are_safe(self):
        levels = {i['title']: i['level'] for i in perms.describe(SANDBOXED)}
        self.assertEqual('safe', levels['Wayland windowing'])
        self.assertEqual('safe', levels['GPU acceleration'])

    def test_free_license_adds_no_proprietary_item(self):
        self.assertNotIn('Proprietary code', self._titles(DROPBOX, is_free=True))

    def test_ipc_is_not_surfaced(self):
        self.assertNotIn('ipc', ' '.join(self._titles({'shared': ['ipc']})).lower())

    def test_empty(self):
        self.assertEqual([], perms.describe(None))
        self.assertEqual([], perms.describe({}))


class SafetyTest(unittest.TestCase):
    def test_dropbox_is_unsafe(self):
        self.assertEqual('unsafe', perms.safety(DROPBOX, is_free=False)['level'])
        self.assertEqual('Potentially unsafe', perms.safety(DROPBOX, is_free=False)['label'])

    def test_sandboxed_is_safe(self):
        self.assertEqual('safe', perms.safety(SANDBOXED, is_free=True)['level'])

    def test_moderate_when_only_warnings(self):
        # network access alone is a warning, not a danger
        self.assertEqual('moderate', perms.safety({'shared': ['network']}, is_free=True)['level'])

    def test_proprietary_alone_is_moderate(self):
        self.assertEqual('moderate', perms.safety({}, is_free=False)['level'])

    def test_no_perms_free_is_safe(self):
        self.assertEqual('safe', perms.safety({}, is_free=True)['level'])


# Real `flatpak info --show-permissions` output (Discord).
SHOW_PERMS = """\
[Context]
shared=network;ipc;
sockets=x11;wayland;pulseaudio;pcsc;
devices=all;
filesystems=xdg-download;xdg-pictures:ro;home;

[Session Bus Policy]
org.kde.StatusNotifierWatcher=talk
"""


class EditableTogglesTest(unittest.TestCase):
    def test_parse_context_strips_modes_and_sections(self):
        ctx = perms.parse_context(SHOW_PERMS)
        self.assertEqual({'network', 'ipc'}, ctx['shared'])
        self.assertEqual({'x11', 'wayland', 'pulseaudio', 'pcsc'}, ctx['sockets'])
        self.assertEqual({'all'}, ctx['devices'])
        self.assertIn('home', ctx['filesystems'])
        self.assertIn('xdg-pictures', ctx['filesystems'])  # ':ro' stripped
        # Session Bus Policy lines are not mistaken for context entries
        self.assertNotIn('org.kde.StatusNotifierWatcher', ctx['shared'])

    def test_editable_toggles_carry_detail_text(self):
        toggles = perms.editable_toggles(perms.parse_context(SHOW_PERMS))
        self.assertTrue(all(t.get('detail') for t in toggles))  # every toggle has tooltip text

    def test_editable_toggles_reflect_state(self):
        states = {t['key']: t['enabled'] for t in perms.editable_toggles(perms.parse_context(SHOW_PERMS))}
        self.assertTrue(states['share:network'])
        self.assertTrue(states['socket:x11'])
        self.assertTrue(states['device:all'])
        self.assertTrue(states['filesystem:home'])
        self.assertFalse(states['filesystem:host'])   # not granted

    def test_editable_toggles_all_off_for_empty(self):
        states = {t['key']: t['enabled'] for t in perms.editable_toggles(perms.parse_context(''))}
        self.assertTrue(all(v is False for v in states.values()))

    def test_override_flag_mapping(self):
        self.assertEqual('--unshare=network', perms.override_flag('share:network', False))
        self.assertEqual('--share=network', perms.override_flag('share:network', True))
        self.assertEqual('--nosocket=x11', perms.override_flag('socket:x11', False))
        self.assertEqual('--nofilesystem=host', perms.override_flag('filesystem:host', False))
        self.assertEqual('--allow=bluetooth', perms.override_flag('feature:bluetooth', True))
        self.assertEqual('--disallow=bluetooth', perms.override_flag('feature:bluetooth', False))
        self.assertIsNone(perms.override_flag('bogus', True))
        self.assertIsNone(perms.override_flag('socket:', True))  # empty value


class GroupedTogglesTest(unittest.TestCase):
    def test_groups_and_flag_labels(self):
        groups = perms.grouped_toggles(perms.parse_context(SHOW_PERMS))
        titles = [g['title'] for g in groups]
        self.assertEqual(['Share', 'Socket', 'Device', 'Features'], titles)
        share = next(g for g in groups if g['title'] == 'Share')
        net = next(i for i in share['items'] if i['key'] == 'share:network')
        self.assertTrue(net['enabled'])
        self.assertEqual('share=network', net['flag'])     # manifest-style sub-label
        feat = next(g for g in groups if g['title'] == 'Features')
        bt = next(i for i in feat['items'] if i['key'] == 'feature:bluetooth')
        self.assertEqual('allow=bluetooth', bt['flag'])    # features use the 'allow' manifest key
        self.assertFalse(bt['enabled'])

    def test_features_parsed_from_context(self):
        ctx = perms.parse_context("[Context]\nfeatures=devel;bluetooth;\n")
        self.assertEqual({'devel', 'bluetooth'}, ctx['features'])
        groups = perms.grouped_toggles(ctx)
        feat = next(g for g in groups if g['title'] == 'Features')
        self.assertTrue(next(i for i in feat['items'] if i['key'] == 'feature:devel')['enabled'])


class FilesystemSectionTest(unittest.TestCase):
    def test_parse_context_keeps_raw_modes(self):
        ctx = perms.parse_context(SHOW_PERMS)
        # filesystems_raw keeps the ':ro' that 'filesystems' strips
        self.assertEqual({'xdg-download', 'xdg-pictures:ro', 'home'}, ctx['filesystems_raw'])

    def test_filesystem_state_presets_reflect_grants_and_modes(self):
        state = perms.filesystem_state(perms.parse_context(SHOW_PERMS))
        by_name = {p['name']: p for p in state['presets']}
        self.assertTrue(by_name['home']['enabled'])
        self.assertEqual('rw', by_name['home']['mode'])
        self.assertTrue(by_name['xdg-download']['enabled'])
        self.assertTrue(by_name['xdg-pictures']['enabled'])
        self.assertEqual('ro', by_name['xdg-pictures']['mode'])   # ':ro' carried through
        self.assertFalse(by_name['host']['enabled'])              # not granted
        self.assertEqual('rw', by_name['host']['mode'])           # default for ungranted
        self.assertTrue(by_name['home']['risky'])                 # home is flagged risky
        self.assertFalse(by_name['xdg-download']['risky'])

    def test_filesystem_state_custom_paths(self):
        # a non-preset path with a :create mode shows up under custom, not presets
        ctx = perms.parse_context("[Context]\nfilesystems=home;/mnt/data:create;\n")
        state = perms.filesystem_state(ctx)
        self.assertEqual([{'name': '/mnt/data', 'mode': 'create'}], state['custom'])
        self.assertTrue({p['name'] for p in state['presets']} >= {'home'})

    def test_filesystem_state_empty(self):
        state = perms.filesystem_state(perms.parse_context(''))
        self.assertEqual([], state['custom'])
        self.assertTrue(all(p['enabled'] is False for p in state['presets']))

    def test_filesystem_flag(self):
        self.assertEqual('--filesystem=home', perms.filesystem_flag('home', True, 'rw'))
        self.assertEqual('--filesystem=home:ro', perms.filesystem_flag('home', True, 'ro'))
        self.assertEqual('--filesystem=/mnt/x:create', perms.filesystem_flag('/mnt/x', True, 'create'))
        self.assertEqual('--nofilesystem=home', perms.filesystem_flag('home', False, 'rw'))
        self.assertEqual('--filesystem=home', perms.filesystem_flag('home', True, 'bogus'))  # unknown mode -> rw
        self.assertEqual('--filesystem=home', perms.filesystem_flag('  home  ', True))       # trimmed
        self.assertIsNone(perms.filesystem_flag('', True))
        self.assertIsNone(perms.filesystem_flag('   ', True))


if __name__ == '__main__':
    unittest.main()
