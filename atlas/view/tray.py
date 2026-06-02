"""System-tray indicator for Atlas (non-Qt).

A pure-Python tray built on **AyatanaAppIndicator3** (falling back to the older
AppIndicator3), which emits a StatusNotifierItem — the freedesktop tray protocol KDE Plasma
shows natively. It rides the same GTK3 main loop pywebview already runs, so it needs no second
toolkit and no Qt.

The tray is *additive and optional*: if the AppIndicator typelib is absent (the
`libayatana-appindicator` system package isn't installed) or it's disabled in config,
``start()`` logs and returns ``None`` and the app behaves exactly as before.

Design notes: docs/plans/2026-06-02-system-tray.md.
"""
import logging
import os
from typing import Optional

# --- backend probe (graceful: a missing typelib must never break app launch) ----------------
_APPINDICATOR = None
_GTK_OK = False
try:
    import gi

    _indicator_ns = None
    for _ns in ('AyatanaAppIndicator3', 'AppIndicator3'):
        try:
            gi.require_version(_ns, '0.1')
            _indicator_ns = _ns
            break
        except (ValueError, ImportError):
            continue

    if _indicator_ns:
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, GLib  # noqa: E402
        if _indicator_ns == 'AyatanaAppIndicator3':
            from gi.repository import AyatanaAppIndicator3 as _APPINDICATOR  # noqa: E402
        else:
            from gi.repository import AppIndicator3 as _APPINDICATOR  # noqa: E402
        _GTK_OK = True
except (ValueError, ImportError):
    _APPINDICATOR = None


TRAY_AVAILABLE = _APPINDICATOR is not None and _GTK_OK


# --- pure helpers (unit-testable without GTK) ------------------------------------------------
def toggle_label(visible: bool) -> str:
    """Label for the show/hide menu item given current window visibility."""
    return 'Hide Atlas' if visible else 'Show Atlas'


def should_cancel_close(quitting: bool, minimize_to_tray: bool, has_indicator: bool) -> bool:
    """Whether a window-close should be cancelled (i.e. hidden to tray) instead of quitting.

    Only when the user hasn't chosen Quit, close-to-tray is enabled, and a tray icon actually
    exists to restore the window from — otherwise the window would vanish with no way back.
    """
    return bool(minimize_to_tray) and bool(has_indicator) and not bool(quitting)


def _tray_config(config: dict) -> dict:
    return ((config or {}).get('ui') or {}).get('tray') or {}


class AtlasTray:
    """Owns the AppIndicator and its menu. All GTK objects are touched on the GTK main thread."""

    def __init__(self, window, config: dict, logger: logging.Logger, icon_path: str):
        self.window = window
        self.config = config
        self.logger = logger
        self.icon_path = icon_path
        self.indicator = None
        self._visible = True
        self._quitting = False
        self._item_toggle = None
        self.minimize_to_tray = bool(_tray_config(config).get('minimize_to_tray', False))

    # -- construction (runs on the GTK main thread via GLib.idle_add) -------------------------
    def _resolve_icon_name(self) -> str:
        """AppIndicator wants a *themed icon name*, not a path. Use the installed `atlas-pm`
        hicolor icon when present; otherwise add our bundled img dir to the icon search path and
        use the file's basename (e.g. `logo`) so it also works when running from source."""
        icon_dir = os.path.dirname(self.icon_path)
        name = 'atlas-pm'
        try:
            theme = Gtk.IconTheme.get_default()
            theme.append_search_path(icon_dir)
            if not theme.has_icon(name):
                name = os.path.splitext(os.path.basename(self.icon_path))[0]
        except Exception as e:  # never let icon resolution stop the tray from appearing
            self.logger.debug(f"tray icon-theme lookup failed, using basename: {e}")
            name = os.path.splitext(os.path.basename(self.icon_path))[0]
        return name

    def build(self) -> bool:
        try:
            icon_name = self._resolve_icon_name()
            self.indicator = _APPINDICATOR.Indicator.new(
                'atlas-pm', icon_name, _APPINDICATOR.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(_APPINDICATOR.IndicatorStatus.ACTIVE)
            self.indicator.set_title('Atlas')
            self.indicator.set_menu(self._build_menu())
            self.logger.info(f"System tray active (AppIndicator, icon='{icon_name}').")
        except Exception as e:
            self.logger.error(f"Could not build the system tray indicator: {e}")
            self.indicator = None
        return False  # one-shot for GLib.idle_add

    def _build_menu(self):
        menu = Gtk.Menu()

        self._item_toggle = Gtk.MenuItem(label=toggle_label(self._visible))
        self._item_toggle.connect('activate', self._on_toggle)
        menu.append(self._item_toggle)

        item_updates = Gtk.MenuItem(label='Check for updates')
        item_updates.connect('activate', self._on_updates)
        menu.append(item_updates)

        menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label='Quit Atlas')
        item_quit.connect('activate', self._on_quit)
        menu.append(item_quit)

        menu.show_all()
        return menu

    # -- state helpers ------------------------------------------------------------------------
    def _set_visible(self, visible: bool):
        self._visible = visible
        if self._item_toggle is not None:
            self._item_toggle.set_label(toggle_label(visible))

    def _show_window(self):
        try:
            self.window.show()
            self.window.restore()
        except Exception as e:
            self.logger.error(f"Could not show window from tray: {e}")
        self._set_visible(True)

    def _hide_window(self):
        try:
            self.window.hide()
        except Exception as e:
            self.logger.error(f"Could not hide window from tray: {e}")
        self._set_visible(False)

    # -- menu callbacks (GTK main thread) -----------------------------------------------------
    def _on_toggle(self, _item):
        if self._visible:
            self._hide_window()
        else:
            self._show_window()

    def _on_updates(self, _item):
        self._show_window()
        try:
            self.window.evaluate_js("activateView('updates')")
        except Exception as e:
            self.logger.error(f"Could not navigate to updates from tray: {e}")

    def _on_quit(self, _item):
        self._quitting = True
        try:
            self.window.destroy()
        except Exception as e:
            self.logger.error(f"Could not quit from tray: {e}")

    # -- window close hook (subscribed to window.events.closing) ------------------------------
    def on_closing(self):
        """Return False to cancel the close (hide to tray) when close-to-tray is on.

        Fired synchronously on the GTK main thread (pywebview's `closing` event uses
        ``should_lock``), so we can hide the window inline — no GLib.idle_add hop needed.
        """
        if not should_cancel_close(self._quitting, self.minimize_to_tray, self.indicator is not None):
            return None  # allow the close (real quit)
        self._hide_window()
        return False


def start(window, config: dict, logger: logging.Logger, icon_path: str) -> Optional[AtlasTray]:
    """Create the tray and wire it to the window. Safe to call unconditionally.

    Returns the AtlasTray (or None when unavailable/disabled). The indicator itself is built on
    the GTK main loop via GLib.idle_add, so this can be called before ``webview.start()``.
    """
    if not TRAY_AVAILABLE:
        logger.info("System tray unavailable (AppIndicator typelib not found) — skipping.")
        return None

    if not bool(_tray_config(config).get('enabled', True)):
        logger.info("System tray disabled in config — skipping.")
        return None

    tray = AtlasTray(window, config, logger, icon_path)
    try:
        window.events.closing += tray.on_closing
    except Exception as e:
        logger.error(f"Could not hook window close for the tray: {e}")
    GLib.idle_add(tray.build)
    return tray
