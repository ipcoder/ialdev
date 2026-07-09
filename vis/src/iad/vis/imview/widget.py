"""anywidget model for the interactive image grid."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import traitlets

from iad.vis.imview.colormaps import build_lut_map
from iad.vis.imview.data import PreparedGrid

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


def apply_prepared(widget: Any, prepared: PreparedGrid) -> None:
    """Push every ``PreparedGrid`` field into widget traits (create and update).

    Syncs panel metadata, binary buffers, colormap LUTs, canvas size, and
    byte/pixel accounting without triggering redundant frontend redraws.
    """
    with widget.hold_trait_notifications():
        widget.panels = [
            {
                'id': p.id,
                'title': p.title,
                'kind': p.kind,
                'width': p.width,
                'height': p.height,
                'sourceWidth': p.source_width,
                'sourceHeight': p.source_height,
                'factor': p.factor,
                'sentBytes': p.sent_bytes,
                'fullBytes': p.full_bytes,
                'cmap': p.cmap,
                'clim': p.clim,
                'layout': p.layout,
                'cbar': p.cbar,
            }
            for p in prepared.panels
        ]
        widget.buffers = [_as_buffer_view(p.buffer) for p in prepared.panels]
        widget.luts = dict(build_lut_map(prepared.cmaps))
        widget.grid = prepared.grid
        widget.cmaps = prepared.cmaps
        widget.clims = [p.clim for p in prepared.panels]
        widget.canvas_width = int(prepared.canvas_size[0])
        widget.canvas_height = int(prepared.canvas_size[1])
        widget.data_sent_bytes = int(prepared.sent_bytes)
        widget.data_full_bytes = int(prepared.full_bytes)
        widget.data_sent_pixels = int(prepared.sent_pixels)
        widget.data_full_pixels = int(prepared.full_pixels)
        widget.data_over_budget = bool(prepared.data_over_budget)


class ImageGridWidget:
    """Factory for the lazy-imported anywidget class."""

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
        show_grid: bool = False,
        adj_clim: bool = False,
    ) -> Any:
        """Instantiate the anywidget and apply ``prepared`` panel data.

        Returns a widget with synced traits: ``panels``, ``buffers``, ``luts``,
        ``canvas_width`` / ``canvas_height``, ``data_sent_*``, ``view``,
        ``cursor``, and ``selection``. The ``value`` property mirrors cursor,
        selection, and view state for marimo reactivity.
        """
        anywidget = _require_anywidget()
        if cls._cls is None:
            cls._cls = cls._build_widget_class(anywidget)
        widget = cls._cls(
            cbar=cbar,
            ticks=ticks,
            hist=bool(hist),
            show_grid=show_grid,
            adj_clim=adj_clim,
            window_title=window_title or '',
            inspect_enabled=inspect,
            view={'scale': 1.0, 'tx': 0.0, 'ty': 0.0},
            cursor={},
            selection={},
        )
        apply_prepared(widget, prepared)
        return widget

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
            canvas_width = traitlets.Int(320).tag(sync=True)
            canvas_height = traitlets.Int(200).tag(sync=True)
            data_sent_bytes = traitlets.Int(0).tag(sync=True)
            data_full_bytes = traitlets.Int(0).tag(sync=True)
            data_sent_pixels = traitlets.Int(0).tag(sync=True)
            data_full_pixels = traitlets.Int(0).tag(sync=True)
            data_over_budget = traitlets.Bool(False).tag(sync=True)
            cbar = traitlets.Bool(True).tag(sync=True)
            ticks = traitlets.Unicode('xy').tag(sync=True)
            hist = traitlets.Bool(False).tag(sync=True)
            show_grid = traitlets.Bool(False).tag(sync=True)
            adj_clim = traitlets.Bool(False).tag(sync=True)
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
