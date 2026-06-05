# Better app detail pages — why-this-source + dependency summary

**Status:** increment 1 shipped (2026-06-05) — needs a GUI eyeball. Dependency-tree + "why is this
installed?" remain separate BACKLOG items.
**Backlog item:** "Better app detail pages" (BACKLOG → Store-quality discovery) — *source-comparison
panel (✅ shipped), "why this source?" hints, a dependency summary (direct / optional / required-by
counts), and a "what will change?" preview (✅ shipped as the transaction preview).*

Atlas is multi-source and its angle is "honest enough for Arch people." The detail page already has
the source-comparison panel and the rich badges, but it doesn't **explain the trust tradeoff of the
source** or give a **scannable dependency picture** — both are exactly what an Arch user wants before
installing.

## What already exists (reuse, don't rebuild)

- **Source-comparison panel** + `sourceCompareNote(type)` (one-liner per source) — already on
  multi-source detail pages.
- **`get_info`** returns a flat key/value table that *includes* a raw "Depends" list — but as an
  unstructured string row, not counts/chips, and no required-by.
- **Dep signals** (all used by the transaction-preview assemblers, fail-open):
  - repo direct deps → `pacman.map_updates_data([name])['d']`;
  - optional deps → `pacman.map_optional_deps([name], remote=…)`;
  - reverse deps → `pacman.map_required_by([name])` (installed set);
  - AUR deps/makedepends → `aur_client.get_info`.
- Flatpak metadata (`get_flathub_metadata`): `verified`, `is_free_license`, downloads.

## Increment 1

### A. "Why this source?" hint (frontend, pure)
A one-line, honest trust note under the type badge / above the description, keyed off what we already
know about the package:
- **arch_repo** → "From the official Arch repositories — built and signed by Arch maintainers."
- **aur** → "From the AUR — community-submitted; Atlas scans the PKGBUILD before building. Review it."
- **flatpak**, verified → "Verified on Flathub — published by the app's developer." ; unverified →
  "Community-packaged on Flathub (not vendor-verified)." ; plus FOSS/proprietary from `is_free_license`.
- **appimage** → "A self-contained AppImage — not sandboxed; trust the source."
Pure `whySourceHint(type, {verified, free_license})` → `{text, level}` (Node-VM-tested). This is the
single-source counterpart to the multi-source compare panel's `sourceCompareNote`.

### B. Dependency summary (backend + frontend)
A compact **Dependencies** section in the detail modal: three counts — **Requires** (direct),
**Optional**, **Required by** (reverse) — each expandable to a chip list. One cheap backend call
`AtlasApi.get_dependency_summary(pkg_id)` → `{direct:[str], optional:[{name,detail}], required_by:[str],
note}`, reusing the signals above and **failing open per field**:
- repo: direct = `map_updates_data` `d`; optional = `map_optional_deps(remote=True)`; required_by =
  `map_required_by` (only meaningful when installed).
- aur: direct = `get_info` `Depends`; optional = `OptDepends`; required_by via `map_required_by` if
  installed. Note that the full set resolves at build time.
- flatpak: no pacman-style deps (runtime-based) → empty + a one-line note; we don't fake it.
Lazy (fetched after the modal opens, like `get_info`), stale-guarded by the existing
`stillCurrentDetail()` check, cached is unnecessary (cheap). Pure `buildDependencySummaryHTML(data)`
(counts + accordions) Node-VM-tested.

## Increment 2 — "Why is this installed?" (shipped 2026-06-05)

Folded into the same dependency summary (it's the natural home — required-by was already there). For
an **installed** package, `get_dependency_summary` now also returns `install_reason`
(`'explicit'` / `'dependency'` / `None`) and a derived `orphan` flag. New pure
`pacman.get_install_reason(name)` parses the local `pacman -Qi` "Install Reason" line (reuses the
existing `get_info`); `orphan = install_reason == 'dependency' and not required_by`. The detail
section now leads with a one-line reason banner: "You installed this explicitly." / "Installed as a
dependency of other packages." / (amber) "Installed as a dependency, but nothing requires it now — an
orphan you can likely remove." Tests: `test_pacman_info.py::GetInstallReasonTest` (3) +
`DependencySummaryTest` orphan/explicit cases + JS reason-line assertions. This answers the BACKLOG
"Why is this installed?" item (explicit vs dep, orphan status, required-by).

## Deferred

- A real **dependency tree** (direct/optional/build + provides/conflicts/replaces as an accordion
  tree) — its own BACKLOG "Power-user sugar" item.

## Verification

- `python -m pytest` + JS harness green (new `get_dependency_summary` test + `whySourceHint` /
  `buildDependencySummaryHTML` contract tests).
- **Needs a GUI eyeball**: hint line per source; dependency counts + expand on a repo pkg, an AUR
  pkg, and a Flatpak (empty + note).
