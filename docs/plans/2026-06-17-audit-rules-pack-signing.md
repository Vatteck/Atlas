# Audit rules-pack: signing scheme for remote packs (design)

**Date:** 2026-06-17
**Status:** ✅ Designed, **deliberately NOT built (deferred indefinitely, 2026-06-17).** Decision: the
permanent maintenance cost of a remote signed feed (crypto dep, key rotation/revocation, signing
tooling + CI, a supply-chain surface to own forever) isn't worth it for an *advisory* scanner on a
**solo-dev side project**, especially since Atlas ships as a fast-updating `-git` AUR package (new
bundled rules already reach users on a normal `yay -Syu`). The local fail-closed loader (step 1, shipped)
covers the real need. **This doc is the record of how to do it safely *if the need ever arises*** — e.g.
if Atlas moves to a slow-release channel (stable AUR pkg, Flatpak, distro packaging). If revisited, the
recommended library is **PyNaCl behind a `verify_pack()` seam** ("don't roll your own crypto" beats
dependency purity for an authenticity check). Step 2 of
[2026-06-17-audit-rules-pack.md](2026-06-17-audit-rules-pack.md) (step 1, the local loader, shipped).

## 1. Threat model — what signing actually buys

A remote rules-pack means Atlas loads rule *data* fetched from `atlas-files` (GitHub raw). Without
authentication, anyone who can write to that repo (account compromise, a bad merge, GitHub
compromise) or interpose on the channel can change what the scanner does. **What's already bounded by
step 1** (don't re-solve): packs are *additive* (can't remove/disable a bundled rule), *regex-only*
(no code execution), and *fail-closed* (any problem → bundled-only). So the residual blast radius of a
hostile feed is narrow:

