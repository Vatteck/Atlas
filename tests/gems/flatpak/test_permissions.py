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


if __name__ == '__main__':
    unittest.main()
