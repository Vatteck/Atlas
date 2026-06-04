import unittest
import json
from datetime import datetime, date, timezone
from unittest.mock import Mock, patch, mock_open
from atlas.view.webview.api import AtlasApi, _json_safe


class GetInstalledFilterTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name, runtime=False):
        p = Mock()
        p.name = name
        p.runtime = runtime
        p.description = ''; p.version = '1'; p.latest_version = '1'
        p.installed = True; p.update = False; p.icon_url = None; p.size = 1
        p.categories = []
        p.get_publisher.return_value = ''
        p.get_type.return_value = 'flatpak'
        for attr in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                     'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, attr).return_value = False
        return p

    def test_flatpak_runtimes_hidden_from_installed(self):
        app = self._pkg('GIMP', runtime=False)
        runtime = self._pkg('org.freedesktop.Platform', runtime=True)
        self.manager.read_installed.return_value = Mock(installed=[app, runtime])

        res = self.api.get_installed()

        names = [p['name'] for p in res['data']]
        self.assertIn('GIMP', names)
        self.assertNotIn('org.freedesktop.Platform', names)


class AurMetaTest(unittest.TestCase):
    """get_aur_meta: current maintainer, 'changed since install' advisory, and update detection."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _setup(self, repository='aur', baseline=None, current='AlphaLynx', has_client=True,
               installed=True, version='2.0.6-1', latest='2.0.11-1'):
        pkg = Mock(name='pkg'); pkg.name = 'antigravity'; pkg.repository = repository
        pkg.maintainer = baseline; pkg.installed = installed; pkg.version = version
        self.api._get_pkg = Mock(return_value=pkg)
        arch_man = Mock()
        arch_man.aur_client.get_info.return_value = [{'Maintainer': current, 'Version': latest}]
        self.api._manager_by_gem = Mock(return_value=arch_man if has_client else None)
        return arch_man

    def test_no_baseline_shows_current_maintainer_without_change(self):
        self._setup(baseline=None, current='AlphaLynx')      # antigravity case
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertEqual('AlphaLynx', data['maintainer'])
        self.assertIsNone(data['changed'])

    def test_changed_maintainer_flagged(self):
        self._setup(baseline='HurricanePootis', current='AlphaLynx')
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertEqual({'old': 'HurricanePootis', 'new': 'AlphaLynx'}, data['changed'])

    def test_same_maintainer_not_flagged(self):
        self._setup(baseline='AlphaLynx', current='AlphaLynx')
        self.assertIsNone(self.api.get_aur_meta('antigravity')['data']['changed'])

    def test_now_orphaned_reported(self):
        self._setup(baseline='AlphaLynx', current=None)
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertIsNone(data['maintainer'])
        self.assertEqual({'old': 'AlphaLynx', 'new': None}, data['changed'])

    def test_non_aur_returns_empty(self):
        self._setup(repository='core', baseline='x')
        self.assertEqual({}, self.api.get_aur_meta('bash')['data'])

    def test_update_available_when_installed_is_older(self):
        # real vercmp: 2.0.6-1 < 2.0.11-1
        self._setup(installed=True, version='2.0.6-1', latest='2.0.11-1')
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertEqual('2.0.11-1', data['latest_version'])
        self.assertTrue(data['update_available'])

    def test_no_update_when_versions_equal(self):
        self._setup(installed=True, version='2.0.11-1', latest='2.0.11-1')
        self.assertFalse(self.api.get_aur_meta('antigravity')['data']['update_available'])

    def test_no_update_for_non_installed(self):
        self._setup(installed=False, version='2.0.6-1', latest='2.0.11-1')
        self.assertFalse(self.api.get_aur_meta('antigravity')['data']['update_available'])


class SerializeSortFieldsTest(unittest.TestCase):
    """The Sort dropdown's 'recently updated' mode needs last_modified serialized."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name, last_modified):
        p = Mock()
        p.name = name
        p.description = ''; p.version = '1'; p.latest_version = '1'; p.installed = False
        p.update = False; p.icon_url = None; p.size = 1; p.categories = []
        p.votes = 42; p.popularity = 3.5; p.last_modified = last_modified
        p.get_publisher.return_value = ''
        p.get_type.return_value = 'aur'
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def test_last_modified_votes_popularity_serialized(self):
        data = self.api._serialize_pkg(self._pkg('yay', 1700000000))
        self.assertEqual(1700000000, data['last_modified'])
        self.assertEqual(42, data['votes'])
        self.assertEqual(3.5, data['popularity'])


class FlatpakIconFallbackTest(unittest.TestCase):
    """Flatpak search results carry no icon; _serialize_pkg derives the predictable Flathub CDN URL."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def _pkg(self, type_, app_id, icon_url=None):
        p = Mock()
        p.name = 'X'; p.description = ''; p.version = '1'; p.latest_version = '1'
        p.installed = False; p.update = False; p.icon_url = icon_url; p.size = 1; p.categories = []
        p.id = app_id
        p.get_publisher.return_value = ''
        p.get_type.return_value = type_
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def test_flatpak_without_icon_gets_flathub_cdn_url(self):
        data = self.api._serialize_pkg(self._pkg('flatpak', 'com.valvesoftware.Steam'))
        self.assertEqual('https://dl.flathub.org/repo/appstream/x86_64/icons/128x128/com.valvesoftware.Steam.png',
                         data['icon_url'])

    def test_flatpak_with_existing_icon_is_not_overridden(self):
        data = self.api._serialize_pkg(self._pkg('flatpak', 'com.x.Y', icon_url='data:image/png;base64,AAAA'))
        self.assertEqual('data:image/png;base64,AAAA', data['icon_url'])

    def test_non_flatpak_gets_no_cdn_fallback(self):
        data = self.api._serialize_pkg(self._pkg('aur', None))
        self.assertEqual('', data['icon_url'])


class FlatpakMetaTest(unittest.TestCase):
    """get_flatpak_meta dispatches to the flatpak gem only for Flatpak packages."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def test_non_flatpak_returns_empty(self):
        pkg = Mock(); pkg.id = 'x'; pkg.get_type.return_value = 'aur'
        with patch.object(self.api, '_get_pkg', return_value=pkg):
            res = self.api.get_flatpak_meta('aur:x')
        self.assertEqual({}, res['data'])

    def test_flatpak_dispatches_to_gem(self):
        pkg = Mock(); pkg.id = 'org.gimp.GIMP'; pkg.get_type.return_value = 'flatpak'
        gem = Mock()
        gem.get_flathub_metadata.return_value = {'is_free': True, 'verified': True,
                                                 'installs_last_month': 67823}
        with patch.object(self.api, '_get_pkg', return_value=pkg), \
             patch.object(self.api, '_manager_by_gem', return_value=gem):
            res = self.api.get_flatpak_meta('flatpak:gimp')
        self.assertTrue(res['data']['is_free'])
        self.assertTrue(res['data']['verified'])
        gem.get_flathub_metadata.assert_called_once_with('org.gimp.GIMP')


