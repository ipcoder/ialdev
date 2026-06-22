"""Plotly-based image grid for notebooks (marimo, Jupyter, static HTML).

Mirrors the API of :func:`iad.vis.insight.imgrid` but renders with Plotly so
colormap, clim, zoom/pan and hover happen client-side after the pixel data is
sent once.
"""

from __future__ import annotations

__all__ = ['imgrid', 'NbImgrid', 'build_figure', 'mpl_to_plotly_colorscale']

from collections import namedtuple
from typing import Any, Literal

import numpy as np

from iad.vis.insight import (
    KeyProcessor,
    MosaicParser,
    _assign_cmaps,
    _optimal_fig_size,
    _to_clim_list,
    assign_args_names,
    convert_image_data,
    grid_layout,
    title_str,
)

_CMAP_MENU = tuple(KeyProcessor.cmaps.values())
_DPI = 96
# Plotly heatmaps embed every z value as JSON text (~10–20 bytes/pixel). Without
# downsampling, a few full-resolution panels routinely exceed marimo's output cap.
_DEFAULT_MAX_PIXELS = 400_000
_DEFAULT_MAX_TOTAL_PIXELS = 800_000
_MARIMO_MAX_TOTAL_PIXELS = 500_000


def _require_plotly():
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError as exc:
        raise ImportError(
            'plgrid requires plotly. Install with: pip install "ialdev-vis[notebook]"'
        ) from exc
    return go, make_subplots


def _registered_cmap_names() -> list[str]:
    import matplotlib.pyplot as plt

    names: list[str] = []
    for name in _CMAP_MENU:
        try:
            plt.get_cmap(name)
        except (ValueError, TypeError):
            continue
        names.append(name)
    return names


def mpl_to_plotly_colorscale(cmap: Any, n: int = 256) -> list[list[float | str]]:
    """Convert a matplotlib colormap name or object to a Plotly colorscale."""
    import matplotlib.pyplot as plt

    if hasattr(cmap, '__call__'):
        cm = cmap
    else:
        try:
            cm = plt.get_cmap(cmap)
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Unknown matplotlib colormap: {cmap!r}') from exc
    samples = cm(np.linspace(0.0, 1.0, n))
    scale: list[list[float | str]] = []
    for idx, rgba in enumerate(samples):
        r, g, b = (int(255 * c) for c in rgba[:3])
        scale.append([idx / max(n - 1, 1), f'rgb({r},{g},{b})'])
    return scale


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
    return 'figure'


def _is_grayscale_rgb(image: np.ndarray) -> bool:
    if image.ndim != 3 or image.shape[2] < 3:
        return False
    return bool(
        np.all(image[:, :, 0] == image[:, :, 1])
        and np.all(image[:, :, 0] == image[:, :, 2])
    )


def _is_rgb_image(image: np.ndarray) -> bool:
    return image.ndim == 3 and image.shape[2] in (3, 4) and not _is_grayscale_rgb(image)


