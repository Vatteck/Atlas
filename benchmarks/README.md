# Benchmarks

This directory is **historical**. It records measurements from the removed Rust
`atlas_rs` experiment so future agents do not repeat the same bad bet.

Atlas is currently **pure Python**. There is no Rust crate, no PyO3 extension, and no
native module to build. Do not use this directory as an instruction to reintroduce native
code.

## Why the old benchmark exists

`bench_srcinfo.py` was the deterministic A/B harness for the former `.SRCINFO` parser
experiment. It compared the original Python parser with a Rust parser and verified both
produced equivalent output before timing.

Result on record from the removed release build (2026-05-28):

| workload | python | rust | speedup |
|---|---:|---:|---:|
| small (5 deps) | ~11 µs | ~6 µs | ~1.9× |
| medium (40 deps) | ~39 µs | ~18 µs | ~2.1× |
| large (200 deps) | ~150 µs | ~67 µs | ~2.2× |
| split (5 subpkgs) | ~46 µs | ~23 µs | ~2.0× |

Even that best-case parser win was too small to justify a Rust toolchain and dual
implementation in an app whose wall-clock cost is dominated by pacman, AUR RPC, Flatpak,
network, and build subprocesses.

## Lessons kept

- Benchmark before adding complexity.
- Native code only makes sense for a measured CPU-bound path with a small result.
- Returning large structured payloads across a Python/native boundary can erase parser
  wins; the reverted native `pacman -Si` parser only measured about **1.2×**.
- Debug native builds can be slower than Python, so any future native experiment must be
  measured in release mode.

For the full verdict, see [`../docs/ROADMAP.md`](../docs/ROADMAP.md). For current work,
see [`../docs/STATUS.md`](../docs/STATUS.md) and [`../docs/BACKLOG.md`](../docs/BACKLOG.md).
