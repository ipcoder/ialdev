"""Matplotlib colormap -> RGBA LUT bytes for the frontend renderer."""

from __future__ import annotations

from typing import Any

import numpy as np

from iad.vis.insight import KeyProcessor, register_custom_colormaps

_CMAP_MENU = tuple(KeyProcessor.cmaps.values())
_LUT_SIZE = 256

# Ensure custom colormaps (rain, wide, durange, ...) are registered.
register_custom_colormaps()


def mpl_lut_bytes(cmap: Any, n: int = _LUT_SIZE) -> bytes:
    """Sample a matplotlib colormap into ``n x 4`` uint8 RGBA bytes (row-major)."""
    import matplotlib.pyplot as plt

    if callable(cmap):
        cm = cmap
    else:
        cm = plt.get_cmap(cmap)
    samples = cm(np.linspace(0.0, 1.0, n))
    rgba = (np.clip(samples, 0.0, 1.0) * 255).astype(np.uint8)
    return rgba.tobytes()


def build_lut_map(cmap_names: list[str]) -> dict[str, bytes]:
    """Build LUT byte blobs for all requested and menu colormap names."""
    names = list(dict.fromkeys([str(n) for n in cmap_names] + list(_registered_menu_names())))
    luts: dict[str, bytes] = {}
    for name in names:
        try:
            luts[name] = mpl_lut_bytes(name)
        except (ValueError, TypeError):
            continue
    return luts


def _registered_menu_names() -> list[str]:
    import matplotlib.pyplot as plt

    names: list[str] = []
    for name in _CMAP_MENU:
        try:
            plt.get_cmap(name)
        except (ValueError, TypeError):
            continue
        names.append(name)
    return names
