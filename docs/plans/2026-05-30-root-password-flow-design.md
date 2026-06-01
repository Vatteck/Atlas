# Root-password flow for the webview — design

**Date:** 2026-05-30
**Status:** implemented and verified in the GUI (2026-06-01) — gimp install prompts for
the password, renders the optdep + missing-deps lists, installs optdeps, reports success.
**Problem:** Arch/AUR (and any privileged) installs fail with "no root access".

## Root cause

`atlas/view/webview/api.py` calls every privileged operation with a hardcoded
`root_password=None`:

```python
self.manager.install(pkg, root_password=None, ...)
self.manager.uninstall(pkg, root_password=None, ...)
self.manager.get_upgrade_requirements([pkg], root_password=None, ...)
self.manager.upgrade(reqs, root_password=None, ...)
```

`SimpleProcess`/`new_root_subprocess` (`atlas/commons/system.py`) only prepend
`sudo -S` when `root_password` is a `str`. With `None`, the pacman/AUR commands run
unprivileged → fail. The webview never collects a password.

The only existing prompt path — `WebviewWatcher.request_root_password()` — uses
`window.prompt(...)` via `evaluate_js`. WebKitGTK (the confirmed backend) does not
support `window.prompt`/`window.confirm`/`window.alert` and returns `null`, so it
yields `(False, '')`. It is also **not** on the main Arch install path; the Arch/Debian
controllers expect the caller to pass `root_password` up front (they only call
`requires_root(action, pkg)` to advertise the need).

## Fix (Python UI + backend, no Rust)

A session-scoped **root-password broker** on `AtlasApi` plus a proper HTML modal.

### 1. Password validation — `atlas/commons/system.py`

Add `validate_root_password(password: str) -> bool`: runs `sudo -k -S -v` feeding
`password\n` on stdin, returns `True` on exit 0. `-k` forces a fresh check (ignores any
cached sudo timestamp) so a wrong password fails fast instead of mid-transaction.

### 2. Broker on `AtlasApi`

- `self._root_password: Optional[str]` — session cache (validated once, reused).
- `self._pwd_event = threading.Event()`, `self._pwd_submitted` holder, `self._pwd_lock`.
- `submit_root_password(self, password)` — **js_api callback** the modal calls; stores
  the value (or `None` for cancel) and sets the event.
- `_prompt_root_password_once(self, message) -> Optional[str]` — clears the event,
  `evaluate_js("showPasswordModal(<msg>)")`, blocks on the event (long timeout),
  returns the submitted password or `None` if cancelled.
- `acquire_root_password(self, action, pkg) -> Tuple[bool, Optional[str]]`:
  - If `not manager.requires_root(action, pkg)` → `(True, None)` (no root needed).
  - If a cached password exists and still validates → `(True, cached)`.
  - Else prompt (up to 3 tries), validate each; on success cache + return `(True, pwd)`;
    on cancel return `(False, None)` so the caller aborts cleanly.

  Returns `proceed` so callers can distinguish "user cancelled" from "no root needed".

### 3. Wire into install / uninstall / update / update_all / batch_uninstall / import

Each replaces `root_password=None` with a brokered password. Pattern:

```python
proceed, pwd = self.acquire_root_password(SoftwareAction.INSTALL, pkg)
if not proceed:
    # user cancelled the password prompt
    return {'status': 'cancelled'}
result = self.manager.install(pkg, root_password=pwd, ...)
```

`update`/`update_all` acquire once (UPGRADE) and pass the same `pwd` to both
`get_upgrade_requirements` and `upgrade`.

### 4. Fix `WebviewWatcher.request_root_password()`

Delegate to the broker so the in-gem call sites (flatpak system install
`controller.py:481`, arch snap-setup `controller.py:3512`) also work. The watcher gets an
optional `api` reference; `request_root_password()` returns `(True, pwd)` from
`api.acquire...`/prompt, or `(False, '')` on cancel. Drop the `window.prompt` path. The
`request_confirmation`/`request_reboot`/`show_message` dialogs (also `window.*`) were
**also converted** in a follow-up commit, reusing this broker pattern
(`prompt_confirmation`/`prompt_message` + `submit_confirmation`/`submit_message_ack`).
Rich `components` are not rendered (text only).

### 5. HTML modal + JS — `index.html` / `main.js`

A `#password-modal` (hidden by default) with a `type="password"` input, Submit/Cancel.
- `window.showPasswordModal(message)` — set prompt text, clear input, unhide, focus.
- Submit → `pyApiCall('submit_root_password', value)` then hide.
- Cancel / Esc → `pyApiCall('submit_root_password', null)` then hide.
- Enter in the field submits.

## Threading note

pywebview dispatches each `js_api` call on its own worker thread. `install()` (worker A)
can block on `_pwd_event` while the modal's Submit fires `submit_root_password()` (worker
B) which sets the event. `evaluate_js` is safe to call from the worker thread. This is the
standard pywebview modal-dialog pattern.

## Verification

Cannot be driven headless. User verifies in the GUI: install an Arch repo pkg → modal
appears → correct password installs, wrong password re-prompts, cancel aborts cleanly.
