# Plan — Universal transaction preview (increment 1: Install)

**Date:** 2026-06-04
**Status:** COMPLETE — install, uninstall, downgrade, update, Update-All aggregate, **and the
source-comparison panel** on detail pages are all shipped (each needs a GUI eyeball).
**Backlog item:** "Universal transaction preview" + the data half of "source-comparison panel"
(BACKLOG → Operation confidence / Better app detail pages).

## Goal

Insert a **pre-flight preview** between the user's click and the privileged transaction:
"here's exactly what's about to happen — proceed?", rendered as cards/badges, *not* a wall of
text. First increment covers **Install** only (strangler-fig: prove the shell + plumbing, then
extend to update / uninstall / downgrade in later increments).

## Decisions already made

- **Install first** (richest payload, best showcase).
- **Share the data layer, render only the preview.** One Python assembler produces a structured
  dict that a future source-comparison panel can also consume; we render only the confirm modal
  now. We do **not** build the side-by-side comparison UI in this increment.
- Follow the house pattern: a **pure/testable Python assembler** + a **thin JS renderer**
  (Node-VM contract-tested), like `get_dashboard_summary`→`buildAttentionCenterHTML` and
  `get_system_health`→`systemHealthChecks`.

## Hard constraint (the honest scope line)

Full **transitive** dependency resolution only happens inside the real transaction (privileged,
heavy, source-specific). The preview must **not** re-implement the resolver. So increment 1 shows
what is *cheaply* knowable up front and is clearly labelled as such:

- repo packages: `pacman -Si` → version, repository, **download size**, **installed size**,
  **direct depends**, **optdepends**, conflicts/replaces.
- AUR packages: RPC `get_info` → version, maintainer, **direct depends/makedepends**, the existing
  AUR safety signals (PKGBUILD scan findings, maintainer-change advisory) — **no size** (AUR builds
  from source; unknown until built — say so).
- Flatpak: Flathub summary → version, download size, **permissions/safety tier** (already computed
  by `gems/flatpak/permissions.py`), verified/FOSS badges.

Deps are shown as **"direct dependencies"** with a note that pacman/makepkg resolves the full set
at install time. This is accurate and avoids a fragile second resolver.

## Backend

New pure assembler (location TBD — likely `atlas/view/webview/transaction_preview.py` or a method
cluster on `AtlasApi`):

```
build_install_preview(pkg) -> {
    action: 'install',
    name, source, version,
    sizes: {download, installed} | None,          # None for AUR (built from source)
    deps: {direct: [...], optional: [...]},        # direct only; note full-resolution caveat
    warnings: [ {level, title, detail}, ... ],     # AUR PKGBUILD findings, maintainer change,
                                                    #   unverified Flatpak, proprietary, etc.
    permissions: [...] | None,                      # Flatpak only (reuse permissions.describe)
    notes: [...],                                   # "deps resolved at install time", etc.
}
```

- Reuse existing signals — **do not** add new fetch paths where one exists:
  `pacman.map_download_sizes`/`get_installed_size`/`map_required_dependencies`, the AUR audit
  (`pkgbuild_audit` / maintainer cache), `flathub`/`permissions` modules.
- **Fail open per field** (same discipline as `get_dashboard_summary`): a failed size/dep/badge
  fetch yields `None`/`[]` and a "couldn't determine" note — never blocks the install.
- New `AtlasApi.get_install_preview(pkg_id)` exposes it to the webview.

## Frontend

- `AtlasApi.install(pkg_id)` no longer fires immediately from the card/detail button. The button
  calls a new `previewThenInstall(pkgId)`: fetch `get_install_preview`, render the modal, and only
  on confirm call the existing `install` path (root-password → terminal → transaction — unchanged).
