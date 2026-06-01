# Flathub API v1 → v2 migration — design + plan

**Date:** 2026-06-01
**Status:** implemented
**Type:** Python backend (no Rust). Network-facing.

## Problem

Flathub retired the v1 REST API. `https://flathub.org/api/v1/apps/{id}` now returns **404**
(verified 2026-06-01). Atlas's Flatpak gem still calls it from three places, so suggestion
enrichment, the app-info panel and screenshots all fail (logs spam
`Could not retrieve app data … Server response: ?`). The app still works (it falls back to
local `flatpak`/AppStream data) but loses remote metadata.

## v1 callers (all in `atlas/gems/flatpak/`)

1. `worker.py:44` `FlatpakAsyncDataLoader.run` — enriches suggestion cards
   (name, description/summary, icon, latest version, categories).
2. `controller.py:379` `get_info` (non-installed branch) — the info panel dict.
3. `controller.py:689` `get_screenshots` — screenshot image URLs.

## Endpoint + field mapping (verified against live v2)

v1 `GET /api/v1/apps/{id}` → v2 `GET /api/v2/appstream/{id}` (sizes: `GET /api/v2/summary/{id}`).

| consumed (v1)                       | v2 appstream                          | change |
|-------------------------------------|---------------------------------------|--------|
| `name`, `summary`, `description`    | `name`, `summary`, `description`      | same (description is HTML) |
| `currentReleaseVersion` / `version` | `releases[0].version`                 | now under releases |
| `currentReleaseDescription`         | `releases[0].description`             | now under releases |
| `currentReleaseDate`                | `releases[0].timestamp` (unix string) | was a formatted date string |
| `iconMobileUrl` / `iconDesktopUrl`  | `icon` (absolute URL)                 | **absolute now** — no FLATHUB_URL prefix |
| `categories` = list of `{name}`     | `categories` = list of **strings**    | **shape changed** |
| `screenshots[].imgDesktopUrl`       | `screenshots[].sizes[].src`           | **shape changed** (pick largest 1x) |
| `developerName`, `projectLicense`   | `developer_name`, `project_license`   | snake_case |
| download/installed size             | `summary/{id}` `download_size`/`installed_size` | separate endpoint |

## Approach

Keep the Python↔network boundary coarse: one small, unit-testable module
`atlas/gems/flatpak/flathub.py` that owns the v2 endpoints and the shape mapping. The three
callers go through it and never see raw v2 JSON.

- `get_appstream(http_client, app_id) -> Optional[dict]` — `GET /appstream/{id}`.
- `latest_release(data) -> dict` — `releases[0]` or `{}`.
- `screenshot_urls(data) -> List[str]` — largest `src` per screenshot.
- `app_info(data) -> dict` — curated, display-ready dict for the info panel
  (name, summary, description (html-stripped), version, developer, license, homepage,
  categories joined, release date).

`constants.py`: `FLATHUB_API_URL` → `…/api/v2` (path moves from `/apps/` to `/appstream/`,
so the module builds the full path; no other module hardcodes `/apps/`).

Pure functions (`latest_release`, `screenshot_urls`, `app_info`) are unit-tested against a
captured v2 payload; `get_appstream` is the only I/O and is trivially mockable.

## Out of scope (note for next agent)

- Sizes via `summary/{id}` — not currently surfaced in the webview info panel; skip until
  a UI consumer needs it. (Hook point left in the plan.)
- Option icons in the confirm modal (tracked separately in STATUS.md).
