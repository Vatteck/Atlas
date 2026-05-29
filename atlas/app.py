import faulthandler
import locale
import os
import sys
import traceback

import urllib3

from atlas import __app_name__, app_args
from atlas.view.core.config import CoreConfigManager
from atlas.view.util import logs


def main(tray: bool = False):
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

    if bool(app_config['ui']['auto_scale']):
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        logger.info("Auto screen scale factor activated")

    try:
        scale_factor = float(app_config['ui']['scale_factor'])
        os.environ['QT_SCALE_FACTOR'] = str(scale_factor)
        logger.info("Scale factor set to {}".format(scale_factor))
    except Exception:
        traceback.print_exc()

    if bool(app_config['ui']['hdpi']):
        logger.info("HDPI settings activated")
        try:
            from PyQt5.QtCore import QCoreApplication, Qt
            QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
            QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        except ImportError:
            logger.warning("PyQt5 is not installed; skipped HDPI scaling attributes.")

    if bool(args.suggestions):
        logger.info("Forcing loading software suggestions after the initialization process")

    if tray or bool(args.tray):
        from atlas.tray import new_tray_icon
        app, widget = new_tray_icon(app_config, logger)
        widget.show()
        sys.exit(app.exec_())
    else:
        from atlas.manage import new_manage_panel
        # We still initialize the backend managers
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
        from atlas.view.webview.api import BauhApi
        
        api = BauhApi(manager, logger)
        
        html_path = 'file://' + os.path.abspath(os.path.join(os.path.dirname(__file__), 'view', 'web', 'index.html'))
        
        window = webview.create_window(
            'bauh', 
            html_path,
            js_api=api,
            width=1000,
            height=700,
            min_size=(800, 600)
        )
        api.set_window(window)
        webview.start(debug=bool(args.logs))
        sys.exit(0)


def tray():
    main(tray=True)


if __name__ == '__main__':
    main()
