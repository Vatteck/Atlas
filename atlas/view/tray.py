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
import math
import os
import shutil
import tempfile
import threading
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


def count_updates(result) -> int:
    """Number of installed packages with a pending update, from a SearchResult-like object."""
    installed = getattr(result, 'installed', None) or []
    return sum(1 for p in installed if getattr(p, 'update', False))


def updates_menu_label(count: int) -> str:
    """Label for the updates menu item; reflects the count when there are any."""
    return f"Updates available: {count}" if count and count > 0 else 'Check for updates'


def badge_text(count: int) -> str:
    """Text drawn in the icon badge; capped so it stays legible. Empty when nothing to update."""
    if not count or count <= 0:
        return ''
    return str(count) if count <= 99 else '99+'


def tray_label_text(count: int) -> str:
    """Text for the AppIndicator label (shown on Unity/GNOME; KDE ignores it — we badge the icon
    instead). Empty when there's nothing to update."""
    return badge_text(count)


def poll_interval_minutes(config: dict) -> int:
    """Tray update-poll interval in minutes (<= 0 disables polling). Tolerates junk values."""
    try:
        return int(_tray_config(config).get('update_check_interval', 60) or 0)
    except (TypeError, ValueError):
        return 0


def _tray_config(config: dict) -> dict:
    return ((config or {}).get('ui') or {}).get('tray') or {}


