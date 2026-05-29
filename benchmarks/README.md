# Benchmarks

A/B benchmarks for the Rust (`atlas_rs`) migration. The discipline (see
[`../docs/ROADMAP.md`](../docs/ROADMAP.md)): a native rewrite must be *measurably*
faster than the Python it replaces, or it isn't worth maintaining two implementations.

## ⚠️ Always benchmark a RELEASE build

`pip install -e .` and `cargo build` produce **debug** Rust by default, which is ~8×
slower than release — slow enough that the native code can lose to pure Python. `setup.py`
now pins `debug=False` so installs are optimized; if you build the extension by hand for
benchmarking, use `--release`:

```bash
CARGO_INCREMENTAL=0 cargo build --release --manifest-path rust/Cargo.toml
cp rust/target/release/libatlas_rs.so \
   atlas/gems/arch/atlas_rs.cpython-*-x86_64-linux-gnu.so
```

## bench_srcinfo.py

Deterministic A/B for `map_srcinfo` (pure `.SRCINFO` parsing — no network/pacman). The
Python reference is the implementation the Rust port replaced (recovered from git), so
the comparison is honest. It verifies both produce equivalent output before timing.

```bash
python benchmarks/bench_srcinfo.py                  # default workloads
python benchmarks/bench_srcinfo.py --scale 4        # bigger inputs
python benchmarks/bench_srcinfo.py --iters 50000 --repeats 8
```

### Result on record (release build, 2026-05-28)

| workload | python | rust | speedup |
|----------|-------:|-----:|--------:|
| small (5 deps)    | ~11 µs  | ~6 µs  | ~1.9× |
| medium (40 deps)  | ~39 µs  | ~18 µs | ~2.1× |
| large (200 deps)  | ~150 µs | ~67 µs | ~2.2× |
| split (5 subpkgs) | ~46 µs  | ~23 µs | ~2.0× |

With a **debug** build the same workloads run ~0.22–0.26× (Rust ~4× *slower*) — the
reason the release-build rule above exists.

## bench_pacman_info.py

A/B for `pacman -Si` output parsing (the CPU half of `map_updates_data`), native
`atlas_rs.parse_pacman_info` vs the real `pacman._parse_info_output_py`. Verifies
equivalent output first.

```bash
python benchmarks/bench_pacman_info.py --packages 100 --iters 300 --repeats 4
```

### Result on record (release build, 2026-05-29)

| description | packages | python | rust | speedup |
|-------------|---------:|-------:|-----:|--------:|
| True  | 100 | ~3060 µs | ~2400 µs | **~1.27×** |
| False | 100 | ~2890 µs | ~2380 µs | **~1.21×** |

**Lesson:** only ~1.2×, much less than `map_srcinfo`'s ~2×. The native path returns ~100
structured dicts, so PyO3 result-marshalling (building nested dicts) plus the Python
list→set conversion dominate the parse win. Parsing ports pay off when the *result* is
small; when it's a big structured payload, the boundary eats the gain. Weigh this before
porting more per-package parsers.

## Not yet benchmarked

`map_missing_deps` is dominated by pacman + AUR network I/O, not CPU, and a fair Python
baseline needs the full `DependenciesAnalyser` object graph. Benchmark it with the
`ATLAS_DISABLE_RS` switch against a fixed package set if/when that path is optimized.
