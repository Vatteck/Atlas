#!/usr/bin/env python3
"""A/B benchmark: native (Rust) ``atlas_rs.map_srcinfo`` vs the original Python impl.

This is the deterministic half of the Phase 0 benchmark discipline (see
``docs/ROADMAP.md``): `.SRCINFO` parsing is pure CPU with no network or pacman, so we
can measure the native speedup repeatably. The Python reference is the implementation
that the Rust version replaced (recovered from git history) so the comparison is
apples-to-apples.

Run:  python benchmarks/bench_srcinfo.py [--scale N] [--iters N] [--repeats N]

It verifies both implementations produce equivalent output before timing, then reports
per-call time and the speedup factor for several workload sizes.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Optional, Set


# --------------------------------------------------------------------------------------
# Reference Python implementation (the code the Rust port replaced; from commit 085499f).
# Kept verbatim so the benchmark measures the real before/after, not a paraphrase.
# --------------------------------------------------------------------------------------
RE_SRCINFO_KEYS = re.compile(r'(\w+)\s+=\s+(.+)\n')

KNOWN_LIST_FIELDS = ('validpgpkeys', 'checkdepends', 'checkdepends_x86_64',
                     'checkdepends_i686', 'depends', 'depends_x86_64', 'depends_i686',
                     'optdepends', 'optdepends_x86_64', 'optdepends_i686', 'sha256sums',
                     'sha256sums_x86_64', 'sha512sums', 'sha512sums_x86_64', 'source',
                     'source_x86_64', 'source_i686', 'makedepends', 'makedepends_x86_64',
                     'makedepends_i686', 'provides', 'conflicts')


def py_merge_subinfos(subinfos, pkgname=None, fields=None):
    info = {}
    for subinfo in subinfos:
        if not pkgname or subinfo.get('pkgname') in {None, pkgname}:
            for key, val in subinfo.items():
                if not fields or key in fields:
                    current_val = info.get(key)
                    if current_val is None:
                        info[key] = val
                    else:
                        if not isinstance(current_val, set):
                            current_val = {current_val}
                            info[key] = current_val
                        if isinstance(val, set):
                            current_val.update(val)
                        else:
                            current_val.add(val)
    for field in list(info.keys()):
        val = info.get(field)
        if isinstance(val, set):
            info[field] = [*val]
    return info


def py_map_srcinfo(string: str, pkgname: Optional[str], fields: Set[str] = None) -> dict:
    subinfos, subinfo = [], {}
    key_fields = {'pkgname', 'pkgbase'}

    for field in RE_SRCINFO_KEYS.findall(string):
        key = field[0].strip()
        val = field[1].strip()

        if subinfo and key in key_fields:
            subinfos.append(subinfo)
            subinfo = {key: val}
        elif not fields or key in fields:
            if key not in subinfo:
                subinfo[key] = {val} if key in KNOWN_LIST_FIELDS else val
            else:
                if not isinstance(subinfo[key], set):
                    subinfo[key] = {subinfo[key]}
                subinfo[key].add(val)

    if subinfo:
        subinfos.append(subinfo)

    pkgnames = {s['pkgname'] for s in subinfos if 'pkgname' in s}
    return py_merge_subinfos(
        subinfos=subinfos,
        pkgname=None if (not pkgname or len(pkgnames) == 1 or pkgname not in pkgnames) else pkgname,
        fields=fields,
    )


# --------------------------------------------------------------------------------------
# Workload generation
# --------------------------------------------------------------------------------------
def make_srcinfo(n_deps: int, n_make: int, n_provides: int, n_split: int) -> str:
    """Build a representative .SRCINFO with the given field counts and split packages."""
    lines = ["pkgbase = bench-pkg",
             "\tpkgdesc = A synthetic package for benchmarking",
             "\tpkgver = 1.2.3",
             "\tpkgrel = 1",
             "\turl = https://example.com/bench"]
    lines += [f"\tdepends = libdep{i}>=1.0" for i in range(n_deps)]
    lines += [f"\tmakedepends = makedep{i}" for i in range(n_make)]
    lines += [f"\tprovides = virt{i}=1.2.3" for i in range(n_provides)]
    lines += [f"\tsource = https://example.com/src{i}.tar.gz" for i in range(3)]
    for s in range(n_split):
        lines.append(f"pkgname = bench-pkg-split{s}")
        lines.append(f"\tdepends = bench-pkg=1.2.3")
        lines.append(f"\tdepends = extralib{s}")
    if n_split == 0:
        lines.append("pkgname = bench-pkg")
    return "\n".join(lines) + "\n"


def normalize(result: dict) -> dict:
    """Normalize for equivalence comparison: sort list values, leave scalars."""
    out = {}
    for k, v in result.items():
        if isinstance(v, (list, set)):
            out[k] = sorted(str(x) for x in v)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------------------
def time_call(fn, src, pkgname, iters: int, repeats: int) -> float:
    """Return best per-call seconds across `repeats` batches of `iters` calls."""
    fn(src, pkgname)  # warmup
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(iters):
            fn(src, pkgname)
        elapsed = time.perf_counter() - start
        best = min(best, elapsed / iters)
    return best


def fmt(seconds: float) -> str:
    return f"{seconds * 1e6:8.2f} us"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scale", type=int, default=1, help="multiplier on field counts")
    ap.add_argument("--iters", type=int, default=20000, help="calls per timed batch")
    ap.add_argument("--repeats", type=int, default=5, help="batches (best is reported)")
    args = ap.parse_args()

    # Locate the built native module (installed, or in the source tree).
    try:
        import atlas_rs  # noqa: F401
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "atlas" / "gems" / "arch"))
        try:
            import atlas_rs  # noqa: F401
        except ImportError:
            print("ERROR: atlas_rs not built. Run `CARGO_INCREMENTAL=0 pip install -e .` first.")
            return 1
    import atlas_rs

    s = args.scale
    workloads = [
        ("small  (5 deps)",     make_srcinfo(5 * s, 2 * s, 1 * s, 0)),
        ("medium (40 deps)",    make_srcinfo(40 * s, 15 * s, 8 * s, 0)),
        ("large  (200 deps)",   make_srcinfo(200 * s, 60 * s, 30 * s, 0)),
        ("split  (5 subpkgs)",  make_srcinfo(40 * s, 15 * s, 8 * s, 5)),
    ]

    print(f"scale={args.scale}  iters={args.iters}  repeats={args.repeats}  (best per-call shown)\n")
    print(f"{'workload':<20} {'python':>12} {'rust':>12} {'speedup':>10}  {'match':>6}")
    print("-" * 66)

    for name, src in workloads:
        py_out = normalize(py_map_srcinfo(src, "bench-pkg"))
        rs_out = normalize(atlas_rs.map_srcinfo(src, "bench-pkg"))
        match = "ok" if py_out == rs_out else "DIFF"

        py_t = time_call(py_map_srcinfo, src, "bench-pkg", args.iters, args.repeats)
        rs_t = time_call(atlas_rs.map_srcinfo, src, "bench-pkg", args.iters, args.repeats)
        speedup = py_t / rs_t if rs_t else float("inf")

        print(f"{name:<20} {fmt(py_t):>12} {fmt(rs_t):>12} {speedup:>9.2f}x  {match:>6}")

        if match == "DIFF":
            print("  ! outputs differ — investigate before trusting these numbers")
            print(f"    python keys: {sorted(py_out)}")
            print(f"    rust keys:   {sorted(rs_out)}")

    print("\nNote: deterministic parsing benchmark only. map_missing_deps (pacman + AUR")
    print("network I/O) is dominated by I/O, not CPU; benchmark it separately if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
