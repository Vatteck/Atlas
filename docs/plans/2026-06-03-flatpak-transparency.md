# Flatpak transparency & control — 2026-06-03

Enrich the Flatpak experience with the kind of info/control Flathub & GNOME Software show:
license (FOSS/proprietary), developer-verified badge, downloads, **permissions** (Flatseal-style),
and a derived **safety tier**. Flatpak-only. Builds on the v2 Flathub API already in `flathub.py`.

## Honest framing

The safety tier is **advisory, not a verdict** — same rule as the PKGBUILD scanner. Never present
"safe"; it's a heuristic derived from the declared permission set + license. Metadata completeness
varies per app → everything degrades gracefully (omit the badge).

## Data sources (reality-checked 2026-06-03)

All from the v2 AppStream payload `flathub.get_appstream(app_id)` **already fetched** in `get_info`,
except stats:
- **License:** `project_license` (SPDX) + **`is_free_license`** (bool — Flathub already classifies
  FOSS vs proprietary, no SPDX parsing needed).
- **Verified:** `metadata['flathub::verification::verified']` (bool) + `…::method` + `…::website`
  (in the same payload — no extra call). (Also a dedicated `/api/v2/verification/<id>/status`.)
- **Age rating (OARS):** `content_rating` — present but often empty; needs OARS→min-age computation.
  Lowest value, **deferred**.
- **Downloads/month:** one call to `/api/v2/stats/<id>` → `installs_last_month`.
- **Permissions:** `flatpak info --show-permissions <id>` for installed apps (the Flatseal case);
  static manifest `[Context]` for not-installed (later). User overrides via `flatpak override --user`.

## Increments (cheapest/highest-value first)

1. ~~**Metadata badges in the detail modal**~~ ✅ **Done (2026-06-03).** License (Open Source /
   Proprietary), verified (✓ via <site> / ⚠ Unverified), downloads/month. `flathub.metadata_badges`
   (from the already-fetched appstream) + `flathub.installs_last_month` (stats endpoint) →
   `FlatpakManager.get_flathub_metadata` → `AtlasApi.get_flatpak_meta` (empty for non-Flatpak);
   `#detail-badges` row in `openDetailModal`. Live-verified (GIMP: FOSS/verified/67k; Spotify:
   proprietary/unverified/135k). Tests: `test_flathub.py` (+5), `test_api.py::FlatpakMetaTest` (2).
2 + 3. **Permissions list + safety tier (combined — same data source).** Reality-check (2026-06-03):
   the Flathub **`/api/v2/summary/<id>`** endpoint exposes the full structured permission set
   (`metadata.permissions`: `sockets`, `filesystems`, `shared`, `devices`, `session-bus`/`system-bus`
   own/talk, `features`) for **any** app — installed or not — so we get the same data Flathub's UI
   uses (no `flatpak info`, works for non-installed). New pure module `flatpak/permissions.py`:
   `describe(perms, is_free)` → `[{title, detail, level: safe|warn|danger}]` (GNOME-Software-style
   human descriptions); `safety(perms, is_free)` → `{level: safe|moderate|unsafe, label}` (danger →
   "Potentially unsafe"). **Advisory only** (describes *declared* permissions, not behavior — never
   "safe to trust"). Heavily unit-tested. Wired into `get_flathub_metadata` (one extra summary fetch)
   → detail modal: a safety badge in the badges row + a permissions list section.
4. ~~**Permission editing (Flatseal-style)**~~ ✅ **Done (2026-06-03).** "⚙ Manage permissions" on
   installed Flatpaks opens a toggle editor (curated high-impact set: network, X11, Wayland, audio,
   all-devices, home, host). Reads current state from `flatpak info --show-permissions`
   (`permissions.parse_context` + `editable_toggles`); each toggle applies immediately via
   `flatpak override --user <flag> <id>` (**no root**) — `permissions.override_flag` maps key→flag.
   Reset = `flatpak override --user --reset`. `flatpak.{show_permissions,set_override,reset_overrides}`
   + `FlatpakManager.{get_permission_toggles,set_permission,reset_permissions}` +
   `AtlasApi.{get_flatpak_overrides,set_flatpak_override,reset_flatpak_overrides}`. Toggles revert on
   failure; effective next launch. Tests: `test_permissions.py` (+4). **Needs a GUI eyeball** (toggling
   actually changes the override file).

## Notes / out of scope

- Flatpak-only; AUR/repo/AppImage unaffected.
- Age rating deferred (OARS computation, low availability).
- Not-installed permission display (static manifest) is a later nicety; #2 targets installed apps.
