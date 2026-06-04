# AUR "maintainer changed hands" advisory — 2026-06-03

Part of the **AUR-safety theme**. Surface when an AUR package's maintainer has changed since you
installed it — a real supply-chain signal (orphaned package adopted by someone new), exactly the
kind of thing worth a second look before pulling their update. Honest framing: *advisory, not a
verdict* — a maintainer change is common and usually benign; it just deserves a glance.

## What exists
- `ArchPackage.maintainer` is cached on install (`controller._install`, ~2773-2789: AUR maintainer
  fetched via `aur_client.get_info(...)['Maintainer']` and written to the disk cache; `maintainer`
  is in `__cached_attrs`). So the **install-time maintainer is the baseline**, stored per package.
- The pre-build advisory review already exists: `_audit_pkgbuild` builds a structured `review`
  payload (`{name, summary, diff, findings}`) rendered by `renderPkgbuildReview` in a confirm modal.
- On an update, `context.maintainer` / `context.pkg.maintainer` is the cached (install-time)
  maintainer; the **current** maintainer comes from the AUR RPC.

## Design (reuse the review modal)
In `_audit_pkgbuild`, for an **AUR update** (`repository == 'aur'`, `not context.new_pkg`):
1. `old = context.maintainer` (or `context.pkg.maintainer`) — the cached baseline.
2. `new = aur_client.get_info(name)[0]['Maintainer']` — one best-effort RPC (the method already
   does a cgit fetch for the diff, so one more network call on the build path is consistent).
3. If both are known and `old != new` → add `review['maintainer_change'] = {'old': old, 'new': new}`
   and make the modal show even when there are no warns/diff (a maintainer change alone prompts).
   - `new` is `None` (package orphaned/removed) is itself worth flagging ("no current maintainer").
4. Frontend: `renderPkgbuildReview` draws a prominent banner —
   "⚠ Maintainer changed since you installed: **X → Y**. Review before updating."

## Limitations (be honest)
- Packages installed before maintainer-caching (no baseline in the cache, e.g. an old `antigravity`
  install showing "Unknown Publisher") can't be compared — we never knew the old maintainer. The
  first update re-caches the current maintainer, so a *subsequent* change is caught. No retroactive
  magic.
- The AUR RPC only reports the *current* maintainer; we rely entirely on our cached baseline for the
  "from" side.

## Scope
- Gate on the existing `aur_check_pkgbuild` toggle (it's part of the same advisory review).
- No auto-block, no "safe" badge — just the banner, consistent with the rest of the theme.

## Update (2026-06-03): also surfaced in the detail modal (discoverability)
The build-time banner only appears mid-update (when you click Update → the PKGBUILD review modal),
which is hard to stumble on. Added `AtlasApi.get_aur_maintainer(pkg_id)` → `{maintainer, changed}`
(one best-effort RPC), and `openDetailModal` now shows, for AUR packages, a **👤 maintainer badge**
in the badge row (fixes the "Unknown Publisher" gap — e.g. antigravity now shows AlphaLynx) plus a
clickable **⚠ Maintainer changed** badge → explainer popup when a baseline exists and differs (and
an "⚠ Orphaned" badge when the package lost its maintainer). Same advisory framing.

## Tests
- `_audit_pkgbuild`: maintainer differs → `review['maintainer_change']` set + modal shown (even with
  a clean PKGBUILD and no diff); same maintainer → not set; new install (`new_pkg`) → never checked;
  missing baseline → no flag. Mock `aur_client.get_info`.
