# Arch-correct mirror refresh + mirrorlist regen action — 2026-06-02

> **Status: DONE (caution + `regenerate_mirrorlist` button shipped). Gem-action fix dropped.**
> Prompted by a real incident: a user overwrote `/etc/pacman.d/mirrorlist` with the stock
> all-commented `.pacnew` via the new pacdiff button, wiping all `core`/`extra` mirror servers.
> The mirrorlist caution + the reflector/rate-mirrors `regenerate_mirrorlist` button (`.pacnew`
> notice + Settings → Mirrors) shipped (24dd152 / 8f3c6c8). **Finding #2 (fix the Manjaro
> `refresh_mirrors` gem action) is intentionally NOT pursued (2026-06-03):** it's inert on Arch
> and superseded — see STATUS Known gaps. Left as dead code; not worth refactoring the startup
> DB-sync flow for zero runtime gain.

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
