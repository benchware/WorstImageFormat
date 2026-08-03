"""Centralized WIMF 2.2 legacy-authoring warnings."""

import warnings


def warn_legacy(feature, replacement="write WIM2 instead"):
    warnings.warn(
        f"{feature} is deprecated in WIMF 2.2 and will be removed in WIMF 3.0; "
        f"{replacement}. Legacy decoding will remain supported.",
        FutureWarning,
        stacklevel=3,
    )
