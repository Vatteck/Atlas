# 2026-07-17 — Read the PKGBUILD inside the pre-build review modal

## Problem (Vatteck GUI report, with screenshot)

During **Update All**, the advisory "Review PKGBUILD" confirmation (from
`ArchManager._audit_pkgbuild`) can pop mid-transaction — e.g. a maintainer-change advisory
for `visual-studio-code-bin`. The modal's own body says *"Read the PKGBUILD."* — but it
offers **no way to do that**. Choices are Cancel (aborts that package's build; in an
Update All you then have to hunt the package down later and use the detail-view PKGBUILD
viewer) or "Build anyway" (proceed unreviewed). The one thing the dialog asks the user to
do is the one thing it doesn't let them do.

Root cause: `_audit_pkgbuild` reads the PKGBUILD text (and `.install` scriptlets) to scan
them, but the structured `review` payload it passes to `request_confirmation` only carries
`summary` / `diff` / `findings` / `maintainer_change` — never the file text. When the only
trigger is a maintainer change (no flagged lines, no diff), the modal shows a single
banner and zero code.

## Fix — ship the text it already has

Backend (`atlas/gems/arch/controller.py`, `_audit_pkgbuild`):

- While scanning, collect per-file entries `{'name', 'text', 'findings'}` for the PKGBUILD
  and each `*.install` scriptlet (skipping unreadable/empty ones), and add them to the
  `review` payload as `files`. The text is already in memory at this point — no new I/O.
- Guard: truncate any single file at 400k chars (marker appended). PKGBUILDs are tiny;
  this only defends the JS bridge against a pathological/adversarial file.

Frontend (`main.js` `renderPkgbuildReview` + `style.css`):

- Render each `review.files` entry as a collapsed `<details class="review-pkgb-file">`
  ("Read the PKGBUILD · N lines", one per file) after the findings list, containing the
  existing line-numbered, syntax-highlighted, severity-flagged code renderer
  (`buildPkgbuildCodeHTML`) in a scroll-contained `.pkgbuild-code` block.
- `buildPkgbuildCodeHTML` gains an optional `idPrefix` param so line-anchor ids can't
  collide with a previously-rendered PKGBUILD-viewer modal in the same DOM.
- Collapsed by default: the modal stays as compact as today; one click opens the code
  in place. No new buttons, no change to Cancel/Build-anyway semantics.

## Tests

- `test_pkgbuild_audit_gate.py`: `review['files']` carries the PKGBUILD text; `.install`
  scriptlets appear as their own entries; findings are attributed to the right file.
- JS contract test: `renderPkgbuildReview` with `files` renders the details block and
  highlighted lines; without `files` behaves as before (export it in the test hooks).

## Non-goals

- No "open the full PKGBUILD viewer" cross-modal jump (the viewer is wired to detail-view
  packages, not a mid-transaction context; embedding the text is simpler and offline).
- No change to when the gate fires or what Cancel does.
