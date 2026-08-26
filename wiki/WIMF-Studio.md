# WIMF Studio

Launch with `wimf-studio` or `wimf view [file]`.

## Encode & Compare

Compare source, decoded output, and a difference view. Studio reports encoded size, ratio, MSE, maximum error, PSNR, encode/decode time, and selected tile modes.

## Inspect

Zoom and pan, select an ROI, inspect metadata, show tile boundaries, and visualize Raw, Predictive, Palette, and Wavelet selections.

## Protection & History

Inspect anti-rot status, attempt bounded repair, browse chrono states, compare states, and export a selected state.

## Codec Lab

Create deterministic corrupted copies, test Base64/data URLs, compare strict decoding with unsafe verified-tile previews, and inspect failed tiles.

The GUI stays responsive by running codec operations in workers. Cancellation is cooperative between tiles and leaves the current document untouched.

## Interface

The interface follows the Fluent design language popularized by
[GoodbyeDPI UI](https://github.com/Storik4pro/goodbyeDPI-UI) (Storik4pro, Apache-2.0):
card sections with soft strokes, an accent action bar, a rotating tip banner, and a
first-run quick-start window. Widgets use the
[Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme) (rdbende) in
dark or light; spacing, sizes and palettes are centralized in wimf/studio_theme.py.