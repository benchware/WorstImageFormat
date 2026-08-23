# SIMD kernel benchmarks

The native SIMD acceleration (AVX2 on x86-64, NEON on AArch64) is
runtime-dispatched: one binary serves every host. To answer "how much is it
worth on this machine?", the repository ships a small native benchmark that
times each backend directly on the current CPU.

## Quick start

```bash
cmake -S . -B build -DWIMF_BUILD_BENCHMARKS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
./build/wimf-simd-bench            # ./build/Release/wimf-simd-bench.exe with MSVC
```

CI runs the same tool on every push: results appear in the **job summary** of
the *Standalone C++* workflow jobs (Linux / Windows / macOS) and are uploaded
as the `simd-bench-<os>` artifacts.

## What is measured

| Section | Meaning |
|---|---|
| Predictive left filter - Cost | Wrapped-absolute-residual cost scan over 32k rows × 256 B |
| Predictive left filter - Emit | Residual emission over the same rows |
| CRC-32 | Table (scalar), ARM hardware extension when present, and the dispatched path the codec actually uses |
| Synthetic sample image | End-to-end lossless encode/decode of a deterministic 512×320×3 gradient+noise image through the public `encode_image` / `decode_image` API |

Inputs are fixed PRNG streams; timing is one warmup pass followed by the
minimum of six repetitions (`steady_clock`); checksum sinks are printed as an
HTML comment so optimizers cannot elide measured work.

## Reading the numbers

- **Compare backends within one report only.** Each CI OS runs on different
  hardware, so Linux-vs-macOS rates are not comparable; the scalar baseline in
  the same table is.
- The speedup table divides accelerated backends by that same-run scalar
  reference, which cancels machine differences for the *ratio*.
- End-to-end image numbers always use the dispatched backend (whatever the
  host supports); they include zstd, tiling, and mode search, so they are far
  from the pure kernel ratios by design.
- Shared CI runners are noisy; treat sub-10% deltas as noise even within one
  report. Re-run before quoting a number.

## Submitting results

Save the Markdown output and open a PR adding it under
`benchmarkinfo/simd/<cpu>-<handle>.md`, following the conventions in
`benchmarkinfo/README.md`. Include the header block (architecture + active
backends) verbatim so readers can see what was dispatched.