class InstalledIconResolveTest(unittest.TestCase):
    """get_pkg_icon: resolve an installed app's icon from .desktop / icon theme dirs."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def test_desktop_icon_name_parsing(self):
        self.assertEqual('firefox', self.api._desktop_icon_name('[Desktop Entry]\nName=Firefox\nIcon=firefox\n'))
        self.assertIsNone(self.api._desktop_icon_name('[Desktop Entry]\nName=X\n'))

    def test_find_icon_file_searches_standard_dirs(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        apps = os.path.join(d, 'hicolor', 'scalable', 'apps')
        os.makedirs(apps)
        open(os.path.join(apps, 'gimp.svg'), 'w').close()
        with patch.object(AtlasApi, '_ICON_DIRS', (apps,)):
            self.assertTrue(self.api._find_icon_file('gimp').endswith('gimp.svg'))
            self.assertIsNone(self.api._find_icon_file('nonexistent'))

    def test_find_icon_file_accepts_absolute_path(self):
        import tempfile, os
        fd, p = tempfile.mkstemp(suffix='.png'); os.close(fd)
        self.assertEqual(p, self.api._find_icon_file(p))
        self.assertIsNone(self.api._find_icon_file('/no/such/icon.png'))

    def test_get_pkg_icon_empty_for_non_installed(self):
        pkg = Mock(); pkg.installed = False; pkg.name = 'x'
        with patch.object(self.api, '_get_pkg', return_value=pkg):
            res = self.api.get_pkg_icon('aur:x')
        self.assertEqual('ok', res['status'])
        self.assertEqual('', res['data'])

    def test_get_pkg_icon_resolves_and_caches_for_installed(self):
        pkg = Mock(); pkg.installed = True; pkg.name = 'gimp'
        with patch.object(self.api, '_get_pkg', return_value=pkg), \
             patch.object(self.api, '_resolve_installed_icon', return_value='data:image/png;base64,AAAA') as mock_resolve:
            r1 = self.api.get_pkg_icon('arch:gimp')
            r2 = self.api.get_pkg_icon('arch:gimp')  # cached → resolver not called again
        self.assertEqual('data:image/png;base64,AAAA', r1['data'])
        self.assertEqual('data:image/png;base64,AAAA', r2['data'])
        mock_resolve.assert_called_once()


class GetOrphansTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name, ptype):
        p = Mock()
        p.name = name
        p.description = ''; p.version = '1'; p.latest_version = '1'; p.installed = True
        p.update = False; p.icon_url = None; p.size = 1; p.categories = []
        p.get_publisher.return_value = ''
        p.get_type.return_value = ptype
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def _arch_man(self, orphan_names):
        m = Mock()
        m.__module__ = 'atlas.gems.arch.controller'
        m.list_orphans.return_value = set(orphan_names)
        return m

    def test_returns_only_real_arch_orphans(self):
        arch = self._arch_man({'gjs', 'gutenprint'})
        self.manager.managers = [arch]
        # a real orphan, a non-orphan arch pkg, and a flatpak that happens to share an
        # orphan name (must NOT be treated as an Arch orphan)
        self.manager.read_installed.return_value = Mock(installed=[
            self._pkg('gjs', 'arch_repo'),
            self._pkg('firefox', 'arch_repo'),
            self._pkg('gutenprint', 'flatpak'),
        ])
        res = self.api.get_orphans()
        names = [p['name'] for p in res['data']]
        self.assertEqual(['gjs'], names)

    def test_no_orphans_short_circuits(self):
        arch = self._arch_man(set())
        self.manager.managers = [arch]
        res = self.api.get_orphans()
        self.assertEqual([], res['data'])
        self.manager.read_installed.assert_not_called()

    def test_orphan_count_is_cheap(self):
        arch = self._arch_man({'gjs', 'gutenprint', 'cpptrace'})
        self.manager.managers = [arch]
        res = self.api.get_orphan_count()
        self.assertEqual('ok', res['status'])
        self.assertEqual(3, res['count'])
        self.manager.read_installed.assert_not_called()  # count must not read_installed


class OpenUrlTest(unittest.TestCase):
    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_opens_http_url(self, mock_open):
        res = self.api.open_url('https://aur.archlinux.org/packages/antigravity')
        self.assertEqual('ok', res['status'])
        mock_open.assert_called_once_with('https://aur.archlinux.org/packages/antigravity')

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_rejects_non_http_scheme(self, mock_open):
        for bad in ['file:///etc/passwd', 'javascript:alert(1)', '', None, 'aur.archlinux.org']:
            res = self.api.open_url(bad)
            self.assertEqual('error', res['status'])
        mock_open.assert_not_called()


class AppSettingsTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())
        # core config
        self.core = {
            'gems': None,
            'suggestions': {'enabled': True, 'by_type': 15},
            'system': {'notifications': True, 'single_dependency_checking': False},
            'updates': {'check_interval': 5, 'ask_for_reboot': True},
            'download': {'icons': True},
            'store_root_password': True,
            'ui': {'tray': {'enabled': True, 'minimize_to_tray': False, 'update_check_interval': 60}},
        }
        self.manager.configman.get_config.return_value = self.core

        # two managers: an arch one (works) and a flatpak one (works) with a config manager
        def mk(modname, enabled, can_work):
            m = Mock()
            m.__module__ = f'atlas.gems.{modname}.controller'
            m.is_enabled.return_value = enabled
            m.can_work.return_value = (can_work, None)
            return m
        self.arch = mk('arch', True, True)
        self.arch.configman.get_config.return_value = {'aur_check_pkgbuild': True}
        self.flatpak = mk('flatpak', True, True)
        self.flatpak.configman.get_config.return_value = {'installation_level': 'user'}
        self.manager.managers = [self.arch, self.flatpak]

    def test_get_app_settings_shape(self):
        res = self.api.get_app_settings()
        self.assertEqual('ok', res['status'])
        data = res['data']
        ids = {t['id'] for t in data['types']}
        self.assertEqual({'arch', 'flatpak'}, ids)
        self.assertTrue(data['flatpak_available'])
        self.assertEqual('user', data['flatpak_installation_level'])
        self.assertTrue(data['general']['suggestions_enabled'])

    def test_save_app_settings_writes_gems_and_applies_live(self):
        res = self.api.save_app_settings({'types': {'arch': True, 'flatpak': False},
                                          'general': {'suggestions_enabled': False},
                                          'flatpak_installation_level': 'system'})
        self.assertEqual('ok', res['status'])
        # gems list written (enabled only) + general toggle applied
        self.assertEqual(['arch'], self.core['gems'])
        self.assertFalse(self.core['suggestions']['enabled'])
        self.manager.configman.save_config.assert_called_once_with(self.core)
        # live apply: set_enabled called per manager
        self.arch.set_enabled.assert_called_once_with(True)
        self.flatpak.set_enabled.assert_called_once_with(False)
        # flatpak level persisted
        self.flatpak.configman.save_config.assert_called_once()

    def test_save_app_settings_invalid_flatpak_level_falls_back_to_ask(self):
        self.api.save_app_settings({'flatpak_installation_level': 'bogus'})
        saved = self.flatpak.configman.save_config.call_args[0][0]
        self.assertIsNone(saved['installation_level'])

    def test_get_app_settings_includes_tray_block(self):
        data = self.api.get_app_settings()['data']
        self.assertIn('tray', data)
        self.assertIn('available', data['tray'])  # whether the AppIndicator backend is present
        self.assertTrue(data['tray']['enabled'])
        self.assertFalse(data['tray']['minimize_to_tray'])
        self.assertEqual(60, data['tray']['update_check_interval'])

    def test_save_app_settings_persists_tray(self):
        res = self.api.save_app_settings({'tray': {'enabled': False, 'minimize_to_tray': True,
                                                   'update_check_interval': 30}})
        self.assertEqual('ok', res['status'])
        self.assertFalse(self.core['ui']['tray']['enabled'])
        self.assertTrue(self.core['ui']['tray']['minimize_to_tray'])
        self.assertEqual(30, self.core['ui']['tray']['update_check_interval'])

    def test_save_app_settings_clamps_negative_interval(self):
        self.api.save_app_settings({'tray': {'update_check_interval': -5}})
        self.assertEqual(0, self.core['ui']['tray']['update_check_interval'])

    def test_save_app_settings_ignores_non_numeric_interval(self):
        self.api.save_app_settings({'tray': {'update_check_interval': 'soon'}})
        self.assertEqual(60, self.core['ui']['tray']['update_check_interval'])  # unchanged

    def test_get_app_settings_includes_arch_block(self):
        data = self.api.get_app_settings()['data']
        self.assertIn('arch', data)
        self.assertTrue(data['arch']['available'])
        self.assertTrue(data['arch']['check_pkgbuild'])
        self.assertIn('mirror_tool', data['arch'])  # None or the detected tool name

    def test_save_app_settings_persists_arch_check_pkgbuild(self):
        res = self.api.save_app_settings({'arch': {'check_pkgbuild': False}})
        self.assertEqual('ok', res['status'])
        saved = self.arch.configman.save_config.call_args[0][0]
        self.assertFalse(saved['aur_check_pkgbuild'])


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    @patch('atlas.view.util.util.notify_user')
    def test_notifies_when_enabled(self, mock_notify):
        self.manager.configman.get_config.return_value = {'system': {'notifications': True}}
        self.api._notify('gimp installed successfully')
        mock_notify.assert_called_once_with('gimp installed successfully')

    @patch('atlas.view.util.util.notify_user')
    def test_silent_when_disabled(self, mock_notify):
        self.manager.configman.get_config.return_value = {'system': {'notifications': False}}
        self.api._notify('gimp installed successfully')
        mock_notify.assert_not_called()

    @patch('atlas.view.util.util.notify_user', side_effect=RuntimeError('boom'))
    def test_never_raises(self, mock_notify):
        self.manager.configman.get_config.return_value = {'system': {'notifications': True}}
        # must not propagate — a notification failure can't break an operation
        self.api._notify('x')


class JsonSafeTest(unittest.TestCase):
    """get_info() payloads carry datetimes (Arch first_submitted/last_modified, Flathub
    release dates) that pywebview's json.dumps can't encode — _json_safe converts them."""

    def test_converts_datetime_and_date(self):
        out = _json_safe({'08_first_submitted': datetime(2024, 5, 1, 13, 30), 'd': date(2024, 5, 1)})
        self.assertEqual('2024-05-01 13:30', out['08_first_submitted'])
        self.assertEqual('2024-05-01', out['d'])

    def test_recurses_nested_structures(self):
        out = _json_safe({'data': {'items': [{'ts': datetime(2024, 1, 2, 3, 4)}]}})
        self.assertEqual('2024-01-02 03:04', out['data']['items'][0]['ts'])

    def test_passes_through_plain_values_and_is_json_dumpable(self):
        payload = _json_safe({'a': 1, 'b': 'x', 'c': True, 'd': None, 'e': [1, 2.5]})
        self.assertEqual({'a': 1, 'b': 'x', 'c': True, 'd': None, 'e': [1, 2.5]}, payload)
        json.dumps(payload)  # must not raise


class AtlasApiOrphansTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)

    def test_serialize_pkg_registry_eviction(self):
        # Setup mock package
        pkg = Mock()
        pkg.name = "test-pkg"
        pkg.description = "desc"
        pkg.version = "1.0"
        pkg.latest_version = "1.0"
        pkg.installed = True
        pkg.update = False
        pkg.icon_url = None
        pkg.publisher = None
        pkg.size = 100
        pkg.categories = []
        pkg.get_publisher = Mock(return_value=None)
        pkg.get_type = Mock(return_value="Flatpak")

        # Populate registry to 2000 elements
        for i in range(2000):
            self.api.pkg_registry[str(i)] = Mock()

        self.assertEqual(len(self.api.pkg_registry), 2000)

        # Serialize one more package (registry size is 2000, not exceeding 2000 yet)
        res = self.api._serialize_pkg(pkg)
        pkg_id = res['id']
        self.assertEqual(len(self.api.pkg_registry), 2001)
        self.assertIn(pkg_id, self.api.pkg_registry)

        # Now force the registry size to 2005 (exceeding 2000)
        for i in range(2000, 2005):
            self.api.pkg_registry[str(i)] = Mock()

        self.assertEqual(len(self.api.pkg_registry), 2006)

        # Serialize one more package, it should trigger eviction (clear) and then add itself
        res2 = self.api._serialize_pkg(pkg)
        pkg_id2 = res2['id']
        self.assertEqual(len(self.api.pkg_registry), 1)
        self.assertIn(pkg_id2, self.api.pkg_registry)


class AtlasApiPinTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        
        self.pkg = Mock()
        self.pkg.name = "test-pin-pkg"
        self.api.pkg_registry["test-id"] = self.pkg

    def test_pin_update_success(self):
        res = self.api.pin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.ignore_update.assert_called_once_with(self.pkg)

    def test_pin_update_not_found(self):
        res = self.api.pin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_pin_update_error(self):
        self.manager.ignore_update.side_effect = Exception("Pin failed")
        res = self.api.pin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Pin failed", res['message'])

    def test_unpin_update_success(self):
        res = self.api.unpin_update("test-id")
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.revert_ignored_update.assert_called_once_with(self.pkg)

    def test_unpin_update_not_found(self):
        res = self.api.unpin_update("unknown-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unknown package id", res['message'])

    def test_unpin_update_error(self):
        self.manager.revert_ignored_update.side_effect = Exception("Unpin failed")
        res = self.api.unpin_update("test-id")
        self.assertEqual(res['status'], 'error')
        self.assertIn("Unpin failed", res['message'])


class AtlasApiExportImportTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)

    @patch('atlas.view.webview.export.open', new_callable=mock_open)
    @patch('atlas.view.webview.export.os.path.exists', return_value=True)
    def test_read_manifest_success(self, mock_exists, mock_file):
        mock_data = {
            'created': '2026-05-28T16:00:00',
            'version': 1,
            'packages': [{'name': 'Firefox', 'type': 'Flatpak'}]
        }
        mock_file.return_value.read.return_value = json.dumps(mock_data)
        
        from atlas.view.webview.export import read_manifest
        packages = read_manifest()
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]['name'], 'Firefox')

    @patch('atlas.view.webview.export.os.path.exists', return_value=False)
    def test_read_manifest_file_not_found(self, mock_exists):
        from atlas.view.webview.export import read_manifest
        with self.assertRaises(FileNotFoundError):
            read_manifest()

    @patch('atlas.view.webview.export.open', new_callable=mock_open)
    def test_write_manifest_success(self, mock_file):
        from atlas.view.webview.export import write_manifest, MANIFEST_PATH
        pkgs = [{'name': 'Firefox', 'type': 'Flatpak'}]
        path = write_manifest(pkgs)
        self.assertEqual(path, MANIFEST_PATH)
        mock_file.assert_called_once_with(MANIFEST_PATH, 'w', encoding='utf-8')

    @patch('atlas.view.webview.api.write_manifest')
    def test_export_packages_success(self, mock_write):
        mock_write.return_value = "/home/user/atlas-manifest.json"
        
        pkg = Mock()
        pkg.name = "test-pkg"
        pkg.description = "desc"
        pkg.version = "1.0"
        pkg.latest_version = "1.0"
        pkg.installed = True
        pkg.update = False
        pkg.icon_url = None
        pkg.publisher = None
        pkg.size = 100
        pkg.categories = []
        pkg.get_publisher = Mock(return_value=None)
        pkg.get_type = Mock(return_value="Flatpak")
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.export_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['count'], 1)
        self.assertEqual(res['data']['path'], "/home/user/atlas-manifest.json")
        mock_write.assert_called_once()

    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_all_skipped(self, mock_read):
        mock_read.return_value = [{'name': 'test-pkg', 'type': 'Flatpak'}]
        
        pkg = Mock()
        pkg.name = "test-pkg"
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 0)
        self.assertEqual(res['data']['skipped'], 1)
        self.assertEqual(res['data']['failed'], [])

    @patch('atlas.view.webview.api.WebviewWatcher')
    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_install_success(self, mock_read, mock_watcher_cls):
        mock_read.return_value = [{'name': 'missing-pkg', 'type': 'Flatpak'}]
        
        # Installed packages (none matching 'missing-pkg')
        installed_res = Mock()
        installed_res.installed = []
        self.manager.read_installed.return_value = installed_res
        
        # Search candidate
        candidate = Mock()
        candidate.name = "missing-pkg"
        candidate.get_type = Mock(return_value="Flatpak")
        
        search_res = Mock()
        search_res.installed = []
        search_res.new = [candidate]
        self.manager.search.return_value = search_res
        
        # Mock successful installation
        install_res = Mock()
        install_res.success = True
        self.manager.install.return_value = install_res

        # Flatpak (user) install needs no root -> broker returns (True, None)
        self.manager.requires_root.return_value = False

        # Setup self.api.window mock to prevent None error or call js
        self.api.window = Mock()
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 1)
        self.assertEqual(res['data']['skipped'], 0)
        self.assertEqual(res['data']['failed'], [])
        self.manager.install.assert_called_once_with(candidate, root_password=None, disk_loader=None, handler=mock_watcher_cls.return_value)

    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_invalid_entries_skipped(self, mock_read):
        # Manifest list has strings and None, plus one valid entry which is already installed
        mock_read.return_value = ["invalid_str", None, {'name': 'test-pkg', 'type': 'Flatpak'}]
        
        pkg = Mock()
        pkg.name = "test-pkg"
        
        installed_res = Mock()
        installed_res.installed = [pkg]
        self.manager.read_installed.return_value = installed_res
        
        res = self.api.import_packages()
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['data']['installed'], 0)
        self.assertEqual(res['data']['skipped'], 1)
        self.assertEqual(res['data']['failed'], [])


class AtlasApiRootPasswordTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        self.api.window = Mock()  # evaluate_js -> Mock, harmless

    def test_no_root_needed_returns_none_without_prompt(self):
        from atlas.api.abstract.controller import SoftwareAction
        self.manager.requires_root.return_value = False
        proceed, pwd = self.api.acquire_root_password(SoftwareAction.SEARCH, None)
        self.assertTrue(proceed)
        self.assertIsNone(pwd)
        self.api.window.evaluate_js.assert_not_called()  # no modal shown

    @patch('atlas.view.webview.api.validate_root_password')
    def test_valid_password_is_cached(self, mock_validate):
        from atlas.api.abstract.controller import SoftwareAction
        import threading
        self.manager.requires_root.return_value = True
        mock_validate.side_effect = lambda pwd, **k: pwd == 'secret'

        # Simulate the modal submitting the password once the prompt is shown.
        def poll_and_submit():
            import time
            for _ in range(100):
                if self.api.window.evaluate_js.called:
                    self.api.submit_root_password('secret')
                    return
                time.sleep(0.02)
        threading.Thread(target=poll_and_submit, daemon=True).start()

        proceed, pwd = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertTrue(proceed)
        self.assertEqual(pwd, 'secret')

        # Second call reuses the cache (validate succeeds) without prompting again.
        self.api.window.evaluate_js.reset_mock()
        proceed2, pwd2 = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertTrue(proceed2)
        self.assertEqual(pwd2, 'secret')
        self.api.window.evaluate_js.assert_not_called()

    @patch('atlas.view.webview.api.validate_root_password')
    def test_cancel_returns_false(self, mock_validate):
        from atlas.api.abstract.controller import SoftwareAction
        import threading, time
        self.manager.requires_root.return_value = True
        mock_validate.return_value = False

        def poll_and_cancel():
            for _ in range(50):
                if self.api.window.evaluate_js.called:
                    self.api.submit_root_password(None)
                    return
                time.sleep(0.02)
        threading.Thread(target=poll_and_cancel, daemon=True).start()

        proceed, pwd = self.api.acquire_root_password(SoftwareAction.INSTALL, None)
        self.assertFalse(proceed)
        self.assertIsNone(pwd)


class AtlasApiDialogTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        self.api.window = Mock()

    def _answer(self, fn):
        import threading, time

        def poll():
            for _ in range(100):
                if self.api.window.evaluate_js.called:
                    fn()
                    return
                time.sleep(0.02)
        threading.Thread(target=poll, daemon=True).start()

    def test_confirmation_accept(self):
        self._answer(lambda: self.api.submit_confirmation(True))
        confirmed, selections = self.api.prompt_confirmation('T', 'body', 'Yes', 'No')
        self.assertTrue(confirmed)
        self.assertIsNone(selections)

    def test_confirmation_deny(self):
        self._answer(lambda: self.api.submit_confirmation(False))
        confirmed, _ = self.api.prompt_confirmation('T', 'body')
        self.assertFalse(confirmed)

    def test_confirmation_no_window_defaults_true(self):
        self.api.window = None
        confirmed, selections = self.api.prompt_confirmation('T', 'body')
        self.assertTrue(confirmed)
        self.assertIsNone(selections)

    def test_confirmation_returns_component_selections(self):
        # the modal hands back per-component selections; prompt_confirmation surfaces them
        self._answer(lambda: self.api.submit_confirmation(True, [[0, 2]]))
        confirmed, selections = self.api.prompt_confirmation(
            'T', 'body', components=[{'kind': 'multiselect', 'options': []}])
        self.assertTrue(confirmed)
        self.assertEqual([[0, 2]], selections)

    def test_message_blocks_until_ack(self):
        self._answer(self.api.submit_message_ack)
        # Returns once acked; if it didn't block/return, the test would hang then time out.
        self.api.prompt_message('Title', 'Body', 'error')
        self.assertTrue(self.api._message_event.is_set())


class BatchOperationsTest(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.logger = Mock()
        self.api = AtlasApi(self.manager, self.logger)
        self.api.window = Mock()

        # Mock packages
        self.pkg1 = Mock()
        self.pkg1.name = "pkg1"
        self.pkg1.installed = True
        self.pkg1.get_type = Mock(return_value="Flatpak")
        self.pkg1.gem_name = "flatpak"

        self.pkg2 = Mock()
        self.pkg2.name = "pkg2"
        self.pkg2.installed = False
        self.pkg2.get_type = Mock(return_value="Flatpak")
        self.pkg2.gem_name = "flatpak"

        # Register packages in registry
        self.api.pkg_registry["flatpak:pkg1"] = self.pkg1
        self.api.pkg_registry["flatpak:pkg2"] = self.pkg2

    @patch('atlas.view.webview.api.WebviewWatcher')
    @patch('atlas.view.webview.api.record_activity')
    def test_batch_uninstall_success(self, mock_record, mock_watcher_cls):
        self.manager.uninstall.return_value = Mock(success=True)
        self.manager.requires_root.return_value = False

        res = self.api.batch_uninstall(["flatpak:pkg1"])
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.uninstall.assert_called_once_with(self.pkg1, root_password=None, handler=mock_watcher_cls.return_value)
        mock_record.assert_called_once_with('uninstall', 'pkg1', 'Flatpak', True)

    @patch('atlas.view.webview.api.WebviewWatcher')
    @patch('atlas.view.webview.api.record_activity')
    def test_batch_install_success(self, mock_record, mock_watcher_cls):
        self.manager.install.return_value = Mock(success=True)
        self.manager.requires_root.return_value = False

        res = self.api.batch_install(["flatpak:pkg2"])
        self.assertEqual(res, {'status': 'ok', 'success': True})
        self.manager.install.assert_called_once_with(self.pkg2, root_password=None, disk_loader=None, handler=mock_watcher_cls.return_value)
        mock_record.assert_called_once_with('install', 'pkg2', 'Flatpak', True)


class CleanupHubTest(unittest.TestCase):
    """Maintenance / "Reclaim space" panel backend (get_cleanup_summary + clean actions)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _arch_man(self, orphan_names):
        m = Mock()
        m.__module__ = 'atlas.gems.arch.controller'
        m.list_orphans.return_value = set(orphan_names)
        return m

    def _flatpak_man(self, level=None, enabled=True):
        m = Mock()
        m.__module__ = 'atlas.gems.flatpak.controller'
        m.is_enabled.return_value = enabled
        m.configman.get_config.return_value = {'installation_level': level}
        return m

    # --- get_cleanup_summary ------------------------------------------------ #
    @patch('atlas.view.webview.api.shutil.which', return_value='/usr/bin/flatpak')
    @patch('atlas.view.webview.api.get_dir_size', return_value=5000)
    @patch('atlas.view.webview.api.os.path.isdir', return_value=True)
    def test_summary_shape_and_is_cheap(self, _isdir, _dirsize, _which):
        self.manager.managers = [self._arch_man({'gjs', 'gtk2'}), self._flatpak_man()]

        res = self.api.get_cleanup_summary()

        self.assertEqual('ok', res['status'])
        data = res['data']
        self.assertEqual(2, data['orphans']['count'])
        self.assertTrue(data['pacman_cache']['available'])
        self.assertEqual(5000, data['pacman_cache']['total_bytes'])
        self.assertTrue(data['flatpak']['available'])
        # The summary must stay cheap — never trigger a full read_installed().
        self.manager.read_installed.assert_not_called()

    @patch('atlas.view.webview.api.shutil.which', return_value=None)
    @patch('atlas.view.webview.api.os.path.isdir', return_value=False)
    def test_summary_handles_missing_cache_and_flatpak(self, _isdir, _which):
        self.manager.managers = [self._arch_man(set())]
        res = self.api.get_cleanup_summary()
        self.assertEqual('ok', res['status'])
        self.assertEqual(0, res['data']['orphans']['count'])
        self.assertFalse(res['data']['pacman_cache']['available'])
        self.assertFalse(res['data']['flatpak']['available'])

    # --- clean_pacman_cache ------------------------------------------------- #
    @patch('atlas.view.webview.api.new_root_subprocess')
    @patch('atlas.view.webview.api.os.path.isdir', return_value=True)
    def test_clean_pacman_cache_cancelled_without_password(self, _isdir, mock_root):
        self.api.ensure_root_password = Mock(return_value=None)
        res = self.api.clean_pacman_cache()
        self.assertEqual('cancelled', res['status'])
        mock_root.assert_not_called()  # never shell out if the user cancels the prompt

    @patch('atlas.view.webview.api.get_dir_size', return_value=1000)
    @patch('atlas.view.webview.api.new_root_subprocess')
    @patch('atlas.view.webview.api.os.path.isdir', return_value=True)
    def test_clean_pacman_cache_error_on_nonzero(self, _isdir, mock_root, _dirsize):
        self.api.ensure_root_password = Mock(return_value='pw')
        proc = Mock(returncode=1)
        proc.communicate.return_value = (b'', b'boom')
        mock_root.return_value = proc
        res = self.api.clean_pacman_cache()
        self.assertEqual('error', res['status'])
        self.assertIn('boom', res['message'])

    # freed = cache size before minus after (real measurement, no root needed to read)
    @patch('atlas.view.webview.api.get_dir_size', side_effect=[5000, 1000])
    @patch('atlas.view.webview.api.new_root_subprocess')
    @patch('atlas.view.webview.api.os.path.isdir', return_value=True)
    def test_clean_pacman_cache_success_reports_freed(self, _isdir, mock_root, _dirsize):
        self.api.ensure_root_password = Mock(return_value='pw')
        self.api._notify = Mock()
        proc = Mock(returncode=0)
        proc.communicate.return_value = (b'', b'')
        mock_root.return_value = proc
        res = self.api.clean_pacman_cache()
        self.assertEqual('ok', res['status'])
        self.assertEqual(4000, res['freed_bytes'])
        self.assertTrue(res['freed_human'])
        self.api._notify.assert_called_once()

    # --- clean_flatpak_unused ----------------------------------------------- #
    @patch('atlas.view.webview.api.new_subprocess')
    @patch('atlas.view.webview.api.shutil.which', return_value='/usr/bin/flatpak')
    def test_clean_flatpak_unused_user_level_needs_no_root(self, _which, mock_new):
        self.manager.managers = [self._flatpak_man(level='user')]
        self.api.ensure_root_password = Mock()
        self.api._notify = Mock()
        proc = Mock(returncode=0)
        proc.communicate.return_value = (b'', b'')
        mock_new.return_value = proc

        res = self.api.clean_flatpak_unused()

        self.assertEqual('ok', res['status'])
        self.api.ensure_root_password.assert_not_called()  # user scope → no root prompt
        cmd = mock_new.call_args[0][0]
        self.assertIn('--user', cmd)
        self.assertIn('--unused', cmd)

    @patch('atlas.view.webview.api.new_root_subprocess')
    @patch('atlas.view.webview.api.shutil.which', return_value='/usr/bin/flatpak')
    def test_clean_flatpak_unused_system_level_uses_root(self, _which, mock_root):
        self.manager.managers = [self._flatpak_man(level='system')]
        self.api.ensure_root_password = Mock(return_value='pw')
        self.api._notify = Mock()
        proc = Mock(returncode=0)
        proc.communicate.return_value = (b'', b'')
        mock_root.return_value = proc

        res = self.api.clean_flatpak_unused()

        self.assertEqual('ok', res['status'])
        self.api.ensure_root_password.assert_called_once()
        cmd = mock_root.call_args[0][0]
        self.assertIn('--system', cmd)


