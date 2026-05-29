#!/usr/bin/env python3
"""A/B benchmark: native atlas_rs.parse_pacman_info vs the pure-Python parser.

Times `pacman -Si` output parsing, the CPU half of `map_updates_data`. The Python side
is the REAL fallback (`pacman._parse_info_output_py`), imported directly, so there is no
copy to drift. The native side includes the list→set conversion that production does, so
the comparison reflects the real `map_updates_data` fast path.

Run:  python benchmarks/bench_pacman_info.py [--packages N] [--iters N] [--repeats N]

NOTE: build release first (setup.py pins debug=False; a debug build is ~8x slower).
Verifies both implementations produce equivalent output before timing.
"""

import argparse
import time

from atlas.gems.arch import pacman, native
from atlas.gems.arch.pacman import _parse_info_output_py, _native_data_as_sets


PKG_TEMPLATE = """Repository      : extra
Name            : pkg{i}
Version         : {i}.2.3-1
Description     : Synthetic package number {i} for benchmarking the parser
Architecture    : x86_64
URL             : https://example.com/pkg{i}
Licenses        : GPL-2.0-or-later
Groups          : None
Provides        : virt{i}  pkg{i}-abi={i}.2
Depends On      : libc  libfoo{i}  libbar{i}>=1.0  libbaz{i}
                  libextra{i}  libmore{i}
Optional Deps   : opt{i}: optional feature
Conflicts With  : oldpkg{i}
Replaces        : ancientpkg{i}
Download Size   :   {ds}.50 KiB
Installed Size  :   {s}.00 MiB
Build Date      : Tue 01 Jan 2024 10:00:00
Validated By    : SHA-256 Sum
"""


def make_si_output(n_packages: int) -> str:
    return "\n".join(
        PKG_TEMPLATE.format(i=i, ds=100 + i, s=1 + (i % 50)) for i in range(n_packages)
    )


def native_parse_with_conversion(atlas_rs, output: str, description: bool) -> dict:
    parsed = atlas_rs.parse_pacman_info(output, description)
    return {name: _native_data_as_sets(data) for name, data in parsed.items()}


def time_call(fn, iters: int, repeats: int) -> float:
    fn()  # warmup
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        for _ in range(iters):
            fn()
        best = min(best, (time.perf_counter() - start) / iters)
    return best


def normalize(result: dict) -> dict:
    out = {}
    for name, d in result.items():
        nd = {}
        for k, v in d.items():
            nd[k] = sorted(v) if isinstance(v, (set, list)) else v
        out[name] = nd
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packages", type=int, default=200, help="packages per parse call")
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()

    atlas_rs = native.load()
    if atlas_rs is None:
        print("ERROR: atlas_rs not available. Build it: CARGO_INCREMENTAL=0 pip install -e .")
        return 1

    output = make_si_output(args.packages)

    for description in (True, False):
        py_out = _parse_info_output_py(output, description)
        rs_out = native_parse_with_conversion(atlas_rs, output, description)
        match = "ok" if normalize(py_out) == normalize(rs_out) else "DIFF"

        py_t = time_call(lambda: _parse_info_output_py(output, description), args.iters, args.repeats)
        rs_t = time_call(lambda: native_parse_with_conversion(atlas_rs, output, description), args.iters, args.repeats)
        speedup = py_t / rs_t if rs_t else float("inf")

        label = f"description={description}"
        print(f"{label:<18} packages={args.packages:<5} "
              f"python={py_t*1e6:8.1f}us  rust={rs_t*1e6:8.1f}us  "
              f"speedup={speedup:5.2f}x  match={match}")
        if match == "DIFF":
            print("  ! outputs differ — investigate before trusting these numbers")

    print("\nNote: parsing only. map_updates_data also runs `pacman -Si` (subprocess +")
    print("sync-db read), which is unchanged; real-world gain depends on the parse fraction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
