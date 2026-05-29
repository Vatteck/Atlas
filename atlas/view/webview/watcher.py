import json
import logging
from typing import Optional, Tuple
from atlas.api.abstract.handler import ProcessWatcher
from atlas.api.abstract.view import MessageType


class WebviewWatcher(ProcessWatcher):

    def __init__(self, logger: logging.Logger, window=None):
        self.logger = logger
        self.window = window
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
        if self.window:
            try:
                password = self.window.evaluate_js("window.prompt('Root privileges required. Enter your password:')")
                if password is not None:
                    return True, password
            except Exception as e:
                self.logger.error(f"Error evaluating root password prompt: {e}")
        return False, ''

    def request_confirmation(self, title: str, body: Optional[str], **kwargs) -> bool:
        self.logger.info(f"Confirmation requested: {title} - {body}")
        if self.window:
            try:
                msg = f"{title}\n\n{body}" if body else title
                # Strip HTML tags if any (basic clean)
                import re
                clean_msg = re.sub('<[^<]+?>', '', msg)
                confirmed = self.window.evaluate_js(f"window.confirm({json.dumps(clean_msg)})")
                return bool(confirmed)
            except Exception as e:
                self.logger.error(f"Error evaluating confirmation dialog: {e}")
        return True

    def request_reboot(self, msg: str) -> bool:
        self.logger.info(f"Reboot requested: {msg}")
        if self.window:
            try:
                confirmed = self.window.evaluate_js(f"window.confirm('Reboot requested: {json.dumps(msg)}\\n\\nReboot now?')")
                return bool(confirmed)
            except Exception as e:
                self.logger.error(f"Error evaluating reboot dialog: {e}")
        return False

    def show_message(self, title: str, body: str, type_: MessageType = MessageType.INFO):
        self.logger.info(f"Message: {title} - {body}")
        if self.window:
            try:
                msg = f"{title}\\n\\n{body}"
                import re
                clean_msg = re.sub('<[^<]+?>', '', msg)
                self.window.evaluate_js(f"window.alert({json.dumps(clean_msg)})")
            except Exception as e:
                self.logger.error(f"Error showing message alert: {e}")
