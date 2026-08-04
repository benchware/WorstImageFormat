# Installation

## PyPI

WIMF supports CPython 3.10–3.14.

```bash
python -m pip install --upgrade wimf
```

Matching Windows, Linux, and macOS wheels include the native C++ backend and do not require a local compiler.

## Verify the backend

```bash
python -m wimf runtime --json
```

Look for:

```json
{
  "native": true,
  "native_orchestration": true
}
```

If `native` is false, WIMF is using the slower Python compatibility implementation. Confirm that your Python version and architecture match a published wheel.

## Launch Studio

```bash
wimf-studio
```

or:

```bash
python -m wimf view
```

Tkinter is required only for Studio. Headless CLI tools do not import it.

## Source installation

A source installation requires a C++17 compiler. The build compiles two native extensions and the pinned Zstandard backend.
