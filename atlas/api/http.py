from __future__ import annotations

import logging
import time
import traceback
from typing import Optional

import yaml

from atlas.commons import system
from atlas.commons.view_utils import get_human_size_str

# `requests` (and its urllib3/charset-normalizer/chardet tree) is ~280 ms of import time and is
# only needed once a network call actually happens — well after the window is shown. It is imported
# lazily inside the methods below (and the session is built on first use) to keep it off the launch
# critical path. See docs/plans/2026-06-20-launch-optimization.md.


class HttpClient:

    def __init__(self, logger: logging.Logger, max_attempts: int = 2, timeout: int = 30, sleep: float = 0.5):
        self.max_attempts = max_attempts
        self._session = None
        self.timeout = timeout
        self.sleep = sleep
        self.logger = logger

    @property
    def session(self):
        if self._session is None:
            import requests
            import urllib3
            # Suppress the InsecureRequestWarning for the intentional ignore_ssl=True calls. This
            # used to run eagerly at app start; it now happens on first session use, which is the
            # first moment urllib3 is actually imported.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            self._session = requests.Session()
        return self._session

    def get(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, ignore_ssl: bool = False, single_call: bool = False,
            session: bool = True, stream: bool = False) -> Optional[requests.Response]:
        import requests
        cur_attempts = 1

        while cur_attempts <= self.max_attempts:
            cur_attempts += 1

            try:
                args = {'timeout': self.timeout, 'allow_redirects': allow_redirects, 'stream': stream}

                if params:
                    args['params'] = params

                if headers:
                    args['headers'] = headers

                if ignore_ssl:
                    args['verify'] = False

                if session:
                    res = self.session.get(url, **args)
                else:
                    res = requests.get(url, **args)

                if 200 <= res.status_code < 300:
                    return res

                if single_call:
                    return res

                if self.sleep > 0:
                    time.sleep(self.sleep)
            except Exception as e:
                if isinstance(e, requests.exceptions.ConnectionError):
                    # A connectivity blip on a best-effort fetch — the caller decides whether it
                    # matters, so this is a warning, not an error (it floods the log otherwise,
                    # e.g. the post-upgrade metadata refresh hitting a momentary network drop).
                    self.logger.warning('Internet seems to be off')
                    raise e
                elif isinstance(e, requests.exceptions.TooManyRedirects):
                    self.logger.warning(f"Too many redirects for GET -> {url}")
                    raise e
                elif e.__class__ in (requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
                    self.logger.warning(f"The URL '{url}' has an invalid schema")
                    raise e

                self.logger.error(f"Could not retrieve data from '{url}'")
                traceback.print_exc()
                continue

            self.logger.warning(f"Could not retrieve data from '{url}'")

    def get_json(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, session: bool = True):
        res = self.get(url, params=params, headers=headers, allow_redirects=allow_redirects, session=session)
        return res.json() if res else None

    def get_yaml(self, url: str, params: dict = None, headers: dict = None, allow_redirects: bool = True, session: bool = True):
        res = self.get(url, params=params, headers=headers, allow_redirects=allow_redirects, session=session)
        return yaml.safe_load(res.text) if res else None

    def get_content_length_in_bytes(self, url: str, session: bool = True) -> Optional[int]:
        if not url:
            return

        import requests
        params = {'url': url, 'allow_redirects': True, 'stream': True}

        try:
            if session:
                res = self.session.get(**params)
            else:
                res = requests.get(**params)
        except requests.exceptions.ConnectionError:
            self.logger.info(f"Internet seems to be off. Could not reach '{url}'")
            return

        if res.status_code == 200:
            size = res.headers.get('Content-Length')

            if size:
                try:
                    return int(size)
                except Exception:
                    pass

    def get_content_length(self, url: str, session: bool = True) -> Optional[str]:
        size = self.get_content_length_in_bytes(url, session)

        if size:
            return get_human_size_str(size)

    def exists(self, url: str, session: bool = True, timeout: int = 5) -> bool:
        import requests
        params = {'url': url, 'allow_redirects': True, 'verify': False, 'timeout': timeout}

        try:
            if session:
                res = self.session.head(**params)
            else:
                res = self.session.get(**params)
        except requests.exceptions.TooManyRedirects:
            self.logger.warning(f"{url} seems to exist, but too many redirects have happened")
            return True

        return res.status_code in (200, 403)
