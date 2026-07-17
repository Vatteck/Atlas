# TOCTOU-Safe AUR Install — 2026-07-16

## Problem

When a user reviews a PKGBUILD then clicks Install, Atlas re-clones the AUR git
repo (`_install_from_aur` → `git.clone`). A malicious maintainer could swap the
PKGBUILD between review and build — the user reviewed file A but the build uses
file B. Low-probability, real risk (the June 2026 Atomic Arch campaign showed
maintainers swapping PKGBUILDs within hours).

## Solution: Review-hash verification

1. When `get_pkgbuild()` fetches a PKGBUILD for review, cache its SHA256 hash
   keyed by package base name.
2. When `install()` is called for an AUR package with a cached hash:
   a. Re-fetch the live PKGBUILD text
   b. Compare SHA256 hashes
   c. Match → proceed normally (no TOCTOU)
   d. Mismatch → re-scan the new PKGBUILD, show findings in a confirmation
      dialog. User can abort or proceed with the changed PKGBUILD.
3. Clear cache after successful install.

## Implementation

- `AtlasApi._reviewed_pkgbuilds: dict` — `{base_name: {sha256, reviewed_at}}`
- `_verify_pkgbuild_toctou(pkg) -> dict` — re-fetches and compares. Returns
  `{status: 'ok'|'changed'|'error', findings: []|None, ...}`
- `install()` calls `_verify_pkgbuild_toctou()` for AUR packages before
  delegating to the Arch manager. On mismatch, prompts user via JS confirmation.
- JS side: `showTransactionPreview` → new `showPkgbuildChangedWarning()` modal.

## Non-changes

- Not caching the full PKGBUILD text (just the hash) — keeps memory footprint low.
- Not modifying the Arch build pipeline (`_install_from_aur`) — the controller
  doesn't need to know about review state.
- Not storing hashes on disk — per-session only. If the session restarts, the
  user reviews again (which is correct behavior).

## Verification

- Manual: install an AUR package, review PKGBUILD, confirm TOCTOU check passes.
- Can't easily test the mismatch path without mocking the AUR.
