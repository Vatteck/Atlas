# Source types rework + multi-source app cards — design + plan

**Date:** 2026-06-01
**Status:** Phase 1 + Phase 2b implemented (2026-06-01); Phase 2a (cross-source cards) pending.
Phase 2b renders AUR variants flat but already computes base-name + variant kind, so nesting
them under a grouped card later is a render-only change.
**Type:** Python (gem enablement) + webview front-end. No Rust.

## Goal & context

Atlas is being focused as an **Arch-targeted** all-in-one installer covering exactly four
sources, mapping to how the user gets software:

| source | gem / `get_type()` | trust |
|---|---|---|
| official repos (pacman) | arch → `arch_repo` | trusted |
| AUR (yay) | arch → `aur` | **community, less vetted** |
| Flatpak | flatpak → `flatpak` | sandboxed |
| AppImage | appimage → `AppImage` | sandboxed |

**Hard rules (from the user):**
- **Arch and AUR are always separate and clearly labelled** — never collapsed into one
  "Arch". When an app has both, official repo is preferred and AUR is visibly marked.
- Snap / Debian / Web are not relevant on Arch and should not appear.

## Problems with the filter today

1. **It doesn't filter.** `pkg_type` is passed to `search/get_installed/get_updates/
   get_suggestions` but those methods ignore it, and there's no client-side filtering. The
   dropdown is decorative.
2. **Incomplete + wrong types.** Options are `appimage/flatpak/snap/aur/web`. Arch
   official-repo (`arch_repo`) and Debian are absent; `aur` catches only half of Arch.
3. **Casing.** AppImage's type is `AppImage` but the filter value is `appimage`.
4. **Raw tags.** Cards show the raw token (`arch_repo`) instead of a friendly label.

---

## Plan

### Phase 1 — Source set + working filter (low risk)

1. **Disable snap/debian/web gems** by overriding `is_default_enabled() -> False` in
   `gems/{snap,debian,web}/controller.py`. `config['gems']` defaults to `None`, so this
   takes effect immediately while staying user-overridable via Settings. Localized,
   reversible, no deletion (respects the "don't big-bang" guardrail).
2. **Filter dropdown** (`index.html`) → `All Types, Arch, AUR, Flatpak, AppImage` with
   values `all / arch_repo / aur / flatpak / appimage`.
3. **Make filtering real, client-side.** Fetch once with no type constraint and filter the
   in-memory `currentPackages` by a normalized source token before render. Switching the
   filter becomes instant (no refetch). Add `normalizeType()`:
   `arch_repo→arch_repo, aur→aur, flatpak→flatpak, 'AppImage'→appimage`.
4. **Friendly labels + trust styling.** Token→label map (`arch_repo→"Arch"`, `aur→"AUR"`,
   …). The **AUR** tag gets a distinct style + tooltip ("AUR — community-maintained, less
   vetted than the official repo"). Keep the existing per-type tag colors otherwise.

### Phase 2 — Multi-source cards (the bigger piece)

When the same app is offered by more than one source, render **one card** with a source
switcher; the underlying per-source package objects (already distinct, id = `type:name`)
remain individually actionable — this is a presentation layer only, no backend identity
model.

1. **Grouping (client-side).** Group the filtered list by a **normalized exact name** key
   (`name.trim().toLowerCase()`).
   - *Why exact:* conservative — avoids merging two unrelated apps that share a name. The
     safe failure mode is "didn't merge" (shows as separate cards, like today), e.g. when a
     Flatpak's display name ("GNU Image Manipulation Program") differs from the Arch pkg
     name ("gimp"). Fuzzier matching can come later if wanted.
2. **Source ordering within a group:** installed source first (always), otherwise the
   user's trust/preference order **arch_repo → aur → flatpak → appimage**. The first becomes
   the card's default-selected source.
3. **Switcher UI (proposed):** small inline **segmented pills** on the card
   (`Arch | AUR | Flatpak`), AUR pill marked. Selecting one re-targets the card's
   version/Install/Uninstall/Run/Details to that source's package id. (Open to a dropdown
   instead — easy swap.)
4. **Interaction with the filter:** filter first, then group. With a specific type
   selected, each group has ≤1 matching source so pills don't show; grouping is meaningful
   mainly under "All Types".
5. **Detail panel / actions** read the active source's serialized pkg (by id), so no
   action-routing changes are needed beyond passing the selected id.

### Phase 2b — AUR variants (decided 2026-06-01)

AUR `-bin`/`-git`/base/forks are **different build choices** (precompiled binary vs VCS
HEAD vs tagged source vs a fork), not interchangeable copies, so they are **NOT grouped**
— each stays its own card. Instead, make them legible and well-ordered (decision: "keep
all separate, just rank + badge"):

- **Badge** each AUR card with its build kind, derived from the name suffix:
  `-git/-svn/-hg/-bzr/-cvs/-nightly` → **git/VCS**, `-bin` → **binary**, `-debug` → debug,
  otherwise **source**. (Variant detection is fine on the front-end from `pkg.name`.)
- **Rank** AUR results: most-voted/popular first, **demote VCS (`-git` …) and
  `out_of_date`**, and **never rank a VCS variant first** (decision: "most-voted non-VCS").
- **Expose the metadata** the ranking/badges need — `_serialize_pkg` currently omits them.
  Add `votes`, `popularity`, `maintainer`, `out_of_date` (and optionally `package_base`)
  to the serialized payload (AUR-only; other gems leave them null). Surface votes/maintainer/
  out-of-date on the card so the choice is informed.
- Forks (different base name, e.g. `foo` vs `foo-cachyos`) stay fully separate — no
  base-name grouping. AUR names are unique, so "same name / different maintainer" can't
  occur; "different maintainer" always means a different package.

### Out of scope / later
- Fuzzy / id-normalized matching (strip flatpak vendor prefixes, compare AppImage display
  names to pkg names). Start exact; revisit if too many real dups stay split.
- Backend-side filtering/grouping (kept client-side; results are already a flat list).
- Sizes from Flathub `summary/{id}`; confirm-modal option icons (tracked separately).

## Risks
- **False merges** from name collisions → mitigated by exact-normalized-name matching.
- Disabling gems changes what a returning user sees; mitigated by leaving them
  re-enableable in Settings and noting it in STATUS.

## Test plan
- JS: pure helpers (`normalizeType`, `groupBySource`, source ordering) unit-tested if a JS
  harness exists; otherwise validated manually + via the Python serialization staying
  unchanged.
- Python: a test asserting snap/debian/web `is_default_enabled()` is False and arch/
  flatpak/appimage stay True.
- Manual GUI: filter each type; confirm a multi-source app (e.g. an app in both repo and
  AUR/Flatpak) shows one card with a working switcher and AUR clearly marked.
