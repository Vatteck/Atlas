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
2. **Permissions display** (installed Flatpaks): parse `flatpak info --show-permissions` into a
   readable list (filesystem, sockets, devices, dbus, …) in the detail modal.
3. **Safety tier** ("Safe / Probably safe / Potentially unsafe"): heuristic over the permission set
   (broad filesystem like `host`/`home`, `devices=all`, no sandbox, session-bus talk) + proprietary
   license. Advisory badge. Pure, unit-testable.
4. **Permission editing (Flatseal-style):** toggle grid → `flatpak override --user <id> --…`
   (overrides in `~/.local/share/flatpak/overrides/`), with a reset. Privileged? `--user` needs no
   root; `--system` would. The bulk of the UI work.

## Notes / out of scope

- Flatpak-only; AUR/repo/AppImage unaffected.
- Age rating deferred (OARS computation, low availability).
- Not-installed permission display (static manifest) is a later nicety; #2 targets installed apps.
