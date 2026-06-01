import os
import shutil
import subprocess
import sys
import traceback
from typing import List

from colorama import Fore

from atlas import __app_name__
from atlas.api.abstract.controller import SoftwareManager
from atlas.api.paths import CONFIG_DIR, CACHE_DIR, TEMP_DIR
from atlas.commons.system import run_cmd
from atlas.view.util import resource


def notify_user(msg: str, icon_path: str = None):
    icon_id = icon_path or get_default_icon_path()

    os.system("notify-send -a {} {} '{}'".format(__app_name__, "-i {}".format(icon_id) if icon_id else '', msg))


def get_default_icon_path() -> str:
    """Bundled icon path for desktop notifications. We pass the file path (not the app
    name) because notify-send would otherwise resolve the themed name 'atlas' to an
    unrelated system icon (e.g. a Maps app)."""
    return resource.get_path('img/logo.png')


def restart_app():
    appimage_path = os.getenv('APPIMAGE')

    restart_cmd = [appimage_path] if appimage_path else [sys.executable, *sys.argv]

    subprocess.Popen(restart_cmd)

    # Stop the pywebview/GTK main loop so app.py returns from webview.start() and exits;
    # the freshly Popen'd process takes over. (Replaces the old Qt QCoreApplication.exit().)
    try:
        import webview
        for window in list(getattr(webview, 'windows', []) or []):
            window.destroy()
    except Exception:
        os._exit(0)


def get_distro():
    if os.path.exists('/etc/arch-release'):
        return 'arch'

    if os.path.exists('/etc/os-release'):
        with open('/etc/os-release', 'r') as os_release_file:
            for line in os_release_file:
                if 'ID_LIKE=arch' in line:
                    return 'arch'

    if os.path.exists('/proc/version'):
        if 'ubuntu' in run_cmd('cat /proc/version').lower():
            return 'ubuntu'

    return 'unknown'


def clean_app_files(managers: List[SoftwareManager], logs: bool = True):

    if logs:
        print('[atlas] Cleaning configuration and cache files')

    for path in (CACHE_DIR, CONFIG_DIR, TEMP_DIR):
        if logs:
            print('[atlas] Deleting directory {}'.format(path))

        if os.path.exists(path):
            try:
                shutil.rmtree(path)
                if logs:
                    print('{}[atlas] Directory {} deleted{}'.format(Fore.YELLOW, path, Fore.RESET))
            except Exception:
                if logs:
                    print('{}[atlas] An exception has happened when deleting {}{}'.format(Fore.RED, path, Fore.RESET))
                    traceback.print_exc()

    if managers:
        for m in managers:
            m.clear_data()

    if logs:
        print('[atlas] Cleaning finished')
