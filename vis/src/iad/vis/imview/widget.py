"""anywidget model for the interactive image grid."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import traitlets

from iad.vis.imview.colormaps import build_lut_map
from iad.vis.imview.data import PanelData, PreparedGrid

_STATIC = Path(__file__).parent / 'static'


def _require_anywidget():
    try:
        import anywidget
    except ImportError as exc:
        raise ImportError(
            'imview requires anywidget. Install with: pip install "ialdev-vis[notebook]"'
        ) from exc
    return anywidget


def _as_buffer_view(array: np.ndarray) -> memoryview:
    """Expose ndarray bytes for anywidget binary comm (not JSON list encoding)."""
    contiguous = np.ascontiguousarray(array)
    return memoryview(contiguous)


class ImageGridWidget:
    """Factory for the anywidget class (lazy import)."""

    _cls: type | None = None

    @classmethod
    def create(
        cls,
        prepared: PreparedGrid,
        *,
        cbar: bool = True,
        ticks: str = 'xy',
        hist: bool | int | None = False,
        window_title: str | None = None,
        inspect: bool = True,
    ) -> Any:
        anywidget = _require_anywidget()
        if cls._cls is None:
            cls._cls = cls._build_widget_class(anywidget)
        luts = build_lut_map(prepared.cmaps)
        panel_meta = [
            {
                'id': p.id,
                'title': p.title,
                'kind': p.kind,
                'width': p.width,
                'height': p.height,
                'cmap': p.cmap,
                'clim': p.clim,
            }
            for p in prepared.panels
        ]
        buffers = [_as_buffer_view(p.buffer) for p in prepared.panels]
        return cls._cls(
            panels=panel_meta,
            buffers=buffers,
            luts=dict(luts),
            grid=prepared.grid,
            cmaps=prepared.cmaps,
            clims=[p.clim for p in prepared.panels],
            cbar=cbar,
            ticks=ticks,
            hist=bool(hist),
            window_title=window_title or '',
            inspect_enabled=inspect,
            view={'scale': 1.0, 'tx': 0.0, 'ty': 0.0},
            cursor={},
            selection={},
        )

    @staticmethod
    def _build_widget_class(anywidget):
        class _ImageGridWidget(anywidget.AnyWidget):
            _esm = _STATIC / 'imgrid.js'
            _css = _STATIC / 'imgrid.css'

            panels = traitlets.List(traitlets.Dict()).tag(sync=True)
            buffers = traitlets.List(traitlets.Any()).tag(sync=True)
            luts = traitlets.Dict().tag(sync=True)
            grid = traitlets.List(traitlets.Int()).tag(sync=True)
            cmaps = traitlets.List(traitlets.Unicode()).tag(sync=True)
            clims = traitlets.List().tag(sync=True)
            cbar = traitlets.Bool(True).tag(sync=True)
            ticks = traitlets.Unicode('xy').tag(sync=True)
            hist = traitlets.Bool(False).tag(sync=True)
            window_title = traitlets.Unicode('').tag(sync=True)
            inspect_enabled = traitlets.Bool(True).tag(sync=True)
            view = traitlets.Dict().tag(sync=True)
            cursor = traitlets.Dict().tag(sync=True)
            selection = traitlets.Dict().tag(sync=True)

            @traitlets.validate('buffers')
            def _validate_buffers(self, proposal):
                out = []
                for buf in proposal['value']:
                    if isinstance(buf, np.ndarray):
                        out.append(_as_buffer_view(buf))
                    elif isinstance(buf, memoryview):
                        out.append(buf)
                    else:
                        out.append(buf)
                return out

            @traitlets.validate('luts')
            def _validate_luts(self, proposal):
                out = {}
                for name, val in proposal['value'].items():
                    if isinstance(val, np.ndarray):
                        out[name] = _as_buffer_view(val)
                    elif isinstance(val, (bytes, bytearray, memoryview)):
                        out[name] = memoryview(val) if not isinstance(val, memoryview) else val
                    else:
                        out[name] = val
                return out

            @property
            def value(self) -> dict[str, Any]:
                return {
                    'cursor': dict(self.cursor),
                    'selection': dict(self.selection),
                    'view': dict(self.view),
                }

        return _ImageGridWidget
