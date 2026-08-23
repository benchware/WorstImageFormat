# Desktop and application integrations

## Linux desktops

CMake installs the `image/x-wimf` shared-mime-info definition, WIMF Studio
desktop association, and thumbnailer entry on Linux. After a system install,
refresh the caches when the package manager does not do so automatically:

```bash
update-mime-database /usr/local/share/mime
update-desktop-database /usr/local/share/applications
```

The thumbnailer invokes `wimf thumbnail`, produces a bounded PNG, and accepts
the `%i`, `%o`, and `%s` fields used by GNOME, KDE, and Xfce thumbnail services.

## Windows Explorer

Configure with `-DWIMF_BUILD_WINDOWS_SHELL=ON` to build the native
`wimf-thumbnail.dll`. Install it and run `register-thumbnail.ps1` with the DLL
path to register it for the current user; the matching unregister script makes
the operation reversible. The DLL implements stream-based `IThumbnailProvider`
and `IPreviewHandler` classes, validates WIMF through the C ABI, bounds output,
and renders an alpha-aware 32-bit DIB. Registration is per-user and does not
require writing to machine-wide registry keys.

## ImageMagick

`integrations/imagemagick` contains an optional ImageMagick 7 decode coder built
with `-DWIMF_BUILD_IMAGEMAGICK=ON`. It recognizes WIMF magic and decodes through
the public C ABI. ImageMagick module installation paths depend on its quantum and
HDRI ABI. GraphicsMagick uses a different module ABI and remains a separate port.

## FFmpeg

`integrations/ffmpeg/wimfdec.c` is an in-tree libavcodec decoder integration.
FFmpeg has no third-party runtime codec plugin ABI, so registration requires an
upstream codec ID, configure/Makefile entries, FATE samples, and FFmpeg review.
The included README lists those changes. Until accepted upstream, this is a
maintained integration source kit rather than support in stock FFmpeg binaries.

## Android (Termux)

AArch64 builds get NEON and the ARM CRC-32 extension automatically through
runtime dispatch; no extra build flags are needed. Build with the standard
`pip install -e . --no-build-isolation` inside Termux using its clang
toolchain. One known native-build caveat: Android Bionic lacks `qsort_r`,
which the bundled Zstandard sources reference; patch or shim that symbol when
building natively on Android (see issue #31 for a worked example). Wheels for
Android are not yet published; guidance tracks the roadmap.