ARCH_NEWS_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<title>Arch Linux: Recent news updates</title>
<item>
  <title>Breaking change in foo</title>
  <link>https://archlinux.org/news/breaking-foo/</link>
  <pubDate>Mon, 25 May 2026 04:58:52 +0000</pubDate>
  <description>&lt;p&gt;Users must &lt;b&gt;intervene&lt;/b&gt; manually.&lt;/p&gt;</description>
</item>
<item>
  <title>Second item</title>
  <link>https://archlinux.org/news/second/</link>
  <pubDate>Tue, 01 Jan 2026 00:00:00 +0000</pubDate>
  <description>Plain text body</description>
</item>
</channel></rss>"""


class ArchSafetyNetTest(unittest.TestCase):
    """News page (get_arch_news) + .pacnew detection (get_pacnew_files)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _mock_feed(self, text, status=200):
        client = Mock()
        client.get.return_value = Mock(status_code=status, text=text)
        self.api._http_client = Mock(return_value=client)
        return client

    # --- get_arch_news ------------------------------------------------------ #
    def test_arch_news_parses_feed(self):
        self._mock_feed(ARCH_NEWS_RSS)
        res = self.api.get_arch_news()
        self.assertEqual('ok', res['status'])
        items = res['data']
        self.assertEqual(2, len(items))
        first = items[0]
        self.assertEqual('Breaking change in foo', first['title'])
        self.assertEqual('https://archlinux.org/news/breaking-foo/', first['url'])
        self.assertEqual('May 25, 2026', first['date'])
        # HTML tags stripped, entities unescaped, whitespace collapsed
        self.assertEqual('Users must intervene manually.', first['summary'])

    def test_arch_news_respects_limit(self):
        self._mock_feed(ARCH_NEWS_RSS)
        res = self.api.get_arch_news(limit=1)
        self.assertEqual(1, len(res['data']))

    def test_arch_news_error_on_bad_response(self):
        self._mock_feed('', status=503)
        res = self.api.get_arch_news()
        self.assertEqual('error', res['status'])

    def test_arch_news_error_when_no_response(self):
        client = Mock()
        client.get.return_value = None
        self.api._http_client = Mock(return_value=client)
        res = self.api.get_arch_news()
        self.assertEqual('error', res['status'])

    # --- get_pacnew_files --------------------------------------------------- #
    @patch('atlas.view.webview.api.run_cmd')
    def test_pacnew_lists_files(self, mock_run):
        mock_run.return_value = "/etc/pacman.conf.pacnew\n/etc/ssh/sshd_config.pacnew\n"
        res = self.api.get_pacnew_files()
        self.assertEqual('ok', res['status'])
        self.assertEqual(2, res['data']['count'])
        self.assertIn('/etc/pacman.conf.pacnew', res['data']['files'])

    @patch('atlas.view.webview.api.run_cmd', return_value='')
    def test_pacnew_empty(self, _mock_run):
        res = self.api.get_pacnew_files()
        self.assertEqual('ok', res['status'])
        self.assertEqual(0, res['data']['count'])
        self.assertEqual([], res['data']['files'])

    # --- check_upgrade_news (the Update All gate) --------------------------- #
    # Feed has: "Breaking change in foo" (25 May 2026), "Second item" (01 Jan 2026).
    def test_upgrade_news_filters_to_items_newer_than_last_sync(self):
        self._mock_feed(ARCH_NEWS_RSS)
        self.api._last_db_sync_time = Mock(return_value=datetime(2026, 5, 1, tzinfo=timezone.utc))
        data = self.api.check_upgrade_news()['data']
        self.assertEqual(1, data['new_count'])                 # only the 25 May item
        self.assertEqual('Breaking change in foo', data['news'][0]['title'])
        self.assertNotIn('dt', data['news'][0])                # internal datetime not leaked

    def test_upgrade_news_none_new_when_synced_after_all_news(self):
        self._mock_feed(ARCH_NEWS_RSS)
        self.api._last_db_sync_time = Mock(return_value=datetime(2026, 6, 1, tzinfo=timezone.utc))
        data = self.api.check_upgrade_news()['data']
        self.assertEqual(0, data['new_count'])
        self.assertEqual([], data['news'])

    def test_upgrade_news_all_new_when_synced_before_all_news(self):
        self._mock_feed(ARCH_NEWS_RSS)
        self.api._last_db_sync_time = Mock(return_value=datetime(2025, 12, 1, tzinfo=timezone.utc))
        data = self.api.check_upgrade_news()['data']
        self.assertEqual(2, data['new_count'])

    def test_upgrade_news_fails_open_on_feed_error(self):
        self._mock_feed('', status=503)
        self.api._last_db_sync_time = Mock(return_value=datetime(2025, 1, 1, tzinfo=timezone.utc))
        res = self.api.check_upgrade_news()
        self.assertEqual('ok', res['status'])      # never blocks the upgrade on a check failure
        self.assertEqual(0, res['data']['new_count'])

    @patch('glob.glob', return_value=[])
    def test_last_db_sync_time_none_without_sync_dbs(self, _mock_glob):
        self.assertIsNone(self.api._last_db_sync_time())

    # --- launch_pacdiff (the .pacnew merge assist) -------------------------- #
    @patch.dict('os.environ', {'TERMINAL': ''})  # don't let a real $TERMINAL skew the test
    @patch('atlas.view.webview.api.shutil.which', return_value=None)
    def test_launch_pacdiff_errors_when_pacdiff_missing(self, _which):
        res = self.api.launch_pacdiff()
        self.assertEqual('error', res['status'])
        self.assertIn('pacman-contrib', res['message'])

    @patch.dict('os.environ', {'TERMINAL': ''})
    def test_launch_pacdiff_errors_when_no_terminal(self):
        # pacdiff present, but no terminal emulator on PATH
        with patch('atlas.view.webview.api.shutil.which', side_effect=lambda b: '/usr/bin/pacdiff' if b == 'pacdiff' else None):
            res = self.api.launch_pacdiff()
        self.assertEqual('error', res['status'])
        self.assertIn('terminal', res['message'].lower())

    @patch.dict('os.environ', {'TERMINAL': ''})
    def test_launch_pacdiff_spawns_terminal_with_sudo_pacdiff(self):
        found = {'pacdiff', 'konsole'}
        with patch('atlas.view.webview.api.shutil.which', side_effect=lambda b: f'/usr/bin/{b}' if b in found else None), \
             patch('subprocess.Popen') as mock_popen:
            res = self.api.launch_pacdiff()
        self.assertEqual('ok', res['status'])
        argv = mock_popen.call_args[0][0]
        self.assertEqual(['konsole', '-e', 'sudo', 'pacdiff'], argv)
        self.assertTrue(mock_popen.call_args[1].get('start_new_session'))

    # --- regenerate_mirrorlist --------------------------------------------- #
    def test_regen_mirrorlist_errors_when_no_tool(self):
        with patch('atlas.view.webview.api.shutil.which', return_value=None):
            res = self.api.regenerate_mirrorlist()
        self.assertEqual('error', res['status'])
        self.assertIn('reflector', res['message'])

    def test_regen_mirrorlist_prefers_reflector_and_saves(self):
        with patch('atlas.view.webview.api.shutil.which', side_effect=lambda b: '/usr/bin/reflector' if b == 'reflector' else None), \
             patch.object(self.api, 'ensure_root_password', return_value='pw'), \
             patch('atlas.view.webview.api.new_root_subprocess') as mock_proc, \
             patch.object(self.api, '_notify'):
            mock_proc.return_value.communicate.return_value = (b'', b'')
            mock_proc.return_value.returncode = 0
            res = self.api.regenerate_mirrorlist()
        self.assertEqual('ok', res['status'])
        argv = mock_proc.call_args[0][0]
        self.assertEqual('reflector', argv[0])
        self.assertIn('/etc/pacman.d/mirrorlist', argv)

    def test_regen_mirrorlist_cancelled_without_password(self):
        with patch('atlas.view.webview.api.shutil.which', return_value='/usr/bin/reflector'), \
             patch.object(self.api, 'ensure_root_password', return_value=None):
            res = self.api.regenerate_mirrorlist()
        self.assertEqual('cancelled', res['status'])

    def test_regen_mirrorlist_reports_tool_failure(self):
        with patch('atlas.view.webview.api.shutil.which', side_effect=lambda b: '/usr/bin/reflector' if b == 'reflector' else None), \
             patch.object(self.api, 'ensure_root_password', return_value='pw'), \
             patch('atlas.view.webview.api.new_root_subprocess') as mock_proc:
            mock_proc.return_value.communicate.return_value = (b'', b'no mirrors found')
            mock_proc.return_value.returncode = 1
            res = self.api.regenerate_mirrorlist()
        self.assertEqual('error', res['status'])
        self.assertIn('no mirrors', res['message'])


