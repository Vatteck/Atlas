from getpass import getuser
from pathlib import Path

from atlas.api import user

__path_name__ = 'atlaspm'


def get_temp_dir(username: str) -> str:
    return f'/tmp/{__path_name__}@{username}'


CACHE_DIR = f'/var/cache/{__path_name__}' if user.is_root() else f'{Path.home()}/.cache/{__path_name__}'
CONFIG_DIR = f'/etc/{__path_name__}' if user.is_root() else f'{Path.home()}/.config/{__path_name__}'
DESKTOP_ENTRIES_DIR = '/usr/share/applications' if user.is_root() else f'{Path.home()}/.local/share/applications'
TEMP_DIR = get_temp_dir(getuser())
LOGS_DIR = f'{TEMP_DIR}/logs'
# Persistent, rotating application log (survives reboots, unlike LOGS_DIR in /tmp) — a small record
# of recent runs for after-the-fact debugging.
APP_LOG_DIR = f'{CACHE_DIR}/logs'
APP_LOG_FILE = f'{APP_LOG_DIR}/atlas.log'
AUTOSTART_DIR = f'/etc/xdg/autostart' if user.is_root() else f'{Path.home()}/.config/autostart'
BINARIES_DIR = f'/usr/local/bin' if user.is_root() else f'{Path.home()}/.local/bin'
SHARED_FILES_DIR = f'/usr/local/share/{__path_name__}' if user.is_root() else f'{Path.home()}/.local/share/{__path_name__}'
# Persistent WebKit storage (localStorage) for the pywebview front-end. Without a storage_path
# pywebview runs WebKit in private mode and discards localStorage on exit, so every UI preference
# (theme, density, view/sort mode, Browse resume, mirror options) silently resets each launch.
# A data dir (not cache) — these are user preferences, not regenerable.
WEBVIEW_STORAGE_DIR = f'{Path.home()}/.local/share/{__path_name__}/webview'
