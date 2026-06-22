# AUR Security Heuristics — Integration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Mine the ks-aur-scanner and aur-audit projects for what Atlas doesn't already have, fill the dependency-tree visualization gap, and stay ahead of the June 2026 AUR threat landscape.

**Architecture:** Atlas already has 80% of what these tools offer — a 742-line audit engine with 30+ rules, annotated PKGBUILD diff view, severity badges, and warning aggregation. This plan covers the remaining 20%: (1) new detection rules from the post-June-2026 incident analysis, (2) an IOC database for known-malicious artifacts, (3) a dependency-tree visualizer for the transaction preview modal, and (4) a rule-health dashboard that makes precision drift visible.

**Tech Stack:** Python 3.11+ (Atlas backend), JavaScript/WebKit (Atlas GUI), stdlib `difflib` (existing), `json` (rules pack format), HTML/CSS (tree viz).

---

## What Atlas Already Has

| Capability | ks-aur-scanner | aur-audit | Atlas |
|-----------|---------------|-----------|-------|
| PKGBUILD regex scanning | 110+ rules | 6 rules | **30 rules** ✅ |
| Annotated diff (what changed + what's suspicious) | ❌ | ❌ | **Yes** ✅ |
| Severity badges (warn/info → red/amber) | ❌ | ❌ | **Yes** ✅ |
| .SRCINFO↔PKGBUILD divergence detection | ❌ | ❌ | **Yes** ✅ |
| Structural checks (network in package(), unchecksummed source) | Partial | ❌ | **Yes** ✅ |
| External rules pack (JSON, no release needed) | ❌ | ❌ | **Yes** ✅ |
| Live precision-drift monitoring (audit_rescan) | ❌ | ❌ | **Yes** ✅ |
| Dependency tree visualization | ❌ | ❌ | **No** ❌ |
| IOC database (known-malicious hashes/URLs) | `aur-scan ioc` | ❌ | **No** ❌ |
| RSS feed monitor (recently-updated packages) | ❌ | `aur-monitor.clj` | **No** |
| TOCTOU-safe install workflow | `aur-scan install` | ❌ | **No** |
| VirusTotal/URLhaus integration | Opt-in | ❌ | **No** |
| SBOM (CycloneDX) output | Yes | ❌ | **No** |

---

## Licensing Compatibility

| Project | License | Rule of Thumb |
|---------|---------|---------------|
| **ks-aur-scanner** | GPL-3.0 | Cannot copy code. Can independently implement the *ideas* and *regex patterns* (functional, not copyrightable). Atlas already does this — see `_KS_AUR_SOURCE` provenance tags. |
| **aur-audit** | MIT | Fully compatible. Can reference directly, adapt patterns. |
| **lenucksi/aur-malware-check** | Shell scripts (unlicensed, community collection) | Use as reference for IOC data only, not code. |

**What Atlas already borrowed (correctly):** Atlas audited ks-aur-scanner's rule categories on 2026-06-16 and independently implemented 17 evergreen rules using standard Python `re` — reverse shells, credential harvest, persistence, obfuscation, dependency confusion, weak integrity. Each rule carries a `source: 'ks-aur-scanner rule categories (mapped to MITRE ATT&CK techniques)'` provenance tag. This is the right approach — idea attribution, independent implementation, no GPL contamination.

---

## Tasks

### Task 1: Add IOC Database (Known-Malicious Artifacts)

**Objective:** Ship a `data/malware_ioc.json` with known-bad AUR package names, npm/bun package names, file artifacts, and C2 domains from the June 2026 Atomic Arch campaign. Wire it into the existing `scan()` pipeline as an additional checker that flags known-IOC matches with higher severity.

**Files:**
- Create: `atlas/gems/arch/data/malware_ioc.json`
- Modify: `atlas/gems/arch/pkgbuild_audit.py` (add IOC checker to scan)
- Modify: `atlas/gems/arch/__init__.py` (load IOC data at startup)
- Test: `tests/gems/arch/test_pkgbuild_audit_ioc.py`

**Sources for IOC data:**
- `lenucksi/aur-malware-check/blob/master/package_list.txt` (~1,600 compromised package names)
- ks-aur-scanner's IOC database (approach: read their `data/` directory, extract unique patterns)
- aur-audit's detection rules (OBF-01, EXEC-01, PERS-01, ENV-01, WRITE-01 — adapt as new rules)

**Step 1: Create the IOC schema**

```json
{
  "version": 1,
  "updated": "2026-06-21",
  "description": "Known-malicious indicators from the June 2026 Atomic Arch AUR supply-chain campaign",
  "source": "Community research (lenucksi/aur-malware-check), ks-aur-scanner IOC database",
  "entries": {
    "aur_packages": ["compromised-package-1", "compromised-package-2"],
    "npm_packages": ["atomic-lockfile", "lockfile-js"],
    "bun_packages": ["js-digest"],
    "file_artifacts": ["scales.bpf.c", "/tmp/.atomic-arch-backdoor"],
    "c2_domains": ["example-c2.malicious.com"],
    "attack_accounts": ["krisztinavarga", "franziskaweber", "tobiaswesterburg", "ellenmyklebust", "custodiatovar", "veramagalhaes"]
  }
}
```

**Step 2: Implement IOC scanner function**

```python
# In pkgbuild_audit.py
IOC_RULE_ID = 'known_ioc'
IOC_SEVERITY = WARN

def _load_ioc_data(path: str = None) -> Dict:
    """Load the malware IOC database. Falls back to bundled data/ if path is None."""
    import json, os
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'data', 'malware_ioc.json')
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {'entries': {}}

def _check_ioc(text: str, ioc_data: Dict) -> List[Dict]:
    """Flag lines that match known-malicious indicators from the IOC database."""
    entries = ioc_data.get('entries', {})
    patterns = []
    for category, values in entries.items():
        for val in values:
            if isinstance(val, str):
                patterns.append((category, re.escape(val)))
    
    findings = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        for category, pattern in patterns:
            if re.search(pattern, raw, re.I):
                findings.append({
                    'line_no': idx, 'line': stripped,
                    'rule': IOC_RULE_ID, 'severity': IOC_SEVERITY,
                    'why': f'Known-malicious indicator ({category}): matches "{pattern}" from the June 2026 campaign',
                    'meta': {'kind': CAMPAIGN, 'added': '2026-06', 'source': _ATOMIC_ARCH_SOURCE}
                })
    return findings
```

**Step 3: Wire IOC check into `scan()`**

Add after structural checks:

```python
# IOC check (if data loaded)
if _ioc_data:
    findings.extend(_check_ioc(text, _ioc_data))
```

**Step 4: Write failing test**

```python
def test_ioc_flags_atomic_lockfile():
    text = 'npm install atomic-lockfile --save-dev'
    findings = scan(text)
    ioc = [f for f in findings if f['rule'] == 'known_ioc']
    assert len(ioc) == 1
    assert ioc[0]['severity'] == 'warn'

def test_ioc_ignores_normal_npm():
    text = 'npm install typescript --save-dev'
    findings = scan(text)
    ioc = [f for f in findings if f['rule'] == 'known_ioc']
    assert len(ioc) == 0
```

**Step 5: Run test, implement, commit**

---

### Task 2: Add aur-audit Detection Rules (Post-Incident Patterns)

**Objective:** Adapt the 6 detection categories from aur-audit that Atlas doesn't already cover. aur-audit is MIT-licensed — patterns are clean to adapt.

**Files:**
- Modify: `atlas/gems/arch/pkgbuild_audit.py` (new rules in `_RULES`)
- Test: `tests/gems/arch/test_pkgbuild_audit.py` (add corpus entries)

**New rules to add:**

| Rule ID | aur-audit | Pattern | Severity |
|---------|-----------|---------|----------|
| `pipe_eval_remote` | EXEC-01 | `sh <(curl)` / `bash <(wget -qO-)` | WARN |
| `systemd_unit_install` | PERS-01 | Writing a `.service`/`.timer` to `/usr/lib/systemd` in an install hook | WARN |
| `shell_rc_write` | ENV-01 | Appending to `.bashrc`/`.zshrc`/`/etc/profile` (Atlas has `shell_function_inject` for `>>` — extend to `echo ... >`) | WARN |
| `host_tamper` | WRITE-01 | Writing outside `$pkgdir`/`$srcdir` to absolute system paths | WARN |

**Step 1: Write the regex rules**

```python
# In _RULES list:
('pipe_eval_remote', WARN,
 'Pipes a remote URL into a shell via process substitution — runs remote code unconditionally '
 '(the Atomic Arch delivery mechanism).',
 re.compile(r'(?:ba|z|da|k)?sh\s+<\s*\(\s*(?:curl|wget)', re.I).search),

('systemd_unit_install', WARN,
 'Writes a systemd .service or .timer unit file during install — install hooks with root '
 'privileges can create persistent services.',
 re.compile(r'install\s+-Dm\S+\s+\S+\s+(?:/etc/systemd/system|/usr/lib/systemd/(?:system|user))/[^\\s]+\\.(?:service|timer)\\b').search),

('shell_rc_write', WARN,
 'Writes to a shell init file (.bashrc, .zshrc, .profile, /etc/profile) — injecting code '
 'that runs on every shell start.',
 re.compile(r'(?:>|>>|tee\\s+-a|c\\bat\\b)\\s*["\\']?\\S*\\.(?:bashrc|zshrc|bash_profile|profile)\\b').search),

('host_tamper', WARN,
 'Writes to an absolute system path outside the build/install directories — '
 'package installs should confine writes to $pkgdir.',
 re.compile(r'\\b(?:install|cp|mv)\\s+[^/]*\\s+(/(?:usr|etc|var|opt|boot)/[^\\s]+)').search),
```

**Step 2: Add corpus test cases** (append to `tests/gems/arch/audit_corpus/`)

**Step 3: Verify existing rules don't break** — run `pytest tests/gems/arch/test_pkgbuild_audit_corpus.py -v`

**Step 4: Commit**

---

### Task 3: Dependency Tree Visualizer

**Objective:** The one clear gap Atlas has vs. ks-aur-scanner. When a user is about to install a package, show a visual tree of all AUR dependencies that will be pulled in, color-coded by safety signals. This replaces the current flat list with a scannable visual.

**Files:**
- Modify: `atlas/view/webview/api.py` → add `get_dependency_tree(pkg_id)` endpoint
- Modify: `atlas/view/webview/main.js` → tree renderer in the confirm modal
- Modify: `atlas/view/webview/style.css` → tree visual styles

**Design:**

```
┌─────────────────────────────────────────────┐
│  Installing: firefox-patch-bin               │
│                                              │
│  Dependencies (5 total, 2 AUR):              │
│                                              │
│  firefox-patch-bin  ⬇                       │
│  ├── gtk3  [repo]  ✅                        │
│  ├── libx11  [repo]  ✅                      │
│  ├── nodejs  [repo]  ✅                      │
│  ├── atomic-lockfile  [AUR]  ⚠️  ORPHANED   │
│  │   └── npm  [repo]  ✅                     │
│  └── electron-bin  [AUR]  ℹ️  OUTDATED      │
│                                              │
│  ⚠️ 1 warning ·  ℹ️ 1 notice                │
└─────────────────────────────────────────────┘
```

Each node shows: package name, source (repo/AUR/Flatpak), and any active warning signal (orphaned/maintainer change/out of date/security finding). Color:
- Green = official repo, no warnings
- Amber = AUR, no warnings (community-maintained, but Atlas has scanned it)
- Red = AUR with active warnings (orphaned, flagged, or audit findings)

**Step 1: Backend — `get_dependency_tree()` endpoint**

Add to `api.py`:

```python
def get_dependency_tree(self, pkg_id: str) -> dict:
    """Resolve the dependency tree for a package (what will be installed if you build this).
    
    Returns {status, data: {root, nodes: [{name, source, warnings, children:[name...]}]}}
    Depth-limited to 3 levels to keep the tree manageable. Fails open — partial results
    are better than blocking the install."""
```

Reuse existing `get_transaction_summary()` infrastructure which already computes deps and warnings per package.

**Step 2: Frontend — tree renderer**

In `main.js`, add a `renderDependencyTree(data)` function that:
1. Builds an indented tree with SVG connecting lines
2. Colors each node by source + warning status
3. Shows warning icons inline
4. Collapses sub-trees > 10 deps with a "show all" toggle

**Step 3: Wire into the confirm modal**

Replace the flat dependency list in the transaction preview confirm modal with the tree view when installing an AUR package with > 2 dependencies.

**Step 4: Style it**

```css
.dep-tree { font-family: monospace; line-height: 1.6; }
.dep-tree-node { padding: 2px 0; }
.dep-tree-node.repo { color: var(--color-success); }
.dep-tree-node.aur-clean { color: var(--color-text); }
.dep-tree-node.aur-warn { color: var(--status-warning); }
.dep-tree-node.aur-danger { color: var(--status-danger); }
.dep-tree-indent { display: inline-block; width: 1.5em; color: var(--color-muted); }
```

**Step 5: Test, commit**

---

### Task 4: Rule-Health Dashboard (Precision Drift Monitoring)

**Objective:** Atlas already has `audit_rescan.py` for batch rule-health checking, but it's CLI-only. Surface it in the GUI as part of the System Health page so power users can see which rules are noisy and which never fire.

**Files:**
- Modify: `atlas/view/webview/api.py` → expose `run_audit_rescan()` endpoint
- Modify: `atlas/view/webview/main.js` → health page UI
- Modify: `atlas/view/webview/index.html` → new section in system health

**Step 1: API endpoint**

```python
def run_audit_rescan(self, sample_size: int = 100) -> dict:
    """Sample `sample_size` live AUR PKGBUILDs and report per-rule fire rates.
    Runs in a background thread to avoid blocking the GUI. Returns {status, data: {report}}"""
```

**Step 2: System Health UI**

Add a "PKGBUILD Audit Rules" section showing:
- Rules with >50% fire rate (potential false positives)
- Rules that never fired (candidate for review/removal)
- A sparkline of rule counts over time (if we have previous scan data cached)

**Step 3: Commit**

---

### Task 5: TOCTOU-Safe Install (Race-Free Build)

**Objective:** ks-aur-scanner's `aur-scan install` has a race-free mode: fetch PKGBUILD once, scan those exact bytes, then build from the same directory. Atlas currently fetches, shows the diff, then the user clicks "build" — but paru re-clones, meaning a package maintainer could swap the PKGBUILD between review and build. Low-probability but real.

**Files:**
- Modify: `atlas/gems/arch/worker.py` → add `fetch_once=True` mode
- Modify: `atlas/view/webview/api.py` → `get_pkgbuild` already fetches; pass the cached copy to the build
- Modify: `atlas/view/core/controller.py` → wire race-free flow

**Step 1: Cache the reviewed PKGBUILD**

When the user opens the PKGBUILD review modal, `get_pkgbuild` already fetches the text. Cache it in a temp `.pkgbuild_reviewed` file keyed by package name.

**Step 2: Build from reviewed copy**

When the user clicks "build," instead of running `paru -S pkg`, run `makepkg -si` from the cached directory that the user already reviewed.

**Step 3: Add a lockfile-style check**

Before `makepkg -si`, re-check that the local directory's PKGBUILD hasn't been modified since the review. If it has, show a warning and re-scan.

**Step 4: Commit**

---

## Task Ordering & Dependencies

```
Task 1 (IOC DB) ───── independent
Task 2 (aur-audit rules) ─ independent, can run parallel
Task 3 (Dependency tree) ─ depends on nothing, highest user-visible impact
Task 4 (Rule-health dashboard) ─ depends on audit_rescan existing, independent otherwise
Task 5 (TOCTOU-safe) ─ depends on caching reviewed PKGBUILD, independent otherwise
```

**Recommended order:** 3 → 1 → 2 → 5 → 4 (highest user-visible impact first)

Task 3 (dependency tree viz) is the one thing Atlas demonstrably doesn't do that ks-aur-scanner does — and Atlas can do it *better* because it has a GUI.

---

## What NOT to Do

- **Don't copy GPL code from ks-aur-scanner.** Rules are independently implemented with source attribution.
- **Don't add VirusTotal integration yet.** The upstream opt-in model is right — Atlas should stay offline-first.
- **Don't add the RSS feed monitor yet.** It's a separate concern (monitoring → alerting) that doesn't fit the install-time safety model.
- **Don't expose a "safe" badge.** The existing disclaimer approach is correct — Atlas surfaces warnings, never certifies safety.
- **Don't break the existing scan pipeline.** All new rules are additive.

---

## Verification

After Task 2: `pytest tests/gems/arch/ -v` — all audit tests pass, new corpus entries hit
After Task 3: Manual GUI test — install an AUR package with 3+ deps, verify tree renders in confirm modal
After Task 5: Manual GUI test — open PKGBUILD review, build, verify it used the reviewed copy
