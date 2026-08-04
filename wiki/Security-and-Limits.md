# Security and limits

WIMF treats image files as untrusted input.

- Dimensions, channel counts, bit depths, tile geometry, offsets, and sizes are validated before allocation.
- Metadata, history counts, extension counts, and aggregate expansion are bounded.
- Tile checksums are verified before reconstruction.
- Unknown or malformed mode and entropy identifiers are rejected.
- Strict decoding never silently substitutes corrupted data.
- Sanitizer and malformed-input jobs are release-blocking.

Zstandard 1.5.7 is pinned for portable wheels. Its source, license, and digests are recorded under `third_party/zstd`; upstream dependency review is separate from first-party CodeQL analysis.

WIMF provides compression and integrity checks, not confidentiality or authentication. Do not store secrets in pixels or metadata.
