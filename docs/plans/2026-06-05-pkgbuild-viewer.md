# PKGBUILD viewer — a first-class UI (2026-06-05)

**Backlog item:** "PKGBUILD viewer as a first-class UI" (Power-user sugar) — *"syntax-highlighted
PKGBUILD, sticky risk summary, line-linked findings, anchored diff, maintainer/source/checksums,
`.install` tab. Could become Atlas's signature AUR feature (the scanner/diff backend already
exists)."*

## Why
The advisory PKGBUILD scanner (`pkgbuild_audit.scan` / `diff_lines`) already exists, but it only
surfaces **at build time** inside the confirm modal — undiscoverable, and you can't read the whole
PKGBUILD, only the flagged lines. This makes the scanner a first-class, on-demand viewer reachable
from any AUR package's **detail page**, so an Arch user can read exactly what a community package
will run *before* deciding to install — Atlas's "honest enough for Arch people" angle.

## Scope (honest)
- **AUR only.** Official-repo packages are built+signed by Arch (no PKGBUILD to vet); Flatpak/
  AppImage have no PKGBUILD. The button shows only for `type === 'aur'`.
- **Advisory, not a verdict.** Reuses `pkgbuild_audit` — same `DISCLAIMER`. A clean scan ≠ safe.
- **Fetches the current AUR PKGBUILD** (cgit HEAD of the package base), not the locally-cloned one
  (we don't keep a clone outside a build). Best-effort; network failure → friendly empty state.

## Increment 1 (this change) — viewer + scan + metadata
### Backend
- `pkgbuild.parse_metadata(text) -> {maintainer, contributors, pkgver, url, sources, checksums}`
  — pure parser (new, in the existing pure `gems/arch/pkgbuild.py`):
  - `maintainer` / `contributors`: from leading `# Maintainer:` / `# Contributor:` comments.
  - `pkgver`, `url`: from the `pkgver=` / `url=` assignments (unquoted).
  - `sources`: URLs from `source=(...)` (strip `name::` prefixes; keep only `proto://` entries).
  - `checksums`: `(algo, value)` pairs from `*sums=(...)` (sha256/sha512/b2/md5/sha1), `SKIP`
    flagged. Lets the UI show "checksums present / some SKIP'd".
- Arch controller: extract a `fetch_pkgbuild(base, commit=None)` from the existing
  `_fetch_pkgbuild_at_commit` (HEAD when `commit` is None) so the cgit URL lives in the gem.
- `AtlasApi.get_pkgbuild(pkg_id) -> {status, data}` where data =
  `{text, findings, summary, metadata, base, url, disclaimer}`. Non-AUR → `{}` + a note. Resolves
  the package **base** via `aur_client.get_info(...).PackageBase` (fallback: pkg name). **Fails
  open** (any failure → `{}`; never raises into the UI).

### Frontend
- A **"View PKGBUILD"** button in the detail modal, shown only for AUR packages (new
  `#detail-pkgbuild-section`).
- A dedicated **`#pkgbuild-modal`** overlay with:
  - **Sticky risk summary** banner (`buildPkgbuildRiskHTML(summary)`) — counts + the disclaimer.
  - **Metadata panel** (`buildPkgbuildMetaHTML(metadata)`) — maintainer/contributors, upstream
    URL, source URLs, checksum status.
  - **Line-linked findings** (`buildPkgbuildFindingsHTML(findings)`) — each row links to its line.
  - **Syntax-highlighted, line-numbered code** (`buildPkgbuildCodeHTML(text, findings)`): every
    line gets a gutter number + `id="pkgb-line-N"`; flagged lines get a severity class; a light,
    pure regex **bash highlighter** (`highlightBashLine`) colors comments/strings/keywords/
    functions/variables (no external lib — WebKitGTK, offline).
- Clicking a finding scrolls to + flashes the line (delegated handler).
- All builders are **pure** and Node-VM contract-tested (`main_js_contracts`); exported.

### Tests
- `test_pkgbuild_audit.py` / a new `test_pkgbuild_meta.py`: `parse_metadata` (maintainer,
  sources w/ `name::`, checksums incl. SKIP, missing fields).
- `test_api.py::PkgbuildViewTest`: non-AUR → empty; AUR happy path (mocked fetch + get_info);
  fail-open on fetch error.
- `main_js_contracts`: `highlightBashLine` (escapes, comment/string), `buildPkgbuildCodeHTML`
  (line ids + flagged class), `buildPkgbuildRiskHTML`, `buildPkgbuildMetaHTML`,
  `buildPkgbuildFindingsHTML` (line links).

## Increment 2 (shipped 2026-06-05) — `.install` tab + copy-raw + AUR preview entry point
- **`.install` scriptlet tab** — `get_pkgbuild` now resolves the `install=` filename(s) via the pure
  `pkgbuild.parse_install_files(text, base)` (expands `$pkgname`/`$pkgbase`/`$_*` vars; drops anything
  unresolved), fetches each via the generalised controller `fetch_aur_file(base, path, commit=None)`
  (`fetch_pkgbuild` is now a thin wrapper), scans them, and returns a **`files`** list (PKGBUILD
  first, then each `.install`). The viewer shows a **tab bar** (`buildPkgbuildTabsHTML`) when >1 file,
  each tab badged with its warn count; the **risk summary is now combined** across PKGBUILD +
  scriptlets (scriptlets run as root on install/upgrade/remove — they matter).
- **Copy** button (header) — copies the **active** file's raw text to the clipboard.
- **Entry point from the install transaction preview** — a "View PKGBUILD" button in the tx-preview
  footer, AUR-only (detected via `source_label`), so the viewer is reachable at the actual
  review-before-build moment, not just the detail page. Viewer modal `z-index` lifted above the other
  modals so it stacks on top when opened from the preview.

## Increment 3 (shipped 2026-06-05) — "changed since your build" diff
- For an **installed** AUR package whose **built commit** we cached (`commit` is a cached `ArchPackage`
  attr, restored by `fill_cached_data`), `get_pkgbuild` now fetches the PKGBUILD at that commit and
  `diff_lines`s it against the current published one (the compromised-release signal). Best-effort:
  no baseline / unchanged / fetch failure → empty `diff`. Returned as `data.diff`.
- Frontend: the viewer is now a list of **views** (pure `buildPkgbuildViews(data)`): a **"Changed
  since your build" diff tab leads** (badge = add/del count, accent-colored) when present, followed by
  the PKGBUILD + `.install` tabs. Diff rendered by pure `buildPkgbuildDiffHTML` (reuses the build-time
  review's `.diff-line` markup). Copy on the diff tab copies the diff text.
- Tests: `PkgbuildViewTest` (+3: not-installed → no diff, installed+changed → diff w/ adds, unchanged
  → none) + `testPkgbuildViewerBuilders` views/diff assertions. Suite **528** + JS 38.
- **Note:** the viewer is most used pre-install (uninstalled → no baseline → no diff tab); the diff
  appears on the detail page of an installed-but-behind AUR pkg, or its update preview. Complements
  the build-time review modal, which still shows this diff at confirm time.

## Non-goals
- No editing here (PKGBUILD edition stays its own build-time flow).
- No "safe" verdict, ever (advisory only).
