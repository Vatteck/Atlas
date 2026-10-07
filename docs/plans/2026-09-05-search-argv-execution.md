# Pass the search query as argv, not shell text (2026-09-05)

## Problem

`atlas/gems/arch/pacman.py:search()` builds a shell command line from the user's search box:

```python
def search(words: str) -> Dict[str, dict]:
    output = run_cmd('pacman -Ss ' + words, print_error=False)
```

`run_cmd` (`atlas/commons/system.py`) passes that string to `subprocess.run` with
`shell=True`, so the query is parsed by `/bin/sh`.

The only thing standing between the GUI search box and the shell is
`sanitize_command_input` (`atlas/commons/util.py:97`), a **denylist**: it truncates at
`|` and `&`, strips `[' " % $ # * < >]` and leading `-flags`, and collapses whitespace.

**This is not a theoretical weakness — it is an exploitable injection.** Verified on
2026-09-05 against the current tree:

- `sanitize_command_input('firefox; touch /tmp/pwned')` returns the string unchanged —
  `;` is not in the denylist. Backticks, newlines (collapsed to spaces, still separate
  words), and parentheses also survive.
- Calling `pacman.search()` with that sanitized query **created the file**. Search runs
  as the desktop user, not root, but this is arbitrary command execution reachable from
  the Search field, and the Arch repos gem is on by default.

Auditing and patching the denylist is the wrong fix. The query should never reach a shell
parser at all.

## Approach

Argument-list execution — the pattern already used elsewhere in `pacman.py`, e.g.
`map_desktop_files` (`pacman.py:223`) calls `new_subprocess(['pacman', '-Ql', *pkgnames])`.

1. **`run_cmd` accepts a sequence.** `cmd` becomes `Union[str, Sequence[str]]`. A string
   keeps today's `shell=True` behaviour (every other caller is unaffected); a sequence
   sets `shell=False` and is handed to `subprocess.run` as argv. The `custom_user`
   wrapper builds `['runuser', '-u', user, '--', *cmd]` instead of interpolating.
   This mirrors `new_subprocess`, which already carries a `shell` flag.
2. **`pacman.search` splits the query into argv:** `run_cmd(['pacman', '-Ss', *words.split()])`.

### Why splitting preserves search semantics

Verified against real pacman on this box, not assumed:

- `pacman -Ss firefox` → many hits.
- `pacman -Ss firefox esr` → the AND of both regexes (only `firefox-esr-bin`), strictly
  narrower.

That is exactly what `shell=True` produced, because the shell was word-splitting the
query on whitespace before pacman ever saw it. `sanitize_command_input` already collapses
runs of whitespace to single spaces, so `split()` yields the same terms. Empty query:
today `'pacman -Ss '` and after the change `['pacman', '-Ss']` are the same argv — no
behaviour change (and `GenericSoftwareManager.search` already guards on a non-empty
query).

Return-code handling is untouched: `pacman -Ss` exits 1 on no match, `run_cmd`'s
`expected_code=0` turns that into `None`, and `search()` returns `{}`.

## Not in scope

`sanitize_command_input` **stays**. This is defence in depth: argv execution makes shell
metacharacters inert, and the sanitizer keeps stripping `-flags` so a query cannot turn
into a pacman option. Removing it would let `-Qi` etc. through as an argv element.

## Other `run_cmd` callers (audit)

Reported, not fixed here — see STATUS.md "Known gaps".

- **`flatpak.search` (`atlas/gems/flatpak/flatpak.py:366`)** —
  `run_cmd(f'flatpak search {word} --{installation}')`. This is the **same GUI query,
  same severity**, on a first-class source that is on by default. Left alone only because
  it is outside this change's stated scope; it should be converted next.
- **Package-name interpolation** (`get_information`, `guess_repository`,
  `find_one_match`, `get_version_for_not_installed`, `map_repositories`, `map_owners`,
  `list_and_map_installed`, …): names come from pacman/AUR output rather than the search
  box, so they are a smaller surface, but they are the same pattern and now have a
  ready migration path via the sequence form of `run_cmd`.
- **Already defended by hand:** `view/webview/api.py` uses `shlex.quote` at 545, 1489 and
  2245. Correct today, but quoting is the weaker habit; these are candidates for the
  sequence form too.
- `controller.py:1864` (`git clone` of a `base_name`) and `makepkg.py` build paths are
  worth a later pass.

## Tests

TDD, all new:

- `run_cmd` with a sequence does not go through a shell — a metacharacter argument is
  passed through verbatim as one argv element rather than interpreted.
- `run_cmd` with a string still uses `shell=True` (no regression for ~50 callers).
- `run_cmd` sequence + `custom_user` builds the `runuser` argv list.
- `pacman.search` passes `['pacman', '-Ss', <terms>]`, splitting a multi-word query.
- Regression test for the injection: a query containing `;` and a shell command reaches
  pacman as literal argv text and executes nothing.

Full suite (787 Python + JS contract tests) must stay green.
