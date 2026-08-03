# Vendored Zstandard

WIMF wheels bundle the unmodified portable Zstandard **1.5.7** amalgamation from
<https://github.com/facebook/zstd/releases/tag/v1.5.7> under its BSD license.

| File | SHA-256 |
|---|---|
| `zstd.c` | `efd2063214b7eb797919386a39833ad0954b08182f89eb01d5f4150415a815ee` |
| `zstd.h` | `9b4bc8245565c98ccfc61c07749928b57e7c0f6fddb0530c4f6aa1971893d88b` |
| `zstd_errors.h` | `66a8c3f71d12ea6e797e4f622f31f3f8f81c41b36f48cad4f5de7d8bfb6aac0a` |
| `LICENSE` | `7055266497633c9025b777c78eb7235af13922117480ed5c674677adc381c9d8` |

CodeQL analyzes WIMF's wrappers and first-party codec code, not this generated
upstream amalgamation. Dependency/CVE review and sanitizer tests remain blocking.
