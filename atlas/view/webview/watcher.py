import json
import logging
import re
from typing import Optional, Tuple
from atlas.api.abstract.handler import ProcessWatcher
from atlas.api.abstract.view import MessageType


class WebviewWatcher(ProcessWatcher):

    def __init__(self, logger: logging.Logger, window=None, api=None):
        self.logger = logger
        self.window = window
        self.api = api  # AtlasApi, for the shared root-password broker
        self._stop = False

    def _push(self, js: str):
        if self.window:
            try:
                self.window.evaluate_js(js)
            except Exception:
                pass  # window may be closing

    def print(self, msg: str):
        if msg:
            self.logger.debug(f'[watcher] {msg}')
            escaped = json.dumps(msg)
            self._push(f'terminalAppend({escaped})')

    def change_status(self, msg: str):
        if msg:
            escaped = json.dumps(msg)
            self._push(f'terminalSetStatus({escaped})')

    def change_substatus(self, msg: str):
        if msg:
            escaped = json.dumps(msg)
            self._push(f'terminalSetSubstatus({escaped})')

    def change_progress(self, val: int):
        self._push(f'terminalSetProgress({int(val)})')

    def should_stop(self) -> bool:
        return self._stop

    def request_root_password(self) -> Tuple[bool, str]:
        self.logger.info("Root password requested by process watcher")
        # Delegate to AtlasApi's broker: it shows the HTML password modal, validates,
        # and caches the password for the session. window.prompt is unsupported in
        # WebKitGTK, so the old evaluate_js("window.prompt(...)") path never worked.
        if self.api is not None:
            try:
                pwd = self.api.ensure_root_password()
                if pwd:
                    return True, pwd
            except Exception as e:
                self.logger.error(f"Error requesting root password: {e}")
        return False, ''

    def request_confirmation(self, title: str, body: Optional[str],
                             confirmation_label: str = None, deny_label: str = None,
                             deny_button: bool = True, **kwargs) -> bool:
        self.logger.info(f"Confirmation requested: {title} - {body}")
        # Delegate to AtlasApi's HTML modal; window.confirm is dead in WebKitGTK.
        if self.api is not None:
            try:
                return self.api.prompt_confirmation(title=self._clean(title),
                                                    body=self._clean(body),
                                                    confirmation_label=confirmation_label,
                                                    deny_label=deny_label,
                                                    deny_button=deny_button)
            except Exception as e:
                self.logger.error(f"Error requesting confirmation: {e}")
        return True

    def request_reboot(self, msg: str) -> bool:
        self.logger.info(f"Reboot requested: {msg}")
        if self.api is not None:
            try:
                return self.api.prompt_confirmation(title='Reboot required',
                                                    body=self._clean(msg),
                                                    confirmation_label='Reboot now',
                                                    deny_label='Later')
            except Exception as e:
                self.logger.error(f"Error requesting reboot: {e}")
        return False

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        self.logger.info(f"Message: {title} - {body}")
        if self.api is not None:
            try:
                type_name = type_.name.lower() if isinstance(type_, MessageType) else 'info'
                self.api.prompt_message(title=self._clean(title), body=self._clean(body),
                                        type_=type_name)
            except Exception as e:
                self.logger.error(f"Error showing message: {e}")

    @staticmethod
    def _clean(text: Optional[str]) -> str:
        """Strip basic HTML tags so gem messages (which use <b>, <br/>) read cleanly."""
        if not text:
            return ''
        return re.sub('<[^<]+?>', '', text)