class RichDetailTest(unittest.TestCase):
    """Detail-modal extras: get_screenshots (Flatpak/AppImage) and get_history."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())
        self.pkg = Mock()
        self.pkg.name = 'gimp'
        self.api.pkg_registry = {'flatpak:gimp': self.pkg}

    def test_get_screenshots_returns_urls(self):
        # generator return + a falsy entry that must be filtered out
        self.manager.get_screenshots.return_value = iter(['http://a/1.png', 'http://a/2.png', ''])
        res = self.api.get_screenshots('flatpak:gimp')
        self.assertEqual('ok', res['status'])
        self.assertEqual(['http://a/1.png', 'http://a/2.png'], res['data'])

    def test_get_screenshots_unknown_pkg(self):
        res = self.api.get_screenshots('does:not-exist')
        self.assertEqual('error', res['status'])

    def test_get_history_serializes_and_marks_current(self):
        hist = Mock()
        hist.history = [{'1_version': '2.10', '3_date': datetime(2026, 1, 1, 0, 0)},
                        {'1_version': '2.11'}]
        hist.pkg_status_idx = 1
        self.manager.get_history.return_value = hist
        res = self.api.get_history('flatpak:gimp')
        self.assertEqual('ok', res['status'])
        self.assertEqual(1, res['data']['current_index'])
        self.assertEqual(2, len(res['data']['history']))
        # datetime is made JSON-safe (ISO string) by _json_safe
        self.assertIsInstance(res['data']['history'][0]['3_date'], str)

    def test_get_history_unknown_pkg(self):
        res = self.api.get_history('does:not-exist')
        self.assertEqual('error', res['status'])


class DowngradeTest(unittest.TestCase):
    """Roll back to a previous version (AtlasApi.downgrade)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())
        self.pkg = Mock()
        self.pkg.name = 'foo'
        self.pkg.get_type.return_value = 'arch_repo'
        self.pkg.gem_name = 'arch'
        self.api.pkg_registry = {'arch_repo:foo': self.pkg}

    @patch('atlas.view.webview.api.record_activity')
    @patch('atlas.view.webview.api.WebviewWatcher')
    def test_downgrade_success(self, mock_watcher_cls, mock_record):
        self.manager.requires_root.return_value = False  # → no password prompt
        self.manager.downgrade.return_value = True
        res = self.api.downgrade('arch_repo:foo')
        self.assertEqual({'status': 'ok', 'success': True}, res)
        self.manager.downgrade.assert_called_once_with(
            self.pkg, root_password=None, handler=mock_watcher_cls.return_value)
        mock_record.assert_called_once_with('downgrade', 'foo', 'arch_repo', True)

    @patch('atlas.view.webview.api.record_activity')
    def test_downgrade_cancelled_without_password(self, _mock_record):
        self.api.acquire_root_password = Mock(return_value=(False, None))
        res = self.api.downgrade('arch_repo:foo')
        self.assertEqual('cancelled', res['status'])
        self.manager.downgrade.assert_not_called()

    def test_downgrade_unknown_pkg(self):
        res = self.api.downgrade('does:not-exist')
        self.assertEqual('error', res['status'])


