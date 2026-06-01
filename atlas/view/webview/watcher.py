import json
import logging
import re
from typing import Optional, Tuple, List
from atlas.api.abstract.handler import ProcessWatcher
from atlas.api.abstract.view import MessageType, MultipleSelectComponent, SingleSelectComponent, \
    ViewContainer, TextComponent, SelectViewType


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

    def request_confirmation(self, title: str, body: Optional[str], components: Optional[list] = None,
                             confirmation_label: str = None, deny_label: str = None,
                             deny_button: bool = True, **kwargs) -> bool:
        self.logger.info(f"Confirmation requested: {title} - {body}")
        # Delegate to AtlasApi's HTML modal; window.confirm is dead in WebKitGTK.
        # Input components (optdep checklist, missing-deps list, provider choices) are
        # serialized for the modal to render and the user's selections are applied back
        # onto the original component objects so the gem code reads them as before.
        if self.api is not None:
            try:
                confirmed, selections = self.api.prompt_confirmation(
                    title=self._clean(title),
                    body=self._clean(body),
                    confirmation_label=confirmation_label,
                    deny_label=deny_label,
                    deny_button=deny_button,
                    components=self._serialize_components(components))
                if confirmed and components:
                    self._apply_selections(components, selections)
                return confirmed
            except Exception as e:
                self.logger.error(f"Error requesting confirmation: {e}")
        return True

    def request_reboot(self, msg: str) -> bool:
        self.logger.info(f"Reboot requested: {msg}")
        if self.api is not None:
            try:
                confirmed, _ = self.api.prompt_confirmation(title='Reboot required',
                                                            body=self._clean(msg),
                                                            confirmation_label='Reboot now',
                                                            deny_label='Later')
                return confirmed
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

    # ------------------------------------------------------------------ #
    # Component (de)serialization for the confirmation modal
    # ------------------------------------------------------------------ #
    # The modal can render checkbox lists (MultipleSelectComponent), single-select
    # combos/radios (SingleSelectComponent) and forms (ViewContainer, e.g. provider
    # choices). Each component is serialized in order; the modal returns a parallel list
    # of selections (option indices) that _apply_selections writes back so callers like
    # arch confirmation.request_optional_deps / request_providers read the chosen values.

    @classmethod
    def _serialize_components(cls, components: Optional[list]) -> List[dict]:
        return [cls._serialize_component(c) for c in components] if components else []

    @classmethod
    def _serialize_component(cls, comp) -> dict:
        if isinstance(comp, MultipleSelectComponent):
            values = comp.values or set()
            return {'kind': 'multiselect',
                    'label': cls._clean(comp.label) if comp.label else '',
                    'options': [cls._serialize_option(o, i, o in values) for i, o in enumerate(comp.options)]}

        if isinstance(comp, SingleSelectComponent):
            return {'kind': 'singleselect',
                    'label': cls._clean(comp.label) if comp.label else '',
                    'selectType': 'combo' if comp.type == SelectViewType.COMBO else 'radio',
                    'options': [cls._serialize_option(o, i, comp.value is o) for i, o in enumerate(comp.options)]}

        if isinstance(comp, ViewContainer):  # FormComponent / PanelComponent
            return {'kind': 'form',
                    'label': cls._clean(getattr(comp, 'label', '') or ''),
                    'components': cls._serialize_components(comp.components)}

        if isinstance(comp, TextComponent):
            return {'kind': 'text', 'html': comp.value or ''}

        # Unknown component: emit a placeholder so the selection arrays stay aligned.
        return {'kind': 'text', 'html': cls._clean(getattr(comp, 'label', '') or '')}

    @classmethod
    def _serialize_option(cls, opt, idx: int, selected: bool) -> dict:
        return {'oi': idx,
                'label': cls._clean(opt.label) if opt.label else '',
                'tooltip': cls._clean(opt.tooltip) if opt.tooltip else None,
                'selected': bool(selected),
                'readOnly': bool(getattr(opt, 'read_only', False))}

    @classmethod
    def _apply_selections(cls, components: Optional[list], selections):
        if not components or not selections:
            return
        for comp, sel in zip(components, selections):
            cls._apply_selection(comp, sel)

    @classmethod
    def _apply_selection(cls, comp, sel):
        if sel is None:
            return
        if isinstance(comp, MultipleSelectComponent):
            comp.values = {comp.options[i] for i in sel if isinstance(i, int) and 0 <= i < len(comp.options)}
        elif isinstance(comp, SingleSelectComponent):
            if isinstance(sel, int) and 0 <= sel < len(comp.options):
                comp.value = comp.options[sel]
        elif isinstance(comp, ViewContainer):
            cls._apply_selections(comp.components, sel)
