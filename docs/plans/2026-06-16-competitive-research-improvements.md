# Competitive research improvements

**Date:** 2026-06-16
**Status:** Theme 1 shipped 2026-06-16 (17 new audit rules, 14 → 31). Themes 2–6 not started.
**Sources reviewed:**
[arch-toolkit](https://github.com/Firstp1ck/arch-toolkit) (Rust AUR library),
[ks-aur-scanner](https://github.com/KiefStudioMA/ks-aur-scanner) (Rust PKGBUILD security scanner, 115+ rules),
[Pacsea](https://github.com/Firstp1ck/Pacsea) (Rust TUI package manager)

---

## Context

All three are Rust projects. Atlas stays pure-Python (AGENTS.md §3.2) — we're learning from
their feature designs, not their implementation language. Each project validates Atlas's
direction (PKGBUILD review, AUR trust scoring, transaction previews) while surfacing gaps
we should close.

---

## Theme 1: Expand PKGBUILD audit rules (14 → ~40) — ✅ shipped 2026-06-16

> **Shipped:** 17 new rules added to `_RULES` in `pkgbuild_audit.py` (14 → **31** total), covering all
> the categories enumerated below: reverse shells (3), credential theft (2), persistence (4),
> obfuscation (3), dependency confusion (1), weak integrity (2), privilege escalation (2). Each has a
> positive + false-positive-safe test in `test_pkgbuild_audit.py::CompetitiveResearchRuleTest`;
> `CLEAN_PKGBUILD` stays at zero findings. New helper `_has_insecure_http_source` handles the
> git+http / localhost exclusions. Suite **603** + JS **48** green. **Needs a GUI eyeball** (open a
> PKGBUILD with one of the new patterns → the line is flagged in the viewer).


**Why:** ks-aur-scanner implements 115+ detection codes. Atlas has 14. We don't need 115
(many are Rust-specific deep analysis, IOC feeds, SARIF tooling — overkill for an advisory
GUI scanner), but there are clear gap categories where a few regex rules each would
meaningfully improve coverage. All stay pure pattern matchers in `pkgbuild_audit.py` — no
external tools, no network, no ML.

### New rules to add

**Reverse shells (WARN)** — ks-aur-scanner's SHELL-001 through SHELL-011. Atlas catches
`ncat`/`socat` under `network_cmd` but misses language-specific reverse shells.
- `reverse_shell_bash`: `/dev/tcp/` + `exec` redirect patterns (bash-native reverse shell)
- `reverse_shell_lang`: `socket.connect`, `IO.popen`, `TCPSocket`, `fsockopen` — Python/Ruby/
  Perl/PHP reverse-shell one-liners
- `reverse_shell_listener`: `nc -l`, `ncat -l`, `socat LISTEN` — listener setup

**Credential theft (WARN)** — ks-aur-scanner's CRED-001 through CRED-005. Atlas has
`sensitive_path` but it only covers `.ssh`, dotfiles, sudoers, crontab, autostart.
- `credential_harvest`: `/etc/shadow`, `.gnupg/`, `wallet`, `kwallet`, `gnome-keyring`,
  `login-keyring`, browser profile paths (`~/.mozilla`, `~/.config/chromium`,
  `~/.config/google-chrome`), `.netrc`
- `ssh_key_exfil`: `id_rsa`, `id_ed25519`, `id_ecdsa` combined with a network command or
  redirect (reading SSH keys alone is `sensitive_path`; *sending* them is the escalation)

**Persistence mechanisms (WARN/INFO)** — ks-aur-scanner's PERSIST-001 through PERSIST-006.
Atlas has `systemd_service_install` (enable/start) and `sensitive_path` (autostart) but
misses other persistence vectors.
- `systemd_timer_create` (WARN): `systemd/system/*.timer`, `systemd/user/*.timer` creation
  (timers are more covert than services — cron replacement, used by the 2018 xeactor miner)
- `cron_persist` (WARN): `crontab -`, `/etc/cron.d/`, `/var/spool/cron/` manipulation
- `rc_local` (WARN): `/etc/rc.local` writes or `rc-local.service` references
- `shell_function_inject` (WARN): `>>.*\.bashrc`, `>>.*\.zshrc`, `>>.*\.profile` (appending
  to shell configs — distinct from reading them, which `sensitive_path` covers)

**Obfuscation variants (WARN)** — ks-aur-scanner's OBF-001 through OBF-008. Atlas has
`base64`, `base64_blob`, `hex_escapes` but misses other encoding tricks.
- `printf_assembly` (WARN): `printf.*\\x` or `printf.*\\[0-9]{3}` chains — building strings
  from octal/hex escapes via printf (the cheap `eval $(printf ...)` trick)
- `gzip_payload` (INFO): `gzip -d` or `zcat` or `gunzip` piped into `sh`/`bash`/`eval` —
  compressed-payload execution
- `xxd_decode` (WARN): `xxd -r` — reverse hex dump, another encoding/decoding vector

**Dependency confusion (WARN)** — ks-aur-scanner's DEP-001. Not in Atlas at all.
- `dep_confusion` (WARN): `provides=` or `conflicts=` listing core system packages
  (`glibc`, `coreutils`, `systemd`, `pacman`, `bash`, `filesystem`, `linux`). A PKGBUILD
  that provides/conflicts with base packages is a takeover vector. Check against a hardcoded
  list of ~20 base/base-devel essentials.

**Weak integrity (INFO)** — ks-aur-scanner's CHK-001/CHK-005. Atlas only flags SKIP.
- `weak_checksum` (INFO): `md5sums=` or `sha1sums=` arrays — MD5/SHA1 are cryptographically
  broken; `sha256sums`/`sha512sums`/`b2sums` should be used instead
- `http_source` (INFO): `source=` entries with `http://` (not `https://`) — MITM risk on
  source downloads. Filter out localhost and `http://` inside `git+http` (git verifies via
  commit hash).

**Privilege escalation refinements (WARN)**
- `suid_capability` (WARN): `setcap` with dangerous capabilities (`cap_setuid`,
  `cap_net_raw`, `cap_sys_admin`, `cap_dac_override`) — capability-based privilege
  escalation, subtler than `chmod +s`
- `ld_preload` (WARN): `LD_PRELOAD=` or `/etc/ld.so.preload` writes — library injection
  for rootkits/keyloggers

### Implementation notes

- All rules are `(id, severity, why, matcher)` tuples appended to `_RULES` in
  `pkgbuild_audit.py`. No architecture change.
- Each rule needs at least one positive test case and one false-positive-safe test case in
  `test_pkgbuild_audit.py`.
- The `sensitive_path` rule stays — the new rules are more specific escalations
  (credential theft = sensitive_path + exfil; shell injection = sensitive_path + append).
  No rule merging needed; findings list tolerates overlap.
- Keep the disclaimer prominent — more rules doesn't mean "safe if clean."
- **Estimated: ~25 new rules, each a one-line regex. Low risk (additive, advisory-only,
  fail-open).**

---

## Theme 2: AUR comments in the detail view

**Why:** Pacsea shows AUR package comments directly in its detail view. Comments often
contain build-fix tips, security warnings from other users, and context about orphaned or
broken packages. Atlas already fetches AUR metadata via `aur_client.get_info` but doesn't
surface comments.

### Design

- **Backend:** New `AtlasApi.get_aur_comments(pkg_name)` — fetch the AUR package comments
  page (`https://aur.archlinux.org/packages/<pkgbase>/` or use the RPC if it exposes
  comments — it doesn't, so scrape the HTML comments section from the web page). Return a
  list of `{author, date, body}` (newest first, capped at 20). **Fail-open** (any error →
  empty list, never blocks). Cache per session (comments don't change mid-session).
- **Frontend:** A "Comments" section in the AUR detail modal (below Dependencies, above
  the info table). Lazy-loaded on first expand (accordion, like the dep tree). Each comment:
  author + relative timestamp + body (markdown-rendered with sanitization — AUR comments
  can contain markdown). Linkify URLs via `safeExternalUrl`.
- **Scope:** AUR packages only. Repo/Flatpak/AppImage get no comments section.

### Gotchas

- AUR has no comments API — the web page must be scraped. Use `requests` +
  `html.parser` (stdlib), not beautifulsoup (no new deps). Parse the `#comments` section
  of `https://aur.archlinux.org/packages/<pkgbase>/`.
- Rate-limit: one fetch per package per session, cached. No burst risk.
- HTML sanitization: strip all tags except basic formatting (`<a>`, `<code>`, `<em>`,
  `<strong>`, `<p>`). Don't trust comment content — it's user-generated.

---

## Theme 3: Auth readiness check before long operations

**Why:** Pacsea implements "auth readiness checks" that evaluate whether the sudo credential
cache will survive a long operation. A multi-package AUR chroot build can take 30+ minutes;
if sudo times out mid-build, the operation fails partway through — a real pain point. Atlas
currently just prompts for the root password upfront but doesn't warn about timeout risk.

### Design

- **Backend:** New `AtlasApi.check_auth_readiness()` or integrate into the transaction
  preview for AUR/multi-package operations. Check `sudo -n true` (returns 0 if cached, 1 if
  not) and, if available, parse `timestamp_timeout` from `sudo -l` output to estimate
  remaining time. Return `{cached: bool, timeout_minutes: int|None}`.
- **Frontend:** When the transaction preview shows a multi-package AUR install or an
  Update-All with AUR packages, and the estimated build time is long (>1 AUR package with
  chroot enabled, or >3 AUR packages without), show an advisory note:
  "This may take a while — ensure your sudo session won't time out" with a suggestion to
  run `sudo -v` in a terminal or configure `timestamp_timeout` in sudoers.
- **Scope:** Advisory only. Never auto-modify sudoers. Never block the operation.

---

## Theme 4: AUR client rate-limit delay

**Why:** arch-toolkit uses a 200ms minimum inter-request delay with exponential backoff for
AUR RPC calls. Atlas has basic retry (2 attempts, 0.5s backoff) but no inter-request delay.
During `get_update_risk_tiers` (batch AUR info for Update-All), Atlas makes one batched RPC
call (good), but other flows that make sequential AUR calls (e.g. resolving deps) could
benefit from a small delay to avoid hitting AUR rate limits.

### Design

- Add a `_last_request_time` timestamp to `AURClient` and a minimum delay (150ms) between
  consecutive requests. Use `time.monotonic()` + `time.sleep(delta)` in the request path.
- Keep it simple — no token bucket, no sliding window. The AUR RPC is not high-throughput;
  a flat delay is sufficient.
- Doesn't affect the batched `get_info` call (already one request for multiple packages).

---

## Theme 5: Package queue across views (exploratory)

**Why:** Pacsea has a persistent package queue — users can browse, search, and queue packages
across multiple views, then review and install the full queue in one shot. Atlas has Select
mode but it's per-view (switching views clears the selection).

### Design (sketch — needs its own plan if picked up)

- A persistent `installQueue` array in the frontend (localStorage-backed).
- An "Add to queue" action on package cards (alongside Install/Uninstall).
- A "Queue (N)" badge in the sidebar or topbar.
- A queue review page or modal: the full list with Remove buttons and a "Install all" action
  that routes each through the transaction preview.
- **Open question:** does batch-queued install go through one aggregate preview (like
  Update-All) or individual previews? Aggregate is better UX but harder to assemble for
  mixed sources.

**Status:** Exploratory. Lower priority than Themes 1-4. Write a dedicated plan before
implementing.

---

## Theme 6: Fuzzy search for packages

**Why:** Pacsea offers fuzzy matching for package search. Atlas uses exact substring
matching. The command palette already has `fuzzyScore` — reusing it for package search
would improve discovery (typo tolerance, partial matches).

### Design (sketch)

- When a local search (`filterPackages` in main.js) returns 0 exact hits, fall back to
  `fuzzyScore`-ranked results from the same package list.
- For remote search (AUR RPC), the RPC already does its own matching — no change needed
  server-side. But client-side re-ranking of RPC results by fuzzy relevance could improve
  ordering.
- **Risk:** Fuzzy results can feel random if the scoring is too loose. Threshold carefully.

**Status:** Exploratory. Low effort if scoped to client-side re-ranking only.

---

## Priority order

| # | Theme | Effort | Value | Risk |
|---|-------|--------|-------|------|
| 1 | ✅ Expand PKGBUILD audit rules (14→31, shipped) | Medium | High — closes the biggest gap vs. ks-aur-scanner | Low (additive, advisory) |
| 2 | AUR comments in detail view | Medium | High — unique context for trust decisions | Low (fail-open, cached) |
| 3 | Auth readiness check | Small | Medium — prevents a real pain point | Low (advisory only) |
| 4 | AUR client rate-limit delay | Small | Medium — correctness/politeness | Low |
| 5 | Package queue (exploratory) | Large | Medium — convenience, not safety | Medium (UX complexity) |
| 6 | Fuzzy search (exploratory) | Small | Low-medium — nice-to-have | Low |

Themes 1-4 are concrete and ready to implement. Themes 5-6 are sketches that need their own
plans if picked up.

---

## What we're NOT adopting (and why)

- **External scanner integration (ClamAV, Trivy, ShellCheck, VirusTotal, Semgrep):**
  ks-aur-scanner and Pacsea both integrate external binaries. Atlas's advisory scanner is
  pure-Python, no external deps, runs offline, and is tuned for PKGBUILD/install-script
  patterns. Adding external tool dependencies would increase install complexity, require
  those tools to be installed, and shift the scanner from "always available" to "optional if
  you install 5 extra tools." The regex rules cover the same *pattern categories*; the
  external tools add depth (ML models, vulnerability databases) that's valuable in a
  dedicated security tool but overkill for an advisory GUI badge.
- **IOC database / known-malicious hash feeds:** ks-aur-scanner maintains an embedded IOC
  database. Atlas's approach is pattern-based (campaign-specific rules like `npm_install_unknown`
  and `temp_upload_service` for Atomic Arch). Adding a feed would need a data pipeline and
  freshness mechanism. If a major new campaign hits, we add a targeted rule (like we did for
  Atomic Arch) — cheaper and more transparent.
- **SARIF output:** Useful for CI integration, irrelevant for a GUI app. The CLI could add
  `--format json` someday but it's not a priority.
- **Rust rewrite / hybrid:** Per the conversation — Atlas stays pure Python. The three
  projects validate that the *features* are right; the implementation language is not a gap.
- **Distro-aware updates (Manjaro/EndeavourOS/CachyOS):** Pacsea supports these. Atlas is
  Arch-focused (AGENTS.md §3.1). These derivatives have their own package managers and
  repos with different update cadences — supporting them properly is a large surface area
  for an "off by default" audience.
- **LLM-based auditing:** Pacsea integrates `aur-sleuth` for LLM-based PKGBUILD analysis.
  Non-goal per BACKLOG (AI recommendations are "easy to make cringe, slow, and
  untrustworthy"). A regex scanner that says "here are lines worth a look" is more honest
  than an LLM that says "this package is safe."
