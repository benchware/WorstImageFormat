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
