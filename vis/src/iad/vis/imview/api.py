"""Public API: imgrid facade and ImageGrid wrapper."""

from __future__ import annotations

import warnings
from collections import namedtuple
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from iad.vis.imview.data import (
    PreparedGrid,
    convert_pairs,
    name_imgrid_images,
    prepare_grid_from_parsed,
)
from iad.vis.imview.widget import ImageGridWidget, apply_prepared


def _in_marimo() -> bool:
    try:
        import marimo
    except ImportError:
        return False
    try:
        return bool(marimo.running_in_notebook())
    except Exception:
        return False


def _in_ipython() -> bool:
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    return get_ipython() is not None


def _resolve_backend(backend: str) -> str:
    if backend != 'auto':
        return backend
    if _in_marimo():
        return 'marimo'
    if _in_ipython():
        return 'jupyter'
    return 'widget'


def _resolve_figsize(
    figsize: tuple[int | None, int | None] | None,
    width: int | None,
    height: int | None,
) -> tuple[int | None, int | None] | None:
    if figsize is not None:
        if width is not None or height is not None:
            warnings.warn(
                'figsize takes precedence over width/height kwargs',
                stacklevel=3,
            )
        return figsize
    if width is not None or height is not None:
        return (width, height)
    return None


class ImageGrid:
    """Wrapper around :class:`~iad.vis.imview.widget.ImageGridWidget`.

    Provides host display protocols (marimo, IPython) and in-place data updates
    via :meth:`update_data`. In marimo, use ``grid.ui`` when composing layouts
    with ``mo.vstack`` / ``mo.hstack``; return the ``ImageGrid`` directly as a
    cell's last expression for a single grid.
    """

    def __init__(
        self,
        widget: Any,
        prepared: PreparedGrid,
        *,
        backend: str,
        ui: Any = None,
        prep_kwargs: dict[str, Any] | None = None,
    ):
        self.widget = widget
        self.images = prepared.images
        self.panels = prepared.panels
        self.backend = backend
        self.ui = ui if ui is not None else widget
        self._ref = list(prepared.source_ref)
        self._prep_kwargs = dict(prep_kwargs or {})

    @property
    def value(self) -> dict[str, Any]:
        return self.widget.value

    def update_data(self, data: Mapping[str, Any] | Sequence[Any]) -> ImageGrid:
        """Replace panel pixel data and re-sync the widget in place.

        *data* is a dict keyed by the panel titles passed to :func:`imgrid`, or a
        sequence of arrays in panel order. Each array must match the shape of the
        corresponding original image (after internal conversion), else ``ValueError``.
        The same conversion and preparation pipeline as :func:`imgrid` is reused.
        """
        titles = [title for title, _ in self._ref]
        if isinstance(data, Mapping):
            if set(data) != set(titles):
                raise ValueError(f'update_data keys {sorted(data)} != panel titles {sorted(titles)}')
            arrays = [data[title] for title in titles]
        else:
            arrays = list(data)
            if len(arrays) != len(titles):
                raise ValueError(f'update_data: expected {len(titles)} arrays, got {len(arrays)}')

        parsed = convert_pairs(list(zip(arrays, titles)))
        for (arr, title), (_, shape) in zip(parsed, self._ref):
            if arr.shape != shape:
                raise ValueError(
                    f'update_data: panel {title!r} shape {arr.shape} != expected {shape}'
                )

        prepared = prepare_grid_from_parsed(parsed, **self._prep_kwargs)
        apply_prepared(self.widget, prepared)
        self.images, self.panels, self._ref = prepared.images, prepared.panels, prepared.source_ref
        return self

    def _display_(self) -> Any:
        import marimo as mo

        return mo.ui.anywidget(self.widget)

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.ui)

    def _repr_mimebundle_(self, include=None, exclude=None):
        return {}


