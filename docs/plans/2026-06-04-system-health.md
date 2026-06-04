# 2026-06-04 — System Health page (the "Arch cockpit")

From BACKLOG → Open work. A dedicated **Health** sidebar page: package-management health checks,
each card = **status + short explanation + one safe action + (optional) details**. The companion
to the dashboard Attention Center — the dashboard *summarizes* what needs attention; Health is
where you *act* on each check. Strictly package/system-maintenance scope (not a YaST).

## Checks (v1)

| Check | Source | Tone logic | Action |
|-------|--------|-----------|--------|
| Database sync | `_last_db_sync_time()` | ok < 24h, warn 1–7d, danger > 7d | Open Updates (a full `-Syu`, never bare `-Sy`) |
| Mirror list | `_mirror_regen_cmd()` | ok if a tool is present, info otherwise | Regenerate mirror list |
| Pacman lock | `/var/lib/pacman/db.lck` | danger if present, ok otherwise | (info only — guidance; no destructive auto-remove in v1) |
| `.pacnew` files | `get_pacnew_files()` | warn if any, ok otherwise | Open pacdiff |
| Orphan packages | `list_orphans()` (via cleanup summary) | warn if any, ok otherwise | Review & remove (orphan checklist) |
| Pacman cache | `get_cleanup_summary()` | info (size shown) | Clean cache |
| Unused Flatpak runtimes | `get_cleanup_summary()` | info if available | Remove unused |
| AUR clean-chroot | arch config + `chroot.available()` | ok if enabled, info otherwise | Open Settings |

All checks are **best-effort / fail-open** (a failed probe → an "couldn't check" card, never a
broken page), mirroring `get_dashboard_summary`.

## Backend

New `AtlasApi.get_system_health()` — runs the cheap signals concurrently on the shared executor
and returns one fail-open payload:

```
{status:'ok', data:{
  db_sync:  {age_hours|None},
  mirrors:  {tool|None},
  lock:     {locked|None},
  pacnew:   {count|None},
  orphans:  {count|None},
  cache:    {human|None},
  flatpak:  {unused_available: bool},
  chroot:   {enabled, available},
}}
```

Reuses `get_pacnew_files` / `get_cleanup_summary` / `_last_db_sync_time` / `_mirror_regen_cmd` /
the arch chroot config. Overlaps the dashboard summary by design (both cheap).

## Frontend

- New **Health** sidebar nav item (after Disk) + `activateView('health')` branch → `renderSystemHealth()`.
- `systemHealthChecks(data)` — **pure** mapping of the payload to an ordered list of
  `{id, icon, title, tone, detail, actionLabel, actionId}` (status/tone logic lives here, so it's
  unit-tested). `renderSystemHealth()` paints cards from it (skeleton → fill) and wires action
  buttons by `actionId`:
  - `updates` → `activateView('updates')`, `mirrors` → `regenerateMirrors(btn)`,
    `pacdiff` → `pyApiCall('launch_pacdiff')`, `orphans`/`cache`/`flatpak` →
    `handleMaintenanceAction(id, renderSystemHealth)` (reused; **parameterized with a refresh
    callback** so it re-renders Health, not the Disk view), `settings` → `activateView('settings')`.
- Reuses the attention-card tone classes (ok/warn/info) + a new `danger` tone; cards in a
  responsive grid like the dashboard. Add a command-palette entry "System health".

## Tests

- `test_api.py::SystemHealthTest` — aggregation shape + fail-open (a sub-check raising → that field
  None, status still ok); lock/mirror/chroot wiring.
- `main_js_contracts.test.js` — `systemHealthChecks`: tones (db-sync age thresholds, orphans>0 →
  warn, lock → danger), action ids, and "couldn't check" when a field is None.

## Verification

`python -m pytest` + Node harness green; **needs a GUI eyeball** (cards, statuses, each action).
