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

## Deferred to increment 2
- **`.install` tab** — fetch + scan `<base>.install` scriptlets (cgit), tab alongside PKGBUILD.
- **Anchored diff** — "changed since your last build" for installed packages (reuse `diff_lines`
  + cached commit), anchored to the same line ids.
- **Copy raw PKGBUILD** button.

## Non-goals
- No editing here (PKGBUILD edition stays its own build-time flow).
- No "safe" verdict, ever (advisory only).
