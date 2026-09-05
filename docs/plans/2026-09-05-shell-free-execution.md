# Take the shell out of Atlas's command execution (2026-09-05)

Follow-up to [2026-09-05-search-argv-execution.md](2026-09-05-search-argv-execution.md),
which fixed `pacman.search`. Vatteck green-lit widening the scope: "Atlas is all about
security."

## The systemic defect

Fixing one call site was treating a symptom. Auditing every execution surface found the
same shape in three shared helpers, and one of them is worse than the search box.

### 1. `SimpleProcess` re-joins an argument list into a shell string

`atlas/commons/system.py`, `SimpleProcess._new`:

```python
return subprocess.Popen(args=[' '.join(cmd)] if self.shell else cmd, **args)
```

Callers pass a correct argv list — `['pacman', '-S', pkgname, '--noconfirm']` — and
`shell=True` **flattens it back into a shell command line**. Every element is re-parsed
as shell syntax. `new_root_subprocess` has the identical `' '.join(final_cmd)`.

This is the high-severity one. It covers install/remove/upgrade/downgrade, which run under
`sudo -S`, and the interpolated values are package names, `--ignore=<pkg>`,
`--assume-installed=<provider>` and app refs. Those are **not** all locally-typed input:
provider and dependency strings are parsed out of AUR PKGBUILD/`.SRCINFO` fields, which
are attacker-controlled text in a community repo.

(The injected command runs as the *user*, not root — `sudo` only covers up to the first
`;` — but arbitrary execution triggered by publishing an AUR package is not a distinction
worth relying on.)

**Every `shell=True` call site in the tree passes a proper argv list.** Checked one by
one: `pacman.upgrade_several`/`download`/`remove_several`, `makepkg.build`/`check`,
`flatpak.update`/`full_update`/`uninstall`/`install`, `snap.*`, `timeshift.delete` and
`read_created_snapshots`, `controller`'s removal transaction and `useradd`. Not one needs
a shell. The flag buys nothing and costs the argv boundary.

It also *silently corrupts* arguments: `pacman.upgrade_several` appends
`--overwrite=*`, and under `shell=True` that `*` is a glob handed to the shell. It
survives today only because nothing in the cwd matches it.

### 2. `execute()` only takes a string

`execute(cmd: str, shell: bool = ...)` either runs the string through a shell or does a
naive `final_cmd.split(' ')`. Callers therefore interpolate:

- `pacman.map_signed` — `f"pacman -{'S' if remote else 'Q'}i {' '.join(names)}"`, shell=True
- `pacman.list_hard_requirements` — `f'pacman -Rc {name} --print-format=%n '`, shell=True
- `sshell.mkdir` — `f'mkdir -p "{dir_path}"'`, shell=True. The double quotes stop word
  splitting but **not** `$(...)`, backticks or `${}`.
- `git.list_commits`, `flatpak.list_updates`, and the Debian gem's aptitude wrappers.

### 3. `run_cmd` string callers (the original defect, remaining sites)

`run_cmd` learned to take an argument list in the previous commit. ~30 callers still
build command lines by f-string. The one that matters most:

- **`flatpak.search`** — `run_cmd(f'flatpak search {word} --{installation}')`, the same
  GUI query, on a default-on source. Same severity as the pacman search box.

The rest interpolate package names, app ids, branches and refs.

### 4. Dead code holding a loaded gun

`atlas/commons/system.py:345`'s `notify_user` builds a `notify-send` line with `.format()`
and runs it through **`os.system`** — the message contains package names. The 2026-08-29
work converted notifications to an argv list, but it did that in
`atlas/view/util/util.py`; this copy was left behind. **It has no callers** (verified),
so it is not exploitable — it is a footgun waiting for the next agent to reach for the
obvious name in `commons`.

## Approach

Delete the shell from every path where Atlas runs a command *it constructed*. Keep it
only where a shell command line is genuinely the thing being run.

1. **Remove the join.** Drop `shell=True` from all `SimpleProcess` / `new_root_subprocess`
   call sites, then delete the `' '.join(cmd)` branch and the `shell` parameter from both.
   Once the parameter is gone, the footgun cannot be reintroduced by a future caller —
   that matters more than a one-line fix for a solo maintainer.
2. **`execute()` accepts a sequence**, like `run_cmd` now does: a sequence forces
   `shell=False` and skips the `split(' ')` guesswork. Convert its interpolating callers.
3. **Convert the remaining `run_cmd` f-string callers** to argument lists, starting with
   `flatpak.search`.
4. **Delete `commons.system.notify_user`** rather than fixing it. `view.util.util.notify_user`
   is the real one and is already argv-based.

### Deliberately left alone

**Launching a user's application** — `subprocess.Popen(..., shell=True)` in
`appimage/controller.py:842`, `arch/controller.py:3313`, `flatpak.py:484`, `snap.py:54`,
`web/controller.py:1149`, `debian/controller.py`. These run a command line that comes from
a `.desktop` `Exec=` entry or an equivalent, where shell syntax is part of the contract and
the user is deliberately launching that program. Converting them is a behaviour change, not
a hardening one. Noted in STATUS.md as reviewed-and-kept, so the next audit doesn't re-derive
it.

**The Debian gem's aptitude wrappers** are converted where the change is mechanical
(argv lists), but `aptitude.py` builds command *strings* in `gen_remove_cmd` and friends.
Atlas is Arch-focused (AGENTS.md §3.1) and the gem is off by default; I cannot exercise
apt on this box, so a blind restructure there would be the risky kind of rewrite §3.3
warns about. Its `execute(..., shell=True)` string sites are reported, not rewritten.

## Tests

TDD throughout. The load-bearing ones:

- `SimpleProcess` passes its argv list to `Popen` unjoined, and no longer accepts `shell`.
- A package name containing `;` reaches pacman as one argv element (`upgrade_several`,
  `remove_several`, `download`).
- `execute()` with a sequence does not use a shell and does not `split(' ')`.
- `flatpak.search` passes `['flatpak', 'search', <term>, '--<installation>']`.
- `commons.system` no longer exports `notify_user`.
- Existing tests asserting exact command strings are updated to expect argv lists — they
  are the regression net for "the command Atlas actually runs is unchanged".

Full suite (Python + JS contract tests) must stay green.
