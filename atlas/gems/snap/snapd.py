import socket
import traceback
from logging import Logger
from typing import Optional, List

from atlas.commons.system import run_cmd

URL_BASE = 'http://snapd/v2'

# `requests`/`urllib3` (the ~280 ms HTTP stack) used to be imported at module scope here to
# subclass HTTPConnection/Adapter. Snap is off by default, yet this module is imported at launch
# (load_managers loads every gem controller), so it dragged the whole stack onto the launch
# critical path. The snapd adapter is now built lazily on first use, inside _build_snapd_adapter().
# See docs/plans/2026-06-20-launch-optimization.md.
_SNAPD_ADAPTER_CLS = None


def _build_snapd_adapter():
    """Define + cache the requests/urllib3 adapter that talks to snapd's UNIX socket. Imports the
    HTTP stack lazily so it stays off the launch path until a snap operation actually runs."""
    global _SNAPD_ADAPTER_CLS
    if _SNAPD_ADAPTER_CLS is None:
        from requests.adapters import HTTPAdapter
        from urllib3.connection import HTTPConnection
        from urllib3.connectionpool import HTTPConnectionPool

        class SnapdConnection(HTTPConnection):
            def __init__(self):
                super(SnapdConnection, self).__init__('localhost')

            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect("/run/snapd.socket")

        class SnapdConnectionPool(HTTPConnectionPool):
            def __init__(self):
                super(SnapdConnectionPool, self).__init__('localhost')

            def _new_conn(self):
                return SnapdConnection()

        class SnapdAdapter(HTTPAdapter):
            def get_connection(self, url, proxies=None):
                return SnapdConnectionPool()

        _SNAPD_ADAPTER_CLS = SnapdAdapter
    return _SNAPD_ADAPTER_CLS


class SnapdClient:

    def __init__(self, logger: Logger):
        self.logger = logger
        self.session = self._new_session()

    def _new_session(self):
        try:
            from requests import Session
            session = Session()
            session.mount("http://snapd/", _build_snapd_adapter()())
            return session
        except Exception:
            self.logger.error("Could not establish a connection to 'snapd.socker'")
            traceback.print_exc()

    def query(self, query: str) -> Optional[List[dict]]:
        final_query = query.strip()

        if final_query and self.session:
            res = self.session.get(url=f'{URL_BASE}/find', params={'q': final_query})

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

    def find_by_name(self, name: str) -> Optional[List[dict]]:
        if name and self.session:
            res = self.session.get(f'{URL_BASE}/find?name={name}')

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

    def list_all_snaps(self) -> List[dict]:
        if self.session:
            res = self.session.get(f'{URL_BASE}/snaps')

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']

        return []

    def list_only_apps(self) -> List[dict]:
        if self.session:
            res = self.session.get(f'{URL_BASE}/apps')

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return json_res['result']
        return []

    def list_commands(self, name: str) -> List[dict]:
        if self.session:
            res = self.session.get(f'{URL_BASE}/apps?names={name}')

            if res.status_code == 200:
                json_res = res.json()

                if json_res['status-code'] == 200:
                    return [r for r in json_res['result'] if r['snap'] == name]
        return []


def is_running() -> bool:
    status = run_cmd('systemctl is-active snapd.service snapd.socket', print_error=False)
    if not status:
        return False
    else:
        for status in status.split('\n'):
            if status.strip().lower() == 'active':
                return True

        return False
