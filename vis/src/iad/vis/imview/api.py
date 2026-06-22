"""Public API: imgrid facade and ImageGrid wrapper."""

from __future__ import annotations

from collections import namedtuple
from typing import Any, Literal

from iad.vis.imview.data import PreparedGrid, parse_imgrid_images, prepare_grid_from_parsed
from iad.vis.imview.widget import ImageGridWidget


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


class ImageGrid:
    """Wrapper around :class:`ImageGridWidget` with host display protocols."""

    def __init__(self, widget: Any, prepared: PreparedGrid, *, backend: str, ui: Any = None):
        self.widget = widget
        self.images = prepared.images
        self.panels = prepared.panels
        self.backend = backend
        self.ui = ui if ui is not None else widget

    @property
    def value(self) -> dict[str, Any]:
        return self.widget.value

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
    max_pixels: int = 400_000,
    max_total_pixels: int | None = None,
    height: int | None = None,
    width: int | None = None,
    backend: Literal['auto', 'marimo', 'jupyter', 'widget', 'figure'] = 'auto',
    out: bool | Literal['widget', 'ui', 'images', 'all', 'fig'] = False,
    mosaic: bool | str | None = None,
    **imkw,
) -> ImageGrid | Any:
    """Interactive image grid for marimo / Jupyter via anywidget.

    Pixel data is sent once as binary buffers; colormap, clim, zoom and hover
    run client-side in the browser.
    """
    if mosaic:
        cbar, ticks = False, ''
        if mosaic != 'titles':
            titles = [''] * len(images)
    if not set(ticks).issubset('xy'):
        raise TypeError("String argument `ticks` may only include 'x' or 'y' letters.")

    imkw.pop('cap', None)
    imkw.pop('fsz', None)
    imkw.pop('figsize', None)
    clim_arg = imkw.pop('clim', clim)
    _ = height, width, labels

    if backend == 'figure':
        backend = 'widget'
    resolved = _resolve_backend(backend)
    n_images = len(images)
    if max_total_pixels is not None and n_images:
        max_pixels = max(1, min(max_pixels, max_total_pixels // n_images))

    parsed = parse_imgrid_images(*images, titles=titles)
    prepared = prepare_grid_from_parsed(
        parsed,
        grid=grid,
        transp=transp,
        cmap=cmap,
        clim=clim_arg,
        max_pixels=max_pixels,
    )
    widget = ImageGridWidget.create(
        prepared,
        cbar=cbar,
        ticks=ticks,
        hist=hist,
        window_title=window_title,
        inspect=inspect,
    )
    ui = widget
    if resolved == 'marimo':
        import marimo as mo

        ui = mo.ui.anywidget(widget)
    result = ImageGrid(widget, prepared, backend=resolved, ui=ui)

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