- New self-contained modal `#transaction-preview-modal` (promise-based, like `#news-gate-modal` —
  the confirm modal is bound to the Python watcher and can't be reused) with a pure renderer
  `buildTransactionPreviewHTML(data)` (Node-VM-tested): header (name + source pill + version),
  a size row, a collapsible deps accordion, a warnings/permissions block, the confirm/cancel
  footer. Reuse `.meta-badge`, `emptyStateHTML`-style helpers, existing safety colours.
- Settings toggle later (skippable preview); **default on** for increment 1. Keep it out of scope
  if it bloats — note in STATUS.

## Interaction with existing gates

The AUR PKGBUILD review and Update-All news gate fire **mid-build** today. For install, the new
preview surfaces the *same* AUR findings up front. Decide during implementation whether the
pre-build `request_confirmation` becomes redundant for the install path (likely keep it — it runs
after the optional PKGBUILD edit step, so it sees the final text; the preview is advisory-before).
Document the call; do not silently double-prompt without a note.

## Tests

- `test_api.py::InstallPreviewTest` — payload shape per source (repo / AUR / Flatpak), fail-open on
  each field, AUR-has-no-size, warnings surfaced.
- `main_js_contracts.test.js` — `buildTransactionPreviewHTML` renders each section, handles
  missing/None fields, escapes names.

## Out of scope (later increments)

- ~~uninstall / downgrade previews~~ → increment 2 (see below).
- Update preview (current→new + maintainer/diff/news/.pacnew rollup) + Update-All aggregate.
- The source-comparison **panel** UI on detail pages (this increment only shapes the data for it).
- Full transitive dependency tree.
```

## Increment 2 — uninstall + downgrade previews (2026-06-04)

Same shape + a new `action` field (`install`/`uninstall`/`downgrade`); the modal title, description,
proceed-button label, and size-row label key off it. The pure renderer `buildTransactionPreviewHTML`
stays generic — only label selection was added.

- **Uninstall** (`get_uninstall_preview` → `_preview_uninstall_arch`): reverse dependencies via
  `pacman.map_required_by([name])` (the cheap "Required By" signal) → a **danger** warning listing the
  installed packages that depend on it (truncated), or a reassuring note when nothing does; **freed
  space** from `pacman.get_installed_size([name])` (shown as "Frees"); an orphan-cleanup note. Flatpak:
  freed size from `pkg.size` + a runtime-reclaim note. No reverse-dep concept off Arch.
- **Downgrade** (`get_downgrade_preview`): advisory only — a **warn** ("rolling back can reintroduce
  fixed bugs/security issues") + notes ("you'll pick the version next", "deps aren't downgraded",
  AUR rebuilds from the previous source). No target enumeration (the gem prompts; cheaply unknowable).
- Honest scope unchanged: no second resolver, fail-open per field, never blocks the action.
- Frontend: `installApp`/`uninstallApp`/`downgradeApp` all await a shared
  `showTransactionPreview(id, action)` (generalised from `showInstallPreview`). Cancel aborts cleanly.
- Tests: `test_api.py` uninstall/downgrade payloads (reverse-dep danger, freed size, fail-open) +
  `main_js_contracts` action-aware labels.

## Increment 3 — update + Update-All aggregate (2026-06-04)

- **Single-package update** (`get_update_preview`): an update is an *acquire of a newer version*, so it
  reuses the install assembler (extracted as `_assemble_acquire_preview(pkg, action)`) and just adds
  `from_version`. The header renders **`v{old} → v{new}`** for `action==='update'`. Same per-source
  advisories as install (AUR maintainer-change/out-of-date/community, Flatpak permissions). Wired into
  `updateApp`.
- **Update-All aggregate** (`action==='update-all'`): **frontend-assembled** by pure
  `buildUpdateAllPreviewData(updates, extras)` — built from the **already-loaded** updates list so it
  costs **no extra `read_installed`** (the measured-cost call). Shows package count, per-source split
  (Arch/AUR/Flatpak), total download size (only over packages that report one; AUR builds from source
  → excluded, noted), and folds in the cheap `check_upgrade_news` count + `get_pacnew_files` count as
  warnings. Reuses the same modal/renderer via a synthesised payload. The existing **rich news gate is
  kept** and fires *after* the aggregate (it shows the clickable articles); the aggregate is the "what",
  the news gate is the "read this first". `update_all` itself unchanged.
- Tests: `test_api.py::UpdatePreviewTest` (version delta, fail-open) + `main_js_contracts`
  (version-delta render, `buildUpdateAllPreviewData` split/sizes/warnings). Suite 480 + JS 28.
- **Needs a GUI eyeball:** single update → `v→v` + size; Update-All → aggregate modal (counts/split/
  size/news), then the news gate when there's news; cancel at either stage aborts.

## Increment 4 — source-comparison panel (2026-06-04, theme complete)

When an app is offered by **more than one source** (e.g. Steam from the Arch repo + Flathub), the
detail page now shows a compact "pick where to install from" table above the description. Pure
`buildSourceCompareHTML(group)` (Node-VM-tested) builds one row per source — source pill, version,
size, a one-line characterisation (`sourceCompareNote`: AUR = community/built-from-source, Flatpak =
sandboxed/cross-distro, repo = official, …), and an **Install** button for each non-installed source
(the installed one shows "✓ Installed"). Built **entirely from the in-memory group** the grid already
collapsed (`collapseByName`) — **no extra backend calls**; each Install button routes through the
normal `installApp` (and thus its full transaction preview), so the panel is a fast at-a-glance
chooser and the preview is the deep-dive. `openDetailModal(pkg, group)` gained an optional `group`
(card clicks pass it; otherwise `findGroupForPkgId` looks it up); single-source apps render nothing
(`#detail-source-compare:empty{display:none}`). Test: `main_js_contracts::testBuildSourceCompareHTML`.
**Needs a GUI eyeball** (open a multi-source app's detail → table renders; Install from the other
source works).

## What was actually built (increment 1)

- **Backend** (`api.py`): `get_install_preview(pkg_id)` + `_source_label` + per-source helpers
  `_preview_arch_repo` / `_preview_aur` / `_preview_flatpak`. Reuses `pacman.map_updates_data`
  (one `-Si` call → version/download+installed size/direct depends) + `pacman.map_optional_deps`,
  the AUR RPC (`aur_client.get_info` → version/maintainer/depends/makedepends/out-of-date), and the
  Flatpak `get_flathub_metadata` (permissions + safety tier + verified/FOSS badges). Fails open per
  field; a top-level failure returns a minimal payload (still `ok`) so the user can always proceed.
- **Frontend** (`main.js` + `index.html` + `style.css`): pure `buildTransactionPreviewHTML(data)`
  (header / size row / sorted warnings / permissions accordion / deps accordion / notes) + a
  promise-based `#tx-preview-modal` (`openTransactionPreview` / `showInstallPreview` /
  `resolveTxPreview`, mirroring the news gate). `installApp` now awaits `showInstallPreview` before
  anything privileged; cancel aborts with nothing started. Both card and detail-modal installs route
  through `installApp`, so one gate covers both.
- **Tests:** `test_api.py::InstallPreviewTest` (5: repo/AUR/Flatpak payloads, fail-open, unknown id)
  + `main_js_contracts` (5: full render, missing-field, escaping, + the two gate-flow regression
  tests below).
- **Bug found in GUI test + fixed:** the gate silently skipped — `pyApiCall` **unwraps** the
  `{status,data}` envelope (returns `response.data`), but `showInstallPreview` checked
  `res.status !== 'ok'` on the already-unwrapped payload, so it always returned `true` (proceed)
  and the modal never showed. Now it treats the result as the payload (guards on `data.name`). Added
  `testShowInstallPreviewOpensModalThroughEnvelope` + `...ProceedsWhenBridgeReturnsNothing` so the
  full fetch→render→resolve path is covered, not just the pure renderer.

## Decision resolved (per user, "keep it")

The existing **mid-build AUR PKGBUILD `request_confirmation`** is **kept** — it runs after the
optional PKGBUILD-edit step so it sees the final text, whereas the new preview is advisory-before.
They are complementary, not duplicates. No change to that path.

## Verification

`python -m pytest` green (468); `node main_js_contracts.test.js` green (22). **Still needs a GUI
eyeball:** install preview for a repo pkg, an AUR pkg, and a Flatpak (sizes/deps/warnings/perms
render; confirm proceeds, cancel aborts cleanly).
