# Plan — AUR discovery buckets

**Date:** 2026-06-05
**Status:** in progress
**Backlog item:** "AUR discovery buckets (not categories)" (BACKLOG → Browse / discovery).

## Goal

AUR has no category taxonomy, so instead of faking categories, offer **discovery buckets** in Browse:
**Popular**, **Recently updated**, **VCS** (`-git`/`-svn`/…), **Binary** (`-bin`). Clicking a bucket
lists its packages as normal cards (install / detail / source-switch all work).

## Data-source decision (resolved with the user, 2026-06-05)

The buckets need votes/popularity/dates that the **names index** Atlas fetches today
(`packages.gz`) does not carry, and the AUR RPC has **no "browse all / sort by votes" endpoint**.

**Chosen: precompute in the `atlas-files` repo** (same pattern as suggestions/categories). A scheduled
GitHub Action turns the heavy `packages-meta-ext-v1.json.gz` dump into a small
`arch/aur_discovery.json` (top N per bucket); Atlas just fetches that one tiny JSON. Atlas stays
light, ranking is always correct, and there's no client-side parse of ~90k packages.

Rejected: (b) download the full dump in Atlas (heavy per-user download + parse), (c) live-RPC only
(can't do Popular / Recently-updated — the two most useful buckets).

## atlas-files side

- `arch/generate_aur_discovery.py` — stdlib-only: download the meta-ext dump, compute buckets, write
  `arch/aur_discovery.json`. Top **60** per bucket. Each entry keeps the **RPC-shaped capitalized
  keys** (`Name`, `Version`, `Description`, `NumVotes`, `Popularity`, `Maintainer`, `OutOfDate`,
  `LastModified`, `URL`, `PackageBase`) so Atlas can map them with the existing `AURDataMapper`.
  - **popular**: sort by `Popularity` desc.
  - **recently_updated**: `NumVotes >= 5` (drop churn/noise), sort by `LastModified` desc.
  - **vcs**: name ends with `-git/-svn/-hg/-bzr/-cvs/-darcs`, sort by `Popularity` desc.
  - **bin**: name ends with `-bin`, sort by `Popularity` desc.
- `.github/workflows/aur-discovery.yml` — daily cron + manual dispatch; runs the generator and
  commits `aur_discovery.json` when it changes.
- Commit an initial generated `aur_discovery.json` so the feature works immediately.

## Atlas side

- **arch gem** (`controller.py`): `list_aur_packages(entries)` → maps RPC-shaped dicts to
  `ArchPackage` via `self.aur_mapper.map_api_data(e, None, self.categories)` (reuse, no new path).
- **`api.py`**:
  - `AUR_DISCOVERY_URL` (atlas-files raw) + `AUR_BUCKETS` (key/label/icon).
  - `_fetch_aur_discovery()` — best-effort fetch via the AUR client's `http_client.get_json`, cached
    in-memory with a 1 h TTL (the data refreshes daily server-side). Fails open → None.
  - `get_aur_discovery()` → `[{key,label,icon,count}]` for non-empty buckets (gated on the arch/AUR
    gem being present).
  - `get_aur_bucket_packages(key)` → serialized cards (registered in `pkg_registry` like any card, so
    install/detail/preview all work).
- **Installed-state on cards (follow-up, 2026-06-05):** `list_aur_packages` does one cheap `pacman -Q`
  (`pacman.map_installed` — *not* the slow `read_installed`) and feeds it through `map_api_data`'s
  `pkgs_installed` arg, so cards read **Install / Uninstall / Update** correctly (Update computed with
  `check_version_update` on installed vs AUR version). Fail-open. Test: `tests/gems/arch/test_aur_discovery.py`.
- **frontend** (`main.js`): `renderBrowse` also fetches `get_aur_discovery` and renders an **AUR
  discovery** row of bucket cards under the category grid. `renderCategoryPackages(key,label,opts)`
  gains an optional `opts.api` so a bucket reuses the same list/back/topbar machinery with
  `get_aur_bucket_packages`. AUR-distinct styling (community accent).

## Tests

- atlas-files: a tiny `test` of the bucket logic if it's split out (or keep the generator simple +
  manually verified against the live dump once).
- Atlas: `test_api.py` — `get_aur_discovery` (buckets from a mocked fetch, empty when no data) +
  `get_aur_bucket_packages` (maps entries → cards). `test_*` for `list_aur_packages` mapping.

## Out of scope

- Per-bucket counts of the *whole* AUR (we show top-N, not totals).
- Live installed-state on bucket cards (kept cheap; detail/preview re-checks).
- More buckets (e.g. "new this week", "orphaned") — easy to add later in the generator.
