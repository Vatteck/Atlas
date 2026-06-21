import faulthandler
import inspect
import locale
import logging
import os
import sys
import threading
import traceback

from atlas import __app_name__, app_args
from atlas.view.core.config import CoreConfigManager
from atlas.view.util import logs

# NOTE: `urllib3` is intentionally NOT imported here. It (and the requests stack) is ~155 ms of
# import time and is only needed once a network call happens — long after the window is shown. The
# InsecureRequestWarning suppression that used to live here now happens lazily in HttpClient when
# its session is first created. See docs/plans/2026-06-20-launch-optimization.md.


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

    args = app_args.read()

    # Diagnostic, no GUI — gather the environment and exit before any backend init.
    if getattr(args, 'self_check', False):
        from atlas import self_check
        sys.exit(self_check.run())

    logger = logs.new_logger(__app_name__, bool(args.logs))

    # Route uncaught exceptions through the logger so a crash is captured in the rotating log file
    # (for after-the-fact debugging), not just printed to a terminal nobody saved. Ctrl-C is left
    # to the default handler.
    def _log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _log_uncaught

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

    force_suggestions = bool(args.suggestions)

    def build_manager():
        """Build the backend orchestrator: i18n + context + gems + GenericSoftwareManager. This is
        the heavy part of startup (gem probing + load_managers I/O). Under window-first startup it
        runs on a background thread *after* the window is shown, so the window appears ~500 ms
        sooner; the front-end shows a boot splash until set_manager() releases it. See
        docs/plans/2026-06-20-launch-optimization.md."""
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
        return GenericSoftwareManager(managers, context=context, config=app_config, force_suggestions=force_suggestions)

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

    # Strangler-fig: window-first startup is the default; ATLAS_LEGACY_STARTUP=1 restores the old
    # synchronous path (build the whole backend before the window) as a fallback if window-first
    # ever misbehaves. See docs/plans/2026-06-20-launch-optimization.md.
    window_first = os.environ.get('ATLAS_LEGACY_STARTUP') != '1'

    manager = None if window_first else build_manager()
    api = AtlasApi(manager, logger)

    html_path = 'file://' + os.path.abspath(os.path.join(os.path.dirname(__file__), 'view', 'webview', 'index.html'))

    # Pin the program name so the window identity is stable and matches the installed
    # `atlas-pm.desktop`. GTK derives the Wayland app_id (and X11 WM_CLASS) from the program
    # name, which otherwise defaults to argv[0]'s basename — e.g. 'app.py' under
    # `python -m atlas.app`, matching no desktop file → fallback icon.
    #
    # Use 'atlas-pm', NOT the bare 'atlas': KDE/Plasma resolves a window's icon by an
    # app_id→icon-name lookup, and several icon themes (char-white, Tela, Fluent, WhiteSur, …)
    # ship a generic 'atlas' icon (a map) that would win over the desktop file's Icon=. The
    # unique 'atlas-pm' collides with no theme and matches atlas-pm.desktop (Icon=atlas-pm).
    try:
        from gi.repository import GLib
        GLib.set_prgname('atlas-pm')
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

    # Force the GTK/WebKit backend — Atlas's documented (and only depended-on) stack. Otherwise
    # pywebview auto-detects and may try Qt first: on a box without qtpy that prints a scary (but
    # non-fatal — it falls back to GTK) traceback, and a Qt window wouldn't honour the GTK app_id
    # we pin via set_prgname. Respect an explicit PYWEBVIEW_GUI override if the user set one.
    if not os.environ.get('PYWEBVIEW_GUI'):
        start_kwargs['gui'] = 'gtk'

    # System-tray indicator (non-Qt, AppIndicator/SNI). Additive and optional: a missing typelib
    # or a disabled config flag makes this a no-op. The indicator is built on the GTK main loop
    # (GLib.idle_add), so it's safe to wire from any thread — it materializes once the loop runs.
    # Reuses the same logo.png as the window icon (icon_path above).
    def _start_tray(mgr):
        try:
            from atlas.view import tray as tray_mod
            tray_mod.start(window, mgr, app_config, logger, icon_path)
        except Exception as e:
            logger.error(f"Could not initialize the system tray: {e}")

    if window_first:
        # Build the backend off the main thread so webview.start() (GTK/WebKit window construction,
        # mostly native and GIL-releasing) runs concurrently — the window appears without waiting on
        # gem probing. set_manager() releases any API calls the front-end made in the meantime.
        def _build_backend():
            try:
                mgr = build_manager()
            except Exception:
                logger.error("Backend initialization failed", exc_info=True)
                return
            api.set_manager(mgr)
            _start_tray(mgr)
        threading.Thread(target=_build_backend, name='atlas-backend-build', daemon=True).start()
    else:
        _start_tray(manager)

    webview.start(**start_kwargs)
    sys.exit(0)


if __name__ == '__main__':
    main()