class BrowseCategoryTest(unittest.TestCase):
    """Browse-by-category discovery view (get_categories / get_category_packages)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

        # name -> raw category labels, mirroring atlas-files/arch/categories.txt
        self.cat_map = {
            '0ad': ['Game'],
            'dolphin-emu': ['Emulator'],     # also a Games bucket label
            'firefox': ['Network', 'Browser'],
            'gimp': ['Graphics'],
            'alsa-lib': ['Audio', 'System'],  # Audio & Video + System
            'python-foo': ['Python'],         # Development bucket
        }

        self.arch = Mock()
        self.arch.__module__ = 'atlas.gems.arch.controller'
        self.arch.read_categories.return_value = self.cat_map
        self.arch.list_category_packages.side_effect = self._list_category_packages
        self.manager.managers = [self.arch]

    def _pkg(self, name):
        p = Mock()
        p.name = name
        p.description = ''; p.version = '1'; p.latest_version = '1'; p.installed = False
        p.update = False; p.icon_url = None; p.size = 1; p.categories = self.cat_map.get(name, [])
        p.get_publisher.return_value = ''
        p.get_type.return_value = 'arch_repo'
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def _list_category_packages(self, names, limit=150):
        return [self._pkg(n) for n in sorted(names)]

    def test_get_categories_buckets_and_counts(self):
        res = self.api.get_categories()
        self.assertEqual('ok', res['status'])
        by_key = {b['key']: b for b in res['data']}

        # Game + Emulator both map into the Games bucket
        self.assertEqual(2, by_key['games']['count'])
        # Network + Browser are the same package (firefox) — distinct-package count is 1
        self.assertEqual(1, by_key['internet']['count'])
        self.assertEqual(1, by_key['graphics']['count'])
        self.assertEqual(1, by_key['multimedia']['count'])   # alsa-lib (Audio)
        self.assertEqual(1, by_key['development']['count'])   # python-foo
        self.assertEqual(1, by_key['system']['count'])        # alsa-lib (System)
        self.assertEqual('Games', by_key['games']['label'])
        # empty buckets are dropped
        self.assertNotIn('office', by_key)

    def test_get_category_packages_resolves_via_arch_gem(self):
        res = self.api.get_category_packages('games')
        self.assertEqual('ok', res['status'])
        names = sorted(p['name'] for p in res['data'])
        self.assertEqual(['0ad', 'dolphin-emu'], names)
        # the arch gem got exactly the matching names
        called_names = set(self.arch.list_category_packages.call_args[0][0])
        self.assertEqual({'0ad', 'dolphin-emu'}, called_names)

    def test_get_category_packages_unknown_key(self):
        res = self.api.get_category_packages('not-a-bucket')
        self.assertEqual('error', res['status'])

    def test_categories_no_arch_gem(self):
        self.manager.managers = []
        res = self.api.get_categories()
        self.assertEqual('ok', res['status'])
        self.assertEqual([], res['data'])