| Attack via a hostile feed | Bounded by | Residual risk |
|---|---|---|
| Disable existing detection | step-1 additive-only | none (can't remove bundled rules) |
| Execute code (RCE) | step-1 regex-only + strict validation | none |
| **Inject misleading findings / social-eng text** | — | **yes** (false WARNs, scary `why` text → erodes trust) |
| **Suppress a *future* external rule by replay/rollback** | — | **yes** (serve an old signed pack) |
| **ReDoS** (hang the advisory scan) | small input + per-line try/except | low, but real |

Signing closes the first two residuals by authenticating the **author** (the holder of the Atlas
signing key), independent of the transport. HTTPS authenticates `raw.githubusercontent.com`, *not*
who wrote the bytes — signing does. Rollback/ReDoS are handled by §5 and §9.

**Design principle:** signing *raises* the trust of a remote pack to "produced by the Atlas
maintainer," but it does **not** bypass step-1 validation. A signed pack still runs through
`load_rule_pack` (regex-only, no bundled-id shadowing, length caps). Defense in depth: a key
compromise still can't inject a non-regex rule or shadow `eval`.

## 2. Trust anchor — bundled public key(s)

- The **public** key(s) are **bundled in the app** (`atlas/gems/arch/audit_pack_keys.py` as a constant
  list), shipped with the code. This is the root of trust: changing the bundled key requires a normal
  app release (the existing, separately-trusted channel). The private key never touches any repo.
- Support a **list** of trusted keys, each with a `key_id` = first 16 hex chars of
  `sha256(raw_pubkey)`. This enables:
  - **Rotation without a flag day:** sign with the new key, ship an app release trusting *both* old +
    new, let it propagate, then drop the old key in a later release.
  - **Revocation:** a compromised key is removed from the bundled list in an app release; until the
    user updates, fail-closed keeps them on bundled rules + last-good verified pack (no worse than
    today). There is no online revocation (an offline-first app can't depend on a CRL).

## 3. What is signed + signature envelope

**Sign the exact bytes of the distributed file** — never a re-canonicalized form (canonicalization
bugs are a classic signature-bypass). Verify-then-parse: verify the downloaded bytes, *then*
`json.loads`.

- `arch/audit_rules.json` — the pack. Top-level gains signed anti-rollback fields:
  ```json
  { "schema": 1, "serial": 7, "issued": "2026-06-17T00:00:00Z",
    "expires": "2026-12-17T00:00:00Z", "rules": [ … step-1 rule objects … ] }
  ```
- `arch/audit_rules.json.sig` — a tiny detached-signature envelope (its own bytes are *not* signed):
  ```json
  { "alg": "ed25519", "key_id": "ab12…", "sig": "<base64 signature over audit_rules.json bytes>" }
  ```

Ed25519 is the algorithm: small (32-byte key, 64-byte sig), fast, misuse-resistant, no parameter
choices. (Final library choice is the open decision in §7.)

## 4. Verification flow (fail-closed, verify-then-parse)

On refresh (startup + periodic, mirroring the `categories.txt` downloader):

1. Fetch `audit_rules.json` **bytes** and `audit_rules.json.sig` over HTTPS into a temp location.
2. Parse the `.sig` envelope. `alg == "ed25519"`; look up `key_id` in the **bundled** trust set →
   unknown key ⇒ **reject**.
3. **Verify** the Ed25519 signature over the *exact downloaded bytes* with that public key → fail ⇒
   **reject**.
4. `json.loads` the now-trusted bytes; check `schema` is known.
5. **Anti-rollback:** `serial` ≥ the highest serial we've ever accepted (persisted in cache) → a lower
   serial ⇒ **reject** (replay/downgrade). **Expiry:** `now ≤ expires` → expired ⇒ ignore remote
   (degrade to bundled + last-good), don't hard-fail. Generous window (≈6 months) so long-offline
   users aren't cut off abruptly; expiry only forces a refresh, never breaks the app.
6. **Defense in depth:** run the rules through the step-1 `load_rule_pack` validator. Any rule that
   fails (non-regex, bundled-id collision, over-length, bad flags) is dropped exactly as for a local
   pack.
7. **Persist only on full success:** write the verified bytes + new serial to cache atomically. The
   *loaded* remote pack is always the last fully-verified one; a failed/again-unreachable fetch keeps
   the last-good cached pack. Never load unverified bytes.

Precedence at scan time: **bundled rules (always)** + **verified remote pack** (if any) + the existing
**local `$CONFIG/arch/audit_rules.json`** (user's own machine, unsigned by design — local trust).
Remote and local stay distinct sources; only remote requires a signature.

## 5. Anti-rollback & freshness — summary
`serial` (monotonic, signed) gives downgrade protection; `issued`/`expires` (signed) bound staleness.
Both live *inside* the signed bytes, so they can't be tampered without breaking the signature. Cache
remembers the highest accepted `serial`.

## 6. Distribution & caching
Mirror the existing category pattern: `URL_AUDIT_RULES = …/atlas-files/main/arch/audit_rules.json`
(+ `.sig`), cached under `$CACHE/arch/audit_rules.remote.json` (+ a small `…serial` marker). Fetch is
best-effort and throttled like other AUR/files traffic; all failures degrade to bundled + last-good.

## 7. OPEN DECISION — Ed25519 verification library

Atlas declares **no** crypto dependency today and is proudly pure-Python/offline. Verification (not
signing) happens in-app on a 64-byte signature — the options trade dependency footprint against
"don't roll your own crypto":

- **PyNaCl** (libsodium / C): mature, audited, 3-line verify. Adds one declared C-extension dep.
- **cryptography** (pyca): modern, already transitively present here — *but its internals are Rust
  now*, which sits awkwardly with Atlas's "no Rust" ethos (it's a dep, not our code, but optically
  loud). Adds a declared dep.
- **Vendored pure-Python Ed25519 *verify-only*** (~100 lines, ref impl): zero new dep, fits the
  pure-Python ethos perfectly; downside is shipping vendored crypto (verify-only, public algorithm,
  but still our responsibility to keep correct).
- **Shell out to `minisign`/`gpg`**: purpose-built, but a runtime *binary* dep; gpg needs our pubkey
  in a keyring (clunky). `minisign`'s format is a clean fit if a binary dep is acceptable.

Recommendation: **PyNaCl** (audited, C-not-Rust, tiny verify) unless you want zero new deps, in which
case the vendored verify-only impl. This is the blocker for implementing the verifier. **(Moot while
the feature is deferred — see Status.)**

## 8. Signing tool (maintainer side, in atlas-files / a tools script)
A script that: validates every rule (reuses `load_rule_pack` **plus a ReDoS/timeout check**, §9),
bumps `serial`, sets `issued`/`expires`, signs the file bytes with the **offline private key**, and
writes the `.sig`. The private key lives offline / in a secrets store — never in any repo or CI by
default. (If CI signing is ever wanted, that's a separate trust decision.)

## 9. ReDoS hardening
Signing restricts authorship to the trusted maintainer, so the realistic ReDoS risk becomes "the
maintainer ships a catastrophic-backtracking regex by accident." Mitigate primarily at **sign time**:
the signing tool runs each pattern against a corpus under a wall-clock **timeout** and refuses to sign
a slow rule. Runtime keeps the step-1 defenses (length cap, tiny input, per-line try/except). If we
want a runtime guarantee too, adopt the `regex` module with a `timeout=` for *external* rules only —
deferred unless the sign-time check is deemed insufficient.

## 10. Failure-mode table (all degrade safely)
| Condition | Result |
|---|---|
| No network / fetch fails | last-good cached remote pack, else bundled |
| `.sig` missing / wrong alg / unknown key_id | reject remote; bundled + last-good |
| Signature invalid | reject remote; bundled + last-good |
| `serial` < highest accepted | reject (rollback) |
| Expired | ignore remote (bundled + last-good); forces refresh |
| Individual rule invalid | that rule dropped (step-1 validator); rest load |
| Bundled key later revoked (app update) | key removed; affected packs no longer load |

## 11. Implementation steps (once §7 is decided)
1. `audit_pack_keys.py` (bundled pubkey list + `key_id`) + a `verify_pack(bytes, sig_obj)` in a new
   `audit_pack_verify.py` (pure, unit-tested with a throwaway test keypair).
2. Extend the cache/fetch layer (new `AuditRulesDownloader` mirroring the category downloader) +
   anti-rollback serial persistence; wire verified load into `pkgbuild_audit.register_rule_pack`.
3. The maintainer signing tool + a CI check that every committed pack verifies and passes the
   ReDoS/timeout corpus.
4. Ship the first signed pack in `atlas-files`.

## Non-goals
- Online revocation / CRL (offline app); revocation is via app release.
- Signing the `.sig` envelope itself (it carries only the signature + key id; integrity comes from the
  signature it transports).
- Encrypting the pack (it's public advisory data — we need *authenticity*, not confidentiality).
