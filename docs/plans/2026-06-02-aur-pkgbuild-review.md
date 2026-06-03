# AUR safety: PKGBUILD-diff review + heuristic flagging — 2026-06-02

> **Status: design note.** Layers 1 + 2 of the "AUR safety" theme (layer 3 = sandboxed chroot
> builds, see [2026-06-02-sandboxed-aur-builds.md](2026-06-02-sandboxed-aur-builds.md)).

## Goal & honest framing

Make it *easy and likely* that a user actually looks at what an AUR package will run before they
build it — especially **what changed** in an update (the "compromised release" / axios-style
threat). Two complementary, **no-AI** aids:

1. **Diff review** — show what changed in `PKGBUILD` / `.install` / `.SRCINFO` since the version
   last built, instead of (or alongside) the full file. Catches a malicious update as a visible diff.
2. **Heuristic flagging** — highlight known-suspicious constructs so the eye stops on the right lines.

**This is a helper, not a verdict.** It finding nothing does **not** mean safe; it's easily evaded
(obfuscation), throws false positives (legit PKGBUILDs use `curl`/`eval`), and must never auto-block
or display a "safe" badge. Most users skip the PKGBUILD entirely — the win is nudging a second look.

## What exists today

- `edit_aur_pkgbuild` config (None=ask / True / False); `_ask_for_pkgbuild_edition` →
  `_display_pkgbuild_for_editing` (`controller.py:2005`) reads the PKGBUILD and shows it in a
  `watcher.request_confirmation` **text component** (editable). The webview renders that confirm modal.
- AUR packages are **git clones** (`git.py: clone`, `list_commits`); no `diff` helper yet.
- `mark/unmark`-PKGBUILD actions + `EDITABLE_PKGBUILDS_FILE` track which pkgs the user wants to edit.

So the *review surface* already exists — we enrich it (diff + flags), we don't build it from scratch.

## Layer 2 first: the heuristic scanner (pure, AI-free, testable)

New pure module `atlas/gems/arch/pkgbuild_audit.py`:

```python
def scan(text: str) -> list[Finding]   # Finding = {line_no, line, rule, severity, why}
```

Stateless regex/substring rules over the PKGBUILD (and `.install` scriptlets). Starter ruleset
(curated, tuned to limit false positives — each is "look here," never "malware"):

- **pipe-to-shell**: `curl|wget … | sh|bash`, `| sh -`, `bash <(…)`
- **base64 / obfuscation**: `base64 -d|--decode`, long base64-looking literals, `\xNN` hex runs,
  `eval`, `${IFS}`, `$(printf '\\…')` — base64 in a PKGBUILD is inherently unusual → flag it.
- **off-source network in build()/package()**: `curl`/`wget`/`nc`/`/dev/tcp`/`ftp` *inside* the
  build/package/prepare functions (sources should be declared in `source=()`).
- **sensitive writes**: `~/.ssh`, `authorized_keys`, `~/.bashrc|.zshrc|.profile`, `/etc/sudoers`,
  `crontab`, `systemctl`/`.service`, autostart `.desktop`, `/etc/cron*`.
- **privilege/perm**: `chmod +s`/setuid, `sudo ` inside scriptlets, broad `rm -rf` on `$HOME`/`/`.
- **source sanity**: `source=()` host ≠ upstream `url=`; `git+`/raw URLs to forks/gists.

Severity is advisory (`info`/`warn`) only. Rules live as data so they're easy to extend/tune.
**Heavily unit-tested** (clean PKGBUILD → no findings; each rule → fires on a crafted sample +
does NOT fire on a benign lookalike where feasible). This is the layer that can be fully verified
headlessly, so build + lock it first.

## Layer 1: diff since last build

- Add `git.diff(proj_dir, from_ref, to_ref, paths=[…])` to `git.py` (the clone is a git repo).
- Reference = the commit last built for this package. Check whether the AUR `ArchPackage`/build
  flow already records the built commit (it tracks `commit`); if so, diff `last..HEAD` over
  `PKGBUILD .SRCINFO *.install`. **First install / no prior commit → no diff**, fall back to
  showing the full PKGBUILD (today's behavior).
- Surface in the review modal: default to the **diff** when one exists, with a "show full PKGBUILD"
  toggle; run the layer-2 scanner over the new content and annotate flagged lines + a summary
  banner ("N things worth a look — this is a hint, not a safety check").

## Frontend

Enrich the existing PKGBUILD review (confirm-modal text component) — or, more likely, a dedicated
review component — to render: the diff (added/removed lines), inline flag markers, and the
advisory summary. Keep the **edit** capability. Exact rendering TBD with the webview component model.

## Build order / increments

1. ~~**`pkgbuild_audit.scan()` + tests**~~ ✅ Done (`3b4c43b`).
2. ~~diff-since-last-build + commit lookup~~ ✅ Done (`0090959`) — uses AUR cgit fetch-by-commit
   (`_fetch_pkgbuild_at_commit`) rather than a `git.diff` helper, since the clone is shallow.
3. ~~Wire into the review UI~~ ✅ Done. Advisory gate (`30fa297`) runs before every AUR build; the
   review now **renders richly** (2026-06-03): `pkgbuild_audit.diff_lines()` → structured diff,
   `_audit_pkgbuild` sends a `{name, summary, diff, findings}` `review` payload through
   `request_confirmation`→`prompt_confirmation`→`showConfirmModal`; `renderPkgbuildReview()` draws
   the colored +/- diff + severity-flagged lines + "not a verdict" banner. **Resolved open Qs:**
   the build flow *does* persist the built commit (`pkg.commit`); rendering reuses the confirm
   modal (no purpose-built view needed) — the blocking decision flow stays intact.
4. ~~Setting to review AUR PKGBUILDs~~ ✅ Done — `aur_check_pkgbuild` config + `check_pkgbuild`
   toggle in webview Settings (defaults on).

**Layers 1 + 2 of the AUR-safety theme are complete.** Only layer 3 (sandboxed chroot builds)
remains, tracked in its own plan.

## Open questions

- Does the build flow already persist the built commit per package? (verify before designing the
  diff reference; fallback = cache the last-approved PKGBUILD text.)
- Default posture: keep edit-on-ask, or move toward "always show the diff for AUR updates"?
- Rendering: extend the generic confirm-modal text component, or a purpose-built review view?
