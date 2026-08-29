# Update cancellation clarity

**Date:** 2026-08-29  
**Status:** implemented

## Problem

The live Atlas log shows two recent Update All runs waiting five minutes for user input and then
surfacing as generic failures:

- 2026-08-29: the root-password prompt timed out before any package transaction started.
- 2026-08-26: the Google Chrome AUR PKGBUILD review timed out after earlier update work had run.

The backend correctly fails closed, but timed-out HTML modals remain open and the Update All
front-end turns a structured `cancelled` result into the misleading message "Bulk upgrade failed".
That makes an intentional safety cancellation indistinguishable from a package-manager failure.

The host package tools are healthy: read-only `checkupdates`, `paru -Qua`, and Flatpak update
discovery all complete successfully, and there is no pacman database lock.

## Changes

1. Ask for Update All authentication before opening the operation terminal, so the password prompt
   is the only blocking surface and the terminal never claims an update started before auth.
2. Return an explicit cancellation message when Update All receives no root password.
3. Teach the front-end to render `status: cancelled` as a cancellation, not an error.
4. Add JS-only dismiss hooks for password and confirmation modals; call them when backend waits time
   out so stale dialogs cannot remain interactive after their operation has already aborted.
5. Put a clear timeout reason into the terminal log when a transaction confirmation expires, so an
   AUR review timeout is visible in the failure summary/raw output.
6. Add focused Python and JS contract coverage, then run the full suites.

## Scope / safety

- No package command, dependency planning, or fail-closed decision changes.
- No timeout is made longer and no confirmation is auto-accepted.
- No package updates are executed as part of verification.

## Status

- Implemented in the webview API/front-end with focused timeout/cancellation contracts.
- Verification: 783 Python tests and 63 JavaScript contract tests pass.
- Not yet exercised through a real password/review timeout in WebKitGTK; the modal callbacks and
  backend timeout branches are contract-tested without waiting five minutes.

## Follow-up decision (2026-08-29)

The five-minute deadline itself is superseded by
[operation attention notifications](2026-08-29-operation-attention-notifications.md): blocking
password/review/message prompts now wait for an explicit answer and send a critical desktop
notification instead of automatically cancelling. The distinct cancellation-vs-failure result
and messaging from this plan remain in use for explicit Cancel/No actions.
