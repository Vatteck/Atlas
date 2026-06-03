# Arch-correct mirror refresh + mirrorlist regen action — 2026-06-02

> **Status: design note (caution shipped; regen not started).** Prompted by a real incident: a user
> overwrote `/etc/pacman.d/mirrorlist` with the stock all-commented `.pacnew` via the new pacdiff
> button, wiping all `core`/`extra` mirror servers (`no servers configured for repository: extra`).

## Problem / findings

1. **`mirrorlist` is the #1 pacdiff footgun.** Its `.pacnew` (from `pacman-mirrorlist` updates) is
   the stock, fully-commented list; merging/overwriting it deletes the user's working mirrors. ✅
   **Shipped:** a pointed caution in the `.pacnew` notice when `mirrorlist` is among the files
   (steer to regenerate/discard, never overwrite). Frontend-only (`renderUpdatesNotice` +
   `.config-notice-warn`).
2. **The existing mirror refresh is Manjaro-only and dead on Arch.** `pacman.refresh_mirrors()` runs
   **`pacman-mirrors -g`** — a *Manjaro* tool not present on Arch/CachyOS (which use
   `reflector` / `rate-mirrors` / `cachyos-rate-mirrors`). So `ArchManager.refresh_mirrors` (a custom
   action) silently can't work on the target platform — a bauh/Manjaro leftover. (Recorded in STATUS
   Known gaps.)

## Proposed feature: a working "Regenerate mirror list" action

**Not** silent auto-regeneration on `.pacnew` detection — that's overreach (privileged, network, and
mirror choice is region-dependent). Instead an explicit, opt-in action:

- **Fix `refresh_mirrors` to be Arch-correct:** detect an available tool in priority order —
  `reflector` (Arch standard), then `rate-mirrors` / `cachyos-rate-mirrors` (CachyOS) — and run it to
  regenerate `/etc/pacman.d/mirrorlist`. Keep Manjaro's `pacman-mirrors` only if it's actually present
  (so Manjaro users aren't broken). If none found → clear "install reflector" message.
  - reflector example: `reflector --protocol https --latest 20 --sort rate --save /etc/pacman.d/mirrorlist`
    (+ optional `--country`). Privileged → route through the root broker.
- **Surface it:** a "Regenerate mirror list" button (a) in the `.pacnew` mirrorlist caution, and/or
  (b) as an Arch action / Disk-or-Settings entry. Confirm before running; show output via the watcher.
- Keep it user-initiated and transparent (show the command + chosen tool), with sane defaults.

## Open questions

- Tool/arg defaults (count, sort, country detection)? Offer a country picker like the legacy
  `refresh_mirrors` already does, but feed it to reflector instead of pacman-mirrors.
- Where to surface the button: the `.pacnew` caution is the most contextual; a general Arch action is
  also reasonable.

## Scope note

The caution (footgun guard) is done. The regen action is a medium feature that doubles as fixing a
real Manjaro-leftover bug — worth doing, but its own increment with the root-broker/privileged flow.
