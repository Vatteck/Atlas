# Release smoke checklist

Atlas's GUI can't be driven headlessly (WebKitGTK), and CI only covers the pure-Python logic
plus the Arch build/install layout. So before tagging a release that strangers will install,
walk this once. It's deliberately short — the goal is to catch the **environment-dependent**
breakage automation can't, not to re-test everything.

Run `atlas --self-check` first on each session and paste/skim the output — it tells you which
paths *this box* actually exercises (tray, terminal, mirror tool, etc.).

## Per session: KDE Plasma **and** GNOME

Log into each (Wayland is fine; note the session type from `--self-check`). On GNOME the tray
needs the AppIndicator extension — that's expected, not a bug.

- [ ] **Launch** — `atlas --logs` opens the window; no blank page; dashboard renders.
- [ ] **Tray** — icon appears (KDE native; GNOME w/ AppIndicator ext). Count badge updates;
      menu navigation works; close-to-tray only if you enabled it.
- [ ] **Search + detail** — search an app, open detail, screenshots/history load.
- [ ] **Update All** — the source toggles show with counts; unticking AUR is remembered next
      open; the pre-flight is snappy (no multi-minute hang); the confirm button count tracks
      the toggles.
- [ ] **A real transaction** — install or update one package end-to-end; terminal shows
      progress; outcome toast is correct.
- [ ] **Settings** — toggles persist across a restart.

## Environment edge cases (do at least once per release, any session)

- [ ] **No `reflector`/`rate-mirrors`** box (or temporarily rename them) — Settings → Mirrors
      disables the regenerate button with an "install a mirror tool" hint instead of erroring.
- [ ] **No `pacman-contrib`** — update detection falls back (no crash); pacdiff button explains
      it needs the package.
- [ ] **No AUR helper** — AUR build path still works (Atlas builds via makepkg itself).
- [ ] A terminal other than the one `--self-check` reports, if you can, for the pacdiff launch.

## Before pushing the tag

- [ ] `python -m pytest` green; CI green (incl. the **Arch — tests + package build** job).
- [ ] `__version__` bumped, `CHANGELOG.md` `[Unreleased]` promoted to the version + date.
- [ ] `README.md` "Status:" line + "What's new" reflect the version.
- [ ] `./linux_dist/arch/release.sh` run; the pinned `atlas-pm` PKGBUILD **actually builds**
      (`cd linux_dist/arch/release && makepkg -f`) and the installed app launches.
