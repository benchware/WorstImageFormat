<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/white.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png">
    <img alt="Worst Image Format" src="https://raw.githubusercontent.com/benchware/WorstImageFormat/main/.github/assets/dark.png" width="500">
  </picture>
</p>

WIMF is an experimental image codec with a Python frontend and a portable C++17 backend. New files use the **WIM2** container and the canonical `.wimf` extension.

WIM2 divides an image into independently decodable tiles and chooses Raw, Predictive, Palette, or Wavelet coding per tile. This supports exact lossless output, lossy compression, region-of-interest decoding, high bit depth, localized corruption detection, optional anti-rot recovery, and indexed history states.

## Start here

- [[Installation]] — install wheels and verify native acceleration.
- [[Python-API]] — encode, decode, inspect, ROI, metadata, and history.
- [[Command-line tools]] — headless workflows and diagnostics.
- [[WIMF-Studio]] — desktop encoder, inspector, and corruption lab.
- [[WIM2-Format]] — container and tile-mode overview.
- [[Conformance-Vectors]] — portable decoder expectations and hashes.
- [[Native-Integration]] — embed the codec without Python.
- [[Corruption-and-Recovery]] — strict decoding, diagnostic previews, and anti-rot.
- [[Legacy-Migration]] — move WIMF v1, `.wif`, AWIF, and `ROT!` content to WIM2.
- [[Roadmap]] — interoperability and adoption work.

## Project status

WIM2 is the only recommended authoring format. WIMF 2.2 warns when deprecated legacy writers are used. WIMF 3.0 will remove those writers while retaining read-only legacy compatibility.

WIMF is experimental. Please report reproducible bugs at <https://github.com/benchware/WorstImageFormat/issues> with your OS, Python version, `wimf runtime --json` output, and a minimal sample when possible.

> WIMF compresses data; it does not encrypt it. Never store secrets in metadata.