class AtlasTray:
    """Owns the AppIndicator and its menu. All GTK objects are touched on the GTK main thread."""

    # Wait this long after the indicator builds before the first update poll, so it doesn't
    # pile onto the app's already-busy startup (gem init, suggestions, the dashboard's own read).
    INITIAL_POLL_DELAY_SECONDS = 30

    def __init__(self, window, manager, config: dict, logger: logging.Logger, icon_path: str):
        self.window = window
        self.manager = manager
        self.config = config
        self.logger = logger
        self.icon_path = icon_path
        self.indicator = None
        self._visible = True
        self._quitting = False
        self._item_toggle = None
        self._item_updates = None
        self._update_count = 0
        self._icon_tmp_dir = None     # temp dir for rendered badge PNGs (created lazily)
        self._base_icon_name = None   # the proven themed name for the un-badged logo (zero state)
        self.minimize_to_tray = bool(_tray_config(config).get('minimize_to_tray', False))
        self.poll_minutes = poll_interval_minutes(config)
        self._stop = threading.Event()
        self._poll_thread = None

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
            self._base_icon_name = icon_name
            self.indicator = _APPINDICATOR.Indicator.new(
                'atlas-pm', icon_name, _APPINDICATOR.IndicatorCategory.APPLICATION_STATUS)
            self.indicator.set_status(_APPINDICATOR.IndicatorStatus.ACTIVE)
            self.indicator.set_title('Atlas')
            self.indicator.set_menu(self._build_menu())
            self.logger.info(f"System tray active (AppIndicator, icon='{icon_name}').")
            self._start_poller()
        except Exception as e:
            self.logger.error(f"Could not build the system tray indicator: {e}")
            self.indicator = None
        return False  # one-shot for GLib.idle_add

    def _build_menu(self):
        menu = Gtk.Menu()

        self._item_toggle = Gtk.MenuItem(label=toggle_label(self._visible))
        self._item_toggle.connect('activate', self._on_toggle)
        menu.append(self._item_toggle)

        self._item_updates = Gtk.MenuItem(label=updates_menu_label(self._update_count))
        self._item_updates.connect('activate', self._on_updates)
        menu.append(self._item_updates)

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

    # -- update-count polling -----------------------------------------------------------------
    # read_installed() is heavyweight (full installed read), so we poll it on a daemon thread at
    # a long, configurable interval and push the count back to the GTK thread via idle_add.
    def _start_poller(self):
        if self.manager is None or self.poll_minutes <= 0:
            self.logger.info("Tray update polling disabled (no manager or interval <= 0).")
            return
        if self._poll_thread is not None:
            return
        self._poll_thread = threading.Thread(target=self._poll_loop, name='atlas-tray-updates', daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        # interruptible sleeps: _stop.wait() returns True the moment we're asked to quit
        if self._stop.wait(self.INITIAL_POLL_DELAY_SECONDS):
            return
        interval_seconds = self.poll_minutes * 60
        while not self._stop.is_set():
            self._poll_once()
            if self._stop.wait(interval_seconds):
                return

    def _poll_once(self):
        try:
            count = count_updates(self.manager.read_installed())
        except Exception as e:
            self.logger.warning(f"Tray update check failed: {e}")
            return
        # GTK widgets must be touched on the main loop; the webview push must NOT (evaluate_js
        # blocks the calling thread on a semaphore the main loop has to release — calling it on
        # the main thread deadlocks). So: schedule the GTK update, push to the webview inline
        # (we're on the poller's background thread here).
        GLib.idle_add(self._apply_count, count)
        self._push_badge_to_webview(count)

    def _push_badge_to_webview(self, count: int):
        """Update the in-app sidebar badge. MUST be called off the GTK main thread."""
        if self.window is None:
            return
        try:
            self.window.evaluate_js(f"window.setUpdatesBadge && window.setUpdatesBadge({int(count)});")
        except Exception as e:
            self.logger.debug(f"could not push update count to the webview: {e}")

    def _apply_count(self, count: int) -> bool:
        """GTK-only updates (label / icon / menu). Runs on the GTK main thread via idle_add —
        so it must never call evaluate_js (see _push_badge_to_webview)."""
        self._update_count = count
        if self.indicator is not None:
            label = tray_label_text(count)
            try:
                self.indicator.set_label(label, label)  # Unity/GNOME show this; KDE ignores it
            except Exception as e:
                self.logger.debug(f"tray set_label failed: {e}")
            self._set_icon_for_count(count)  # the visible cue on KDE: a badge on the icon
        if self._item_updates is not None:
            self._item_updates.set_label(updates_menu_label(count))
        return False  # one-shot for GLib.idle_add

    # -- icon badge (KDE doesn't render set_label, so draw the count onto the icon) -----------
    def _set_icon_for_count(self, count: int):
        if self.indicator is None:
            return
        try:
            if count and count > 0:
                path = self._render_badge_icon(count)
                if path:
                    # An absolute path makes AppIndicator load the file as a pixmap — the only way
                    # KDE reliably shows a custom (non-themed) icon. set_icon_theme_path + a bare
                    # name does NOT work on KDE's SNI host (falls back to the "A" letter avatar).
                    self.indicator.set_icon_full(path, f"{count} update(s) available")
                    return
            # Zero state: restore the proven themed name (never regress the base icon).
            if self._base_icon_name:
                self.indicator.set_icon_full(self._base_icon_name, 'Atlas')
        except Exception as e:
            self.logger.debug(f"tray set_icon failed: {e}")

    def _render_badge_icon(self, count: int) -> Optional[str]:
        """Composite a red count badge onto the logo; return the absolute path of the PNG."""
        try:
            import cairo
            gi.require_version('Gdk', '3.0')
            from gi.repository import GdkPixbuf, Gdk

            if not self._icon_tmp_dir:
                self._icon_tmp_dir = tempfile.mkdtemp(prefix='atlas-tray-')

            text = badge_text(count)
            size = 64
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(self.icon_path, size, size)
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            ctx = cairo.Context(surface)
            Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
            ctx.paint()

            radius = 19
            cx, cy = size - radius - 2, radius + 2  # top-right corner
            # white ring first, so the red bubble stays legible on our dark-red logo (or any bg)
            ctx.set_source_rgb(1, 1, 1)
            ctx.arc(cx, cy, radius + 2.5, 0, 2 * math.pi)
            ctx.fill()
            ctx.set_source_rgb(0.85, 0.12, 0.12)
            ctx.arc(cx, cy, radius, 0, 2 * math.pi)
            ctx.fill()

            ctx.set_source_rgb(1, 1, 1)
            ctx.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            ctx.set_font_size(28 if len(text) <= 1 else (22 if len(text) <= 2 else 16))
            ext = ctx.text_extents(text)
            ctx.move_to(cx - (ext.width / 2 + ext.x_bearing), cy - (ext.height / 2 + ext.y_bearing))
            ctx.show_text(text)

            path = os.path.join(self._icon_tmp_dir, 'atlas-tray-' + text.replace('+', 'plus') + '.png')
            surface.write_to_png(path)
            return path
        except Exception as e:
            self.logger.debug(f"tray badge render failed: {e}")
            return None

    # -- menu callbacks (GTK main thread) -----------------------------------------------------
    def _on_toggle(self, _item):
        if self._visible:
            self._hide_window()
        else:
            self._show_window()

    def _on_updates(self, _item):
        self._show_window()  # GTK window op — safe on the main thread

        # evaluate_js must run OFF the GTK main thread (it blocks the caller on a semaphore the
        # main loop releases — calling it here would deadlock the UI). Navigate + recount on a
        # worker thread.
        def navigate_and_recount():
            if self.window is not None:
                try:
                    self.window.evaluate_js("activateView('updates')")
                except Exception as e:
                    self.logger.error(f"Could not navigate to updates from tray: {e}")
            if self.manager is not None:
                self._poll_once()

        threading.Thread(target=navigate_and_recount, name='atlas-tray-open-updates', daemon=True).start()

    def _on_quit(self, _item):
        self._quitting = True
        self._stop.set()  # stop the poller's interruptible sleep
        if self._icon_tmp_dir:
            shutil.rmtree(self._icon_tmp_dir, ignore_errors=True)
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


def start(window, manager, config: dict, logger: logging.Logger, icon_path: str) -> Optional[AtlasTray]:
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

    tray = AtlasTray(window, manager, config, logger, icon_path)
    try:
        window.events.closing += tray.on_closing
    except Exception as e:
        logger.error(f"Could not hook window close for the tray: {e}")
    GLib.idle_add(tray.build)
    return tray
