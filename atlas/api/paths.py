from getpass import getuser
from pathlib import Path

from atlas.api import user

__path_name__ = 'atlaspm'


def get_temp_dir(username: str) -> str:
    return f'/tmp/{__path_name__}@{username}'


CACHE_DIR = f'/var/cache/{__path_name__}' if user.is_root() else f'{Path.home()}/.cache/{__path_name__}'
CONFIG_DIR = f'/etc/{__path_name__}' if user.is_root() else f'{Path.home()}/.config/{__path_name__}'
USER_THEMES_DIR = f'/usr/share/{__path_name__}/themes' if user.is_root() else f'{Path.home()}/.local/share/{__path_name__}/themes'
DESKTOP_ENTRIES_DIR = '/usr/share/applications' if user.is_root() else f'{Path.home()}/.local/share/applications'
TEMP_DIR = get_temp_dir(getuser())
LOGS_DIR = f'{TEMP_DIR}/logs'
AUTOSTART_DIR = f'/etc/xdg/autostart' if user.is_root() else f'{Path.home()}/.config/autostart'
BINARIES_DIR = f'/usr/local/bin' if user.is_root() else f'{Path.home()}/.local/bin'
SHARED_FILES_DIR = f'/usr/local/share/{__path_name__}' if user.is_root() else f'{Path.home()}/.local/share/{__path_name__}'
