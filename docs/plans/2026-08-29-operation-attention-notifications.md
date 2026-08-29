# Operation attention notifications

**Date:** 2026-08-29  
**Status:** implemented

## Problem

An AUR-heavy Update All can spend a long time building between PKGBUILD review prompts. On
Hyprland, Atlas may be on another workspace or monitor when the next prompt appears, so the user
has no reliable signal that the transaction is paused. The existing five-minute backend deadline
then cancels the operation even though nothing is actually wrong.

## Decision

Interactive package operations should wait for an explicit answer. A forgotten prompt is not a
package failure, and an arbitrary five-minute deadline is hostile after a long build.

1. Remove automatic password, confirmation, and blocking-message cancellation deadlines. The
   existing modal Cancel/No controls remain the way to abort, so behavior stays fail-closed.
2. Send a critical desktop notification whenever Atlas opens one of those blocking prompts. The
   notification says the operation is paused and names the requested action (for example,
   "Review PKGBUILD"). Respect the existing System notifications setting.
3. Mark the transaction terminal as waiting for the named action, then switch it back to
   "Continuing…" after the answer.
4. Build notification commands as argument arrays instead of interpolated shell strings, and add
   the `atlas-pm` desktop-entry hint so notification daemons can associate the alert with Atlas.
5. Update the Settings description so "System notifications" explicitly covers operations that
   need attention, not only completion.

## Scope / safety

- No package command, build, dependency-planning, or confirmation decision changes.
- Atlas never auto-accepts a prompt.
- Atlas does not steal focus or move itself across workspaces; the desktop notification is the
  cross-workspace signal.

## Verification

- Focused API and notification-command tests pass.
- Full suite: 787 Python tests and 62 JavaScript contract tests pass.
- Live Hyprland notification/PKGBUILD timing remains a manual smoke check; the real installed
  stable app is still 0.16.1 and does not contain this change.