def _downsample_image(image: np.ndarray, max_pixels: int) -> np.ndarray:
    h, w = image.shape[:2]
    if h * w <= max_pixels:
        return image
    factor = int(np.ceil(np.sqrt(h * w / max_pixels)))
    if image.ndim == 2:
        view = image.reshape(h // factor, factor, w // factor, factor)
        return view.mean(axis=(1, 3))
    view = image.reshape(h // factor, factor, w // factor, factor, image.shape[2])
    return view.mean(axis=(1, 3)).astype(image.dtype)


def _prepare_image(image: np.ndarray, max_pixels: int) -> np.ndarray:
    if _is_grayscale_rgb(image):
        image = image[:, :, 0]
    return _downsample_image(image, max_pixels)


def _pixel_budget_per_image(
    n_images: int,
    *,
    max_pixels: int,
    max_total_pixels: int | None,
    backend: str,
) -> int:
    """Per-panel pixel cap balancing quality vs notebook wire size."""
    if max_total_pixels is None:
        use_marimo_cap = backend == 'marimo' or (backend == 'auto' and _in_marimo())
        total = _MARIMO_MAX_TOTAL_PIXELS if use_marimo_cap else _DEFAULT_MAX_TOTAL_PIXELS
    else:
        total = max_total_pixels
    return max(1, min(max_pixels, total // max(n_images, 1)))


def _grid_shape(grid: tuple[int, int] | MosaicParser) -> tuple[int, int]:
    if isinstance(grid, MosaicParser):
        return grid.shape
    return grid


def _axis_ids(row: int, col: int, ncols: int) -> tuple[str, str]:
    axis_num = (row - 1) * ncols + col
    if axis_num == 1:
        return 'x', 'y'
    return f'x{axis_num}', f'y{axis_num}'


def _mosaic_subplot_map(grid: MosaicParser) -> dict[str, tuple[int, int]]:
    positions: dict[str, tuple[int, int]] = {}
    for row_idx, row in enumerate(grid.layout, start=1):
        for col_idx, symbol in enumerate(row, start=1):
            if symbol == '.':
                continue
            base = symbol[0]
            if base.isupper():
                positions[symbol] = (row_idx, col_idx)
    return positions


def _figure_size_px(
    shape: tuple[int, int],
    im_shape: tuple[int, ...],
    height: int | None,
    width: int | None,
) -> tuple[int, int]:
    if height is not None and width is not None:
        return height, width
    fig_w_in, fig_h_in = _optimal_fig_size(shape, im_shape)
    return int(fig_h_in * _DPI), int(fig_w_in * _DPI)


def _finite_values(image: np.ndarray) -> np.ndarray:
    data = image.astype(float, copy=False)
    return data[np.isfinite(data)]


def _clim_steps(
    panel_data: list[tuple[np.ndarray, tuple[float, float]]],
    heatmap_trace_indices: list[int],
    steps: int = 16,
) -> list[dict]:
    slider_steps: list[dict] = []
    for pct in np.linspace(0, 45, steps):
        args_zmin: list[float | None] = []
        args_zmax: list[float | None] = []
        for image, clim in panel_data:
            finite = _finite_values(image)
            if finite.size == 0:
                zmin, zmax = clim
            else:
                zmin = float(np.percentile(finite, pct))
                zmax = float(np.percentile(finite, 100 - pct))
            args_zmin.append(zmin)
            args_zmax.append(zmax)
        slider_steps.append(
            dict(
                method='restyle',
                args=[{'zmin': args_zmin, 'zmax': args_zmax}, heatmap_trace_indices],
                label=f'{pct:.0f}%',
            )
        )
    return slider_steps


def _cmap_buttons(
    cmap_names: list[str],
    heatmap_trace_indices: list[int],
) -> list[dict]:
    buttons: list[dict] = []
    n = len(heatmap_trace_indices)
    for name in cmap_names:
        colorscale = mpl_to_plotly_colorscale(name)
        buttons.append(
            dict(
                label=name,
                method='restyle',
                args=[{'colorscale': [colorscale] * n}, heatmap_trace_indices],
            )
        )
    return buttons


def _add_histogram_trace(
    fig: Any,
    go: Any,
    image: np.ndarray,
    row: int,
    col: int,
    clim: tuple[float, float] | None,
    bins: int,
) -> None:
    finite = _finite_values(image)
    if finite.size == 0:
        return
    mx = clim[1] if clim else float(finite.max())
    data = finite[finite <= mx]
    counts, edges = np.histogram(data, bins=bins)
    if counts.max() == 0:
        return
    centers = (edges[:-1] + edges[1:]) / 2
    scale = image.shape[0] * 0.12 / counts.max()
    fig.add_trace(
        go.Bar(
            x=centers,
            y=counts * scale,
            marker=dict(color='rgba(180,255,130,0.55)'),
            showlegend=False,
            hoverinfo='skip',
        ),
        row=row,
        col=col,
    )


def _pixel_value(image: np.ndarray, x: int, y: int) -> float | tuple | str:
    h, w = image.shape[:2]
    if x < 0 or y < 0 or x >= w or y >= h:
        return '—'
    if image.ndim == 2:
        val = image[y, x]
    else:
        val = image[y, x]
        if image.shape[2] >= 3:
            val = tuple(image[y, x, : min(3, image.shape[2])].tolist())
    if isinstance(val, (float, np.floating)):
        if not np.isfinite(val):
            return 'nan'
        return float(val)
    return val


def _format_readout(
    x: int,
    y: int,
    images: list[tuple[np.ndarray, Any]],
) -> str:
    lines = [f'({y}, {x})']
    for image, title in images:
        val = _pixel_value(image, x, y)
        if isinstance(val, float):
            lines.append(f'{title_str(title)}: {val:5.2f}')
        else:
            lines.append(f'{title_str(title)}: {val}')
    return '\n'.join(lines)


def build_figure(
    images: list[tuple[np.ndarray, Any]],
    *,
    grid: tuple[int, int] | MosaicParser,
    clims: list[tuple[float, float]],
    cmaps: list[Any],
    cbar: bool = True,
    ticks: str = 'xy',
    hist: bool | int | None = False,
    window_title: str | None = None,
    cmap_menu: bool = True,
    clim_slider: bool = True,
    height: int | None = None,
    width: int | None = None,
    max_pixels: int = 2_000_000,
) -> Any:
    """Build a client-interactive Plotly figure for a list of images."""
    go, make_subplots = _require_plotly()
    prepared = [(_prepare_image(image, max_pixels), title) for image, title in images]
    shape = _grid_shape(grid)
    fig_height, fig_width = _figure_size_px(shape, prepared[0][0].shape, height, width)

    if isinstance(grid, MosaicParser):
        specs = [[{} if sym != '.' else None for sym in row] for row in grid.layout]
        title_by_symbol = {code: title_str(title) for code, (_, title) in zip(grid.images, images)}
        mosaic_titles: list[str] = []
        for row in grid.layout:
            for sym in row:
                if sym == '.':
                    mosaic_titles.append('')
                elif sym[0].isupper():
                    mosaic_titles.append(title_by_symbol.get(sym, sym))
                else:
                    mosaic_titles.append('')
        fig = make_subplots(
            rows=int(shape[0]),
            cols=int(shape[1]),
            specs=specs,
            subplot_titles=mosaic_titles,
            horizontal_spacing=0.03,
            vertical_spacing=0.06,
        )
        positions = _mosaic_subplot_map(grid)
        panel_positions = [positions[code] for code in grid.images]
    else:
        rows, cols = int(grid[0]), int(grid[1])
        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[title_str(title) for _, title in images],
            shared_xaxes=True,
            shared_yaxes=True,
            horizontal_spacing=0.03,
            vertical_spacing=0.06,
        )
        panel_positions = []
        for idx in range(len(images)):
            panel_positions.append((idx // cols + 1, idx % cols + 1))

    heatmap_trace_indices: list[int] = []
    shared_clim = len({clim for clim in clims if clim}) == 1 and len(clims) > 1

    for panel_idx, ((image, _title), clim, cmap_name, (row, col)) in enumerate(
        zip(prepared, clims, cmaps, panel_positions)
    ):
        showscale = bool(cbar) and (panel_idx == 0 if shared_clim else True)
        if _is_rgb_image(image):
            if image.dtype != np.uint8:
                rgb = image
                if rgb.max() <= 1.0:
                    rgb = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
                else:
                    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
            else:
                rgb = image
            fig.add_trace(
                go.Image(z=rgb),
                row=row,
                col=col,
            )
        else:
            colorscale = mpl_to_plotly_colorscale(cmap_name)
            zmin, zmax = clim if clim else (None, None)
            fig.add_trace(
                go.Heatmap(
                    z=image,
                    colorscale=colorscale,
                    zmin=zmin,
                    zmax=zmax,
                    showscale=showscale,
                    colorbar=dict(title='') if showscale else None,
                    hovertemplate='x=%{x}<br>y=%{y}<br>val=%{z:.4g}<extra></extra>',
                ),
                row=row,
                col=col,
            )
            heatmap_trace_indices.append(len(fig.data) - 1)

        if hist:
            bins = 32 if hist is True else int(hist)
            _add_histogram_trace(fig, go, image, row, col, clim, bins)

        x_id, _y_id = _axis_ids(row, col, shape[1])
        fig.update_yaxes(
            autorange='reversed',
            scaleanchor=x_id,
            scaleratio=1,
            showticklabels='y' in ticks,
            row=row,
            col=col,
        )
        fig.update_xaxes(
            showticklabels='x' in ticks,
            row=row,
            col=col,
        )

    if not isinstance(grid, MosaicParser):
        fig.update_xaxes(matches='x')
        fig.update_yaxes(matches='y')

    layout_kwargs: dict[str, Any] = dict(
        height=fig_height,
        width=fig_width,
        margin=dict(l=20, r=20, t=60 if window_title else 40, b=20),
    )
    if window_title:
        layout_kwargs['title'] = dict(text=window_title)
    menus: list[dict] = []
    if cmap_menu and heatmap_trace_indices:
        cmap_names = list(dict.fromkeys([str(c) for c in cmaps] + _registered_cmap_names()))
        menus.append(
            dict(
                type='dropdown',
                direction='down',
                x=0.01,
                y=1.12,
                xanchor='left',
                yanchor='top',
                showactive=True,
                buttons=_cmap_buttons(cmap_names, heatmap_trace_indices),
            )
        )
    if menus:
        layout_kwargs['updatemenus'] = menus
    if clim_slider and heatmap_trace_indices:
        panel_data = [
            (image, clims[idx])
            for idx, (image, _) in enumerate(prepared)
            if not _is_rgb_image(image)
        ]
        clim_step_list = _clim_steps(panel_data, heatmap_trace_indices)
        layout_kwargs['sliders'] = [
            dict(
                active=len(clim_step_list) // 2,
                x=0.12,
                y=1.08,
                len=0.85,
                pad=dict(t=30),
                currentvalue=dict(prefix='clim tail: '),
                steps=clim_step_list,
            )
        ]
    fig.update_layout(**layout_kwargs)
    return fig


class NbImgrid:
    """Notebook image grid wrapper with host-specific display adapters."""

    def __init__(
        self,
        figure: Any,
        images: list[tuple[np.ndarray, Any]],
        *,
        backend: str,
        inspect_enabled: bool,
        ui: Any = None,
        readout: Any = None,
    ):
        self.figure = figure
        self.images = images
        self.backend = backend
        self.inspect_enabled = inspect_enabled
        self.ui = ui
        self.readout = readout
        self._selection: dict[str, Any] = {}

    @property
    def value(self) -> dict[str, Any]:
        return dict(self._selection)

    @property
    def readout_text(self) -> str | None:
        if self.ui is None or not hasattr(self.ui, 'points'):
            return None
        points = self.ui.points
        if not points:
            return None
        point = points[0]
        x = int(round(point.get('x', 0)))
        y = int(round(point.get('y', 0)))
        return _format_readout(x, y, self.images)

    def show(self) -> None:
        self.figure.show()

    def _display_(self) -> Any:
        import marimo as mo

        if self.ui is None:
            return mo.as_html(self.figure)
        text = self.readout_text
        if text:
            return mo.vstack([self.ui, mo.md(f'```\n{text}\n```')], gap=1)
        hint = 'Click a panel to inspect pixel values across axes.'
        return mo.vstack([self.ui, mo.md(hint)], gap=1)

    def _ipython_display_(self) -> None:
        from IPython.display import display

        if self.readout is not None:
            display(self.readout)
        display(self.ui if self.ui is not None else self.figure)

    def _repr_mimebundle_(self, include=None, exclude=None):
        from IPython.display import display

        bundle: dict[str, Any] = {}
        try:
            import plotly.io as pio

            bundle['text/html'] = pio.to_html(
                self.ui if self.ui is not None else self.figure,
                include_plotlyjs='cdn',
                full_html=False,
            )
        except Exception:
            bundle['text/plain'] = repr(self)
        return bundle


def _wrap_marimo(
    fig: Any,
    images: list[tuple[np.ndarray, Any]],
    *,
    inspect_enabled: bool,
) -> NbImgrid:
    import marimo as mo

    plot_ui = mo.ui.plotly(fig)
    return NbImgrid(
        fig,
        images,
        backend='marimo',
        inspect_enabled=inspect_enabled,
        ui=plot_ui,
        readout=mo.md('') if inspect_enabled else None,
    )


def _wrap_jupyter(
    fig: Any,
    images: list[tuple[np.ndarray, Any]],
    *,
    inspect_enabled: bool,
) -> NbImgrid:
    go, _ = _require_plotly()
    try:
        fig_widget = go.FigureWidget(fig)
    except ImportError:
        return NbImgrid(fig, images, backend='jupyter', inspect_enabled=False, ui=fig)
    readout = None
    if inspect_enabled:
        try:
            import ipywidgets as widgets
        except ImportError:
            return NbImgrid(fig, images, backend='jupyter', inspect_enabled=False, ui=fig_widget)
        readout = widgets.HTML(value='<i>Click a panel to inspect pixel values across axes.</i>')
        image_traces = [trace for trace in fig_widget.data if trace.type in ('heatmap', 'image')]

        def _on_click(trace: Any, points: Any, state: Any) -> None:
            if not points.xs or not points.ys:
                return
            x = int(round(points.xs[0]))
            y = int(round(points.ys[0]))
            text = _format_readout(x, y, images).replace('\n', '<br>')
            readout.value = f'<pre>{text}</pre>'

        for trace in image_traces:
            trace.on_click(_on_click)
    return NbImgrid(fig, images, backend='jupyter', inspect_enabled=inspect_enabled, ui=fig_widget, readout=readout)


def imgrid(
    *images,
    labels: dict | list[dict] = None,
    titles: list[str] | None = None,
    grid: str | tuple | list | MosaicParser = 'auto',
    transp: bool = False,
    cmap: str | list[str] = 'rain',
    cbar: bool = True,
    clim: Any = 'auto',
    ticks: str = 'xy',
    hist: bool | int | None = False,
    window_title: str | None = None,
    inspect: bool = True,
    cmap_menu: bool = True,
    clim_slider: bool = True,
    max_pixels: int = _DEFAULT_MAX_PIXELS,
    max_total_pixels: int | None = None,
    height: int | None = None,
    width: int | None = None,
    backend: Literal['auto', 'marimo', 'jupyter', 'figure'] = 'auto',
    out: bool | Literal['fig', 'ui', 'images', 'all'] = False,
    mosaic: bool | str | None = None,
    adj_clim: bool | None = None,
    **imkw,
) -> NbImgrid | Any | None:
    """Show titled images in a Plotly grid for notebook environments.

    Mirrors :func:`iad.vis.insight.imgrid` argument parsing. Rendering and most
    interactions are client-side; host adapters add cross-axes pixel inspection.

    Plotly serialises scalar images as heatmap ``z`` arrays in JSON, so wire size
    grows quickly with resolution × panel count. Use ``max_pixels`` (per panel) and
    ``max_total_pixels`` (split across all panels) to stay within marimo/Jupyter
    output limits. In marimo the total budget defaults to a stricter cap.
    """
    if mosaic:
        cbar, ticks = False, ''
        if mosaic != 'titles':
            titles = [''] * len(images)
    if adj_clim is not None:
        clim_slider = adj_clim
    if not set(ticks).issubset('xy'):
        raise TypeError("String argument `ticks` may only include 'x' or 'y' letters.")

    imkw.pop('cap', None)
    imkw.pop('fsz', None)
    imkw.pop('figsize', None)
    clim_arg = imkw.pop('clim', clim)

    parsed = assign_args_names(
        images,
        names=titles,
        func_name='imgrid',
        nest_level=1,
        enum_form='Stream_{}',
    )
    parsed = [convert_image_data(*item) for item in parsed]
    grid_spec = grid_layout(len(parsed), grid, transp)
    clims = _to_clim_list(clim_arg, parsed)
    cmaps = _assign_cmaps(cmap, len(parsed))

    if transp and not isinstance(grid_spec, MosaicParser):
        from iad.core.datatools import transpose

        grid_spec = grid_spec[::-1]
        parsed, clims, cmaps = map(
            lambda seq: transpose(seq, int(grid_spec[0])),
            (parsed, clims, cmaps),
        )

    if labels:
        pass

    resolved = _resolve_backend(backend)
    panel_pixels = _pixel_budget_per_image(
        len(parsed),
        max_pixels=max_pixels,
        max_total_pixels=max_total_pixels,
        backend=resolved if backend != 'auto' else 'auto',
    )

    fig = build_figure(
        parsed,
        grid=grid_spec,
        clims=clims,
        cmaps=cmaps,
        cbar=cbar,
        ticks=ticks,
        hist=hist,
        window_title=window_title,
        cmap_menu=cmap_menu,
        clim_slider=clim_slider,
        height=height,
        width=width,
        max_pixels=panel_pixels,
    )
    if resolved == 'marimo':
        result = _wrap_marimo(fig, parsed, inspect_enabled=inspect)
    elif resolved == 'jupyter':
        result = _wrap_jupyter(fig, parsed, inspect_enabled=inspect)
    else:
        result = NbImgrid(fig, parsed, backend='figure', inspect_enabled=False)

    if out:
        payload = {
            'fig': result.figure,
            'ui': result.ui,
            'images': result.images,
            'nb': result,
        }
        if out is True:
            out = 'nb'
        if out == 'all':
            return namedtuple('PlgridOut', payload.keys())(**payload)
        if out in payload:
            return payload[out]
        if out == 'fig':
            return result.figure
        if out == 'ui':
            return result.ui
        if out == 'images':
            return result.images
    return result