def imgrid(
    *images,
    labels: dict | list[dict] = None,
    titles: list[str] | None = None,
    grid: str | tuple | list = 'auto',
    transp: bool = False,
    cmap: str | list[str] = 'rain',
    cbar: bool = True,
    clim: Any = 'auto',
    ticks: str = 'xy',
    hist: bool | int | None = False,
    window_title: str | None = None,
    inspect: bool = True,
    show_grid: bool = False,
    adj_clim: bool = False,
    resize: Literal['no', 'up', 'down', 'error'] | bool = 'error',
    max_pixels: int = 500_000,
    max_total_pixels: int = 1_500_000,
    figsize: tuple[int | None, int | None] | None = None,
    max_zoom: float | Literal['full'] | None = None,
    downsample: int | None = None,
    height: int | None = None,
    width: int | None = None,
    backend: Literal['auto', 'marimo', 'jupyter', 'widget', 'figure'] = 'auto',
    out: bool | Literal['widget', 'ui', 'images', 'all', 'fig'] = False,
    mosaic: bool | str | None = None,
    **imkw,
) -> ImageGrid | Any:
    """Interactive image grid for marimo / Jupyter via anywidget.

    Pixel data is sent once as binary buffers; colormap, clim, pan/zoom, and
    hover inspection run client-side. Layout (mosaic grids, colorbars, axis
    chrome) is computed in Python and sent as precomputed panel rects.

    Parameters
    ----------
    *images
        Arrays, PIL images, or ``(array, title)`` pairs. Titles default to
        inferred variable names or ``Stream_{n}``.
    grid
        ``'auto'``, ``(rows, cols)``, mosaic string (e.g. ``'AB\\nCD'``), or
        :class:`~iad.vis.gridcore.MosaicParser`.
    figsize
        ``(width, height)`` target size in CSS pixels. Either dimension may be
        ``None``. Overrides legacy ``width`` / ``height`` kwargs.
    max_zoom
        Crispness headroom for static oversampling: buffer resolution is at
        least ``panel_display_size * max_zoom``. Use ``'full'`` for factor 1.
        Mutually exclusive with ``downsample``.
    downsample
        Fixed integer downsample factor applied in Python before transfer.
    max_pixels, max_total_pixels
        Per-panel pixel budget (default 500k) and total budget (default 1.5M).
        Used when ``max_zoom`` / ``downsample`` are not set.
    backend
        ``'auto'`` picks marimo / Jupyter / raw widget. Use ``'widget'`` in tests.
    out
        Return a component instead of ``ImageGrid``: ``'widget'``, ``'ui'``,
        ``'images'``, ``'grid'``, ``'all'``, or ``'fig'``.

    Returns
    -------
    ImageGrid or Any
        Default: :class:`ImageGrid` with ``.widget``, ``.ui``, ``.value``,
        and :meth:`ImageGrid.update_data`.
    """
    if mosaic:
        cbar, ticks = False, ''
        if mosaic != 'titles':
            titles = [''] * len(images)
    if not set(ticks).issubset('xy'):
        raise TypeError("String argument `ticks` may only include 'x' or 'y' letters.")

    if downsample is not None and max_zoom is not None:
        raise ValueError('max_zoom and downsample are mutually exclusive')

    imkw.pop('cap', None)
    imkw.pop('fsz', None)
    kw_figsize = imkw.pop('figsize', None)
    clim_arg = imkw.pop('clim', clim)
    _ = labels

    resolved_figsize = _resolve_figsize(
        figsize if figsize is not None else kw_figsize,
        width,
        height,
    )

    if backend == 'figure':
        backend = 'widget'
    resolved = _resolve_backend(backend)

    parsed = convert_pairs(name_imgrid_images(*images, titles=titles))
    prep_kwargs = dict(
        grid=grid,
        transp=transp,
        cmap=cmap,
        clim=clim_arg,
        max_pixels=max_pixels,
        max_total_pixels=max_total_pixels,
        resize=resize,
        cbar=cbar,
        ticks=ticks,
        figsize=resolved_figsize,
        max_zoom=max_zoom,
        downsample=downsample,
    )
    prepared = prepare_grid_from_parsed(parsed, **prep_kwargs)
    widget = ImageGridWidget.create(
        prepared,
        cbar=cbar,
        ticks=ticks,
        hist=hist,
        window_title=window_title,
        inspect=inspect,
        show_grid=show_grid,
        adj_clim=adj_clim,
    )
    ui = widget
    if resolved == 'marimo':
        import marimo as mo

        ui = mo.ui.anywidget(widget)
    result = ImageGrid(
        widget,
        prepared,
        backend=resolved,
        ui=ui,
        prep_kwargs=prep_kwargs,
    )

    if out:
        payload = {
            'widget': result.widget,
            'ui': result.ui,
            'images': result.images,
            'grid': result,
            'fig': result.widget,
        }
        if out is True:
            out = 'grid'
        if out == 'all':
            return namedtuple('ImviewOut', payload.keys())(**payload)
        if out in payload:
            return payload[out]
    return result
