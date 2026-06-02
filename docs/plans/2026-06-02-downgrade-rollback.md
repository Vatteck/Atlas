# Downgrade / rollback

**Date:** 2026-06-02
**Status:** done (2026-06-02)
**Scope:** let the user roll an installed package back to a previous version from the detail
modal. Classic Arch safety move; rounds out the maintenance/safety theme.

## Why
The gems already implement `downgrade` (the orchestrator exposes
`GenericSoftwareManager.downgrade(pkg, root_password, handler)`), and `_serialize_pkg`
already reports `can_be_downgraded` — but nothing in the webview called it. Recovering from
a bad update is a real Arch pain point with no GUI affordance until now.

## Backend (`atlas/view/webview/api.py`)
- `downgrade(pkg_id) -> {status, success}` — mirrors `update()`/`uninstall()`: resolve the
  root password via the broker (`SoftwareAction.DOWNGRADE`; `cancelled` if the user backs
  out), open the terminal panel, call `manager.downgrade(pkg, root_password, handler=
  WebviewWatcher(...))`, mark the terminal done, `record_activity('downgrade', …)` and
  `_notify`. The **gem** decides the target version (and may prompt through the watcher —
  the confirm modal already renders component choices), so the API stays a thin driver.

## Frontend (`index.html` / `main.js` / `style.css`)
- Detail-modal footer shows a **Downgrade** button when `pkg.installed &&
  pkg.can_be_downgraded` (between Close and the primary action). `window.downgradeApp(id)`
  mirrors `updateApp` (toast → `downgrade` → wipe cache / release lock).
- `.activity-action.downgrade` styled like `update_all` so the Activity feed badges it.

## Tests (`tests/view/webview/test_api.py::DowngradeTest`)
- success: `manager.downgrade` called with the pkg + watcher, returns `{ok, success}`,
  records the activity;
- cancelled when the root prompt is declined (and `downgrade` is never called);
- error on unknown id.

## Notes
- Needs a **GUI eyeball**: the actual rollback runs a privileged pacman transaction and the
  gem may show a version-choice prompt — can't be driven headless. Verify on a package with
  `can_be_downgraded` true (an installed repo package with an older version in the cache).
