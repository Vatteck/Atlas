import faulthandler
import inspect
import locale
import logging
import os
import sys
import traceback

import urllib3

from atlas import __app_name__, app_args
from atlas.view.core.config import CoreConfigManager
from atlas.view.util import logs


def main():
    if not os.getenv('PYTHONUNBUFFERED'):
        os.environ['PYTHONUNBUFFERED'] = '1'

    if not os.getenv('XDG_RUNTIME_DIR'):
        os.environ['XDG_RUNTIME_DIR'] = f'/run/user/{os.getuid()}'

    # Workaround for WebKitGTK Wayland driver bugs / Protocol Error 71 crashes
    if sys.platform.startswith('linux'):
        if not os.getenv('WEBKIT_DISABLE_COMPOSITING_MODE'):
            os.environ['WEBKIT_DISABLE_COMPOSITING_MODE'] = '1'
        if not os.getenv('WEBKIT_DISABLE_DMABUF_RENDERER'):
            os.environ['WEBKIT_DISABLE_DMABUF_RENDERER'] = '1'

    faulthandler.enable()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    args = app_args.read()

    logger = logs.new_logger(__app_name__, bool(args.logs))

    try:
        locale.setlocale(locale.LC_NUMERIC, '')
    except Exception:
        logger.error("Could not set locale 'LC_NUMBERIC' to '' to display localized numbers")
        traceback.print_exc()

    if args.offline:
        logger.warning("offline mode activated")

    app_config = CoreConfigManager().get_config()

    # (Display scaling for the old Qt UI was removed — the pywebview/GTK front-end scales
    # via GDK_SCALE/GDK_DPI_SCALE; the old QT_SCALE_FACTOR/HDPI knobs did nothing here.)

    if bool(args.suggestions):
        logger.info("Forcing loading software suggestions after the initialization process")

    # Initialize the backend managers and launch the pywebview window
    from atlas.api import user
    from atlas.api.abstract.context import ApplicationContext
    from atlas.api.http import HttpClient
    from atlas.commons.internet import InternetChecker
    from atlas.context import generate_i18n, DEFAULT_I18N_KEY
    from atlas.view.core import gems
    from atlas.view.core.controller import GenericSoftwareManager
    from atlas.view.util import resource, util
    from atlas.view.util.cache import DefaultMemoryCacheFactory
    from atlas.view.util.disk import DefaultDiskCacheLoaderFactory
    from atlas import ROOT_DIR, __version__

    i18n = generate_i18n(app_config, resource.get_path('locale'))
    cache_factory = DefaultMemoryCacheFactory(expiration_time=int(app_config['memory_cache']['data_expiration']))
    http_client = HttpClient(logger)

    context = ApplicationContext(i18n=i18n,
                                 http_client=http_client,
                                 download_icons=bool(app_config['download']['icons']),
                                 app_root_dir=ROOT_DIR,
                                 cache_factory=cache_factory,
                                 disk_loader_factory=DefaultDiskCacheLoaderFactory(logger),
                                 logger=logger,
                                 distro=util.get_distro(),
                                 file_downloader=None,
                                 app_name=__app_name__,
                                 app_version=__version__,
                                 internet_checker=InternetChecker(offline=args.offline),
                                 suggestions_mapping={},
                                 root_user=user.is_root())

    managers = gems.load_managers(context=context, locale=i18n.current_key, config=app_config, default_locale=DEFAULT_I18N_KEY, logger=logger)
    force_suggestions = bool(args.suggestions)
    manager = GenericSoftwareManager(managers, context=context, config=app_config, force_suggestions=force_suggestions)

    # Launch pywebview Native Window
    import webview
    from atlas.view.webview.api import AtlasApi

    # Drop only pywebview's harmless "Error while processing window.native.* : unable to get
    # the value" lines (a few GTK window internals it can't expose to JS). This is a targeted
    # filter — every other pywebview log record (including real errors on any desktop) still
    # comes through, so it doesn't hide anything debuggable.
    class _PywebviewNativeNoiseFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage()
            return not ('Error while processing window.native.' in msg
                        and 'unable to get the value' in msg)

    logging.getLogger('pywebview').addFilter(_PywebviewNativeNoiseFilter())

    api = AtlasApi(manager, logger)

    html_path = 'file://' + os.path.abspath(os.path.join(os.path.dirname(__file__), 'view', 'webview', 'index.html'))

    # Pin the program name so the window identity is stable and matches the installed
    # `atlas.desktop`. On Wayland the compositor/dock/switcher resolves a window's icon by
    # matching its app_id to a .desktop file (then reading that file's Icon=); GTK derives the
    # app_id (and the X11 WM_CLASS) from the program name, which otherwise defaults to argv[0]'s
    # basename — e.g. 'app.py' under `python -m atlas.app`, matching no desktop file → fallback
    # icon. Setting it to 'atlas' makes app_id='atlas', which matches atlas.desktop (Icon=atlas-pm).
    try:
        from gi.repository import GLib
        GLib.set_prgname('atlas')
    except Exception:
        pass  # non-GTK backend / gi unavailable — harmless

    window = webview.create_window(
        'Atlas',
        html_path,
        js_api=api,
        width=1000,
        height=700,
        min_size=(400, 400)
    )
    api.set_window(window)

    # X11 complement to the app_id pinning above: set an explicit window icon (_NET_WM_ICON)
    # so X11 WMs that show a per-window icon (titlebar / taskbar / alt-tab) use our bundled
    # logo instead of falling back to the WM_CLASS theme lookup (a generic 'atlas' map icon).
    # Wayland ignores client-set window icons and uses the app_id→.desktop match instead, so
    # this is mostly a no-op there. The `icon` start param is GTK/Qt-only and was added in
    # pywebview 4.2 — feature-detect so the app still launches on older pywebview.
    start_kwargs = {'debug': bool(args.logs)}
    icon_path = os.path.join(os.path.dirname(__file__), 'view', 'resources', 'img', 'logo.png')
    try:
        if os.path.exists(icon_path) and 'icon' in inspect.signature(webview.start).parameters:
            start_kwargs['icon'] = icon_path
    except (TypeError, ValueError):
        pass

    webview.start(**start_kwargs)
    sys.exit(0)


if __name__ == '__main__':
    main()
