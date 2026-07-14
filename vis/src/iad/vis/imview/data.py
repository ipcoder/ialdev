"""Parse imgrid inputs, compute layout, and pack binary panel buffers.

This module is the Python-side preparation pipeline for :mod:`iad.vis.imview`.
It converts raw arrays into :class:`PreparedGrid` payloads: per-panel binary
buffers (downsampled once), display-space layout rects, color limits, and byte
accounting for the toolbar readout.

Layout is computed in reference CSS pixels (not image samples). Panel aspect
ratios match the source images. :func:`prepare_grid_from_parsed` chooses an
integer downsample factor per panel from ``figsize``, ``max_zoom``,
``downsample``, or ``max_pixels`` budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from iad.vis.gridcore import (
    MosaicParser,
    _assign_cmaps,
    _resize_images,
    _to_clim_list,
    assign_args_names,
    convert_image_data,
    grid_layout,
    title_str,
)

_PAD = 8
_TITLE_H = 15
_CBAR_W = 7
_CBAR_LABEL_W = 28
_YLABEL_W = 20
_XLABEL_H = 13
_BASE_PANEL_H = 120
_MIN_PANEL_PX = 240
_MAX_CANVAS_W = 960
_MAX_CANVAS_H = 720
_BYTES_PER_PIXEL = 4


def _is_grayscale_rgb(image: np.ndarray) -> bool:
    if image.ndim != 3 or image.shape[2] < 3:
        return False
    return bool(
        np.all(image[:, :, 0] == image[:, :, 1])
        and np.all(image[:, :, 0] == image[:, :, 2])
    )


def _is_rgb_image(image: np.ndarray) -> bool:
    return image.ndim == 3 and image.shape[2] in (3, 4) and not _is_grayscale_rgb(image)


def _collapse_grayscale(image: np.ndarray) -> np.ndarray:
    if _is_grayscale_rgb(image):
        return image[:, :, 0]
    return image


def downsample_by_factor(image: np.ndarray, factor: int) -> np.ndarray:
    """Block-mean downsample by an integer factor along H and W.

    Trims trailing rows/columns so dimensions are divisible by ``factor``.
    Scalar arrays become ``float32``; RGB arrays keep their dtype.
    """
    factor = max(1, int(factor))
    if factor <= 1:
        return image
    h, w = image.shape[:2]
    h_trim = (h // factor) * factor
    w_trim = (w // factor) * factor
    image = image[:h_trim, :w_trim]
    if image.ndim == 2:
        view = image.reshape(h_trim // factor, factor, w_trim // factor, factor)
        return view.mean(axis=(1, 3)).astype(np.float32)
    view = image.reshape(
        h_trim // factor, factor, w_trim // factor, factor, image.shape[2],
    )
    return view.mean(axis=(1, 3)).astype(image.dtype)


def downsample_image(image: np.ndarray, max_pixels: int) -> np.ndarray:
    """Downsample until ``height * width <= max_pixels`` (auto factor)."""
    h, w = image.shape[:2]
    if h * w <= max_pixels:
        return image
    factor = int(np.ceil(np.sqrt(h * w / max_pixels)))
    return downsample_by_factor(image, max(factor, 1))


def _auto_downsample_factor(src_w: int, src_h: int, max_pixels: int) -> int:
    total = src_w * src_h
    if total <= max_pixels:
        return 1
    return int(np.ceil(np.sqrt(total / max_pixels)))


def _choose_downsample_factor(
    src_w: int,
    src_h: int,
    panel_w: int,
    panel_h: int,
    *,
    downsample: int | None,
    max_zoom: float | Literal['full'] | None,
    max_pixels: int,
) -> int:
    if downsample is not None:
        return max(1, int(downsample))
    if max_zoom == 'full':
        return 1
    if max_zoom is not None:
        zoom = max(1.0, float(max_zoom))
        target_w = max(1, int(np.ceil(panel_w * zoom)))
        target_h = max(1, int(np.ceil(panel_h * zoom)))
        factor_w = src_w // target_w
        factor_h = src_h // target_h
        return max(1, int(min(factor_w, factor_h)))
    return _auto_downsample_factor(src_w, src_h, max_pixels)


def _panel_byte_size(width: int, height: int) -> int:
    return width * height * _BYTES_PER_PIXEL


@dataclass
class PanelData:
    """One panel's packed buffer and layout metadata for the frontend."""

    id: int
    title: str
    kind: str  # 'scalar' | 'rgb'
    width: int  # buffer width (after downsample)
    height: int  # buffer height (after downsample)
    cmap: str
    clim: list[float | None]
    buffer: np.ndarray
    layout: dict[str, int] = field(default_factory=dict)  # x, y, w, h in reference px
    cbar: dict[str, int] | None = None
    source_width: int = 0  # original image width before downsample
    source_height: int = 0
    factor: int = 1  # integer downsample factor applied in Python
    sent_bytes: int = 0  # bytes sent for this panel buffer
    full_bytes: int = 0  # bytes at full source resolution


@dataclass
class PreparedGrid:
    """Fully prepared grid payload consumed by :class:`~iad.vis.imview.widget.ImageGridWidget`."""

    panels: list[PanelData]
    grid: list[int]  # [rows, cols]
    images: list[tuple[np.ndarray, Any]]  # resized source arrays + titles
    cmaps: list[str]
    canvas_size: tuple[int, int] = (320, 200)  # reference CSS px (w, h)
    sent_bytes: int = 0
    full_bytes: int = 0
    sent_pixels: int = 0
    full_pixels: int = 0
    data_over_budget: bool = False  # True when explicit max_zoom/downsample exceeds max_pixels
    source_ref: list[tuple[Any, tuple[int, ...]]] = field(default_factory=list)


def _grid_dims(grid_spec: tuple[int, int] | MosaicParser, n_panels: int) -> tuple[int, int]:
    if isinstance(grid_spec, MosaicParser):
        return int(grid_spec.shape[0]), int(grid_spec.shape[1])
    return int(grid_spec[0]), int(grid_spec[1])


def _cell_placements(
    grid_spec: tuple[int, int] | MosaicParser,
    n_panels: int,
) -> list[tuple[int, int, int, int]]:
    """Return (row, col, row_span, col_span) for each panel."""
    if isinstance(grid_spec, MosaicParser):
        layout = grid_spec.layout
        placements: list[tuple[int, int, int, int]] = []
        for symbol in grid_spec.images[:n_panels]:
            cells = [
                (r, c)
                for r, row in enumerate(layout)
                for c, sym in enumerate(row)
                if sym == symbol
            ]
            if not cells:
                raise ValueError(f'Symbol {symbol!r} not found in mosaic layout')
            rows = [r for r, _ in cells]
            cols = [c for _, c in cells]
            row0, row1 = min(rows), max(rows)
            col0, col1 = min(cols), max(cols)
            placements.append((row0, col0, row1 - row0 + 1, col1 - col0 + 1))
        return placements
    rows, cols = int(grid_spec[0]), int(grid_spec[1])
    return [(i // cols, i % cols, 1, 1) for i in range(n_panels)]


def _dims_from_height(aspect: float, h: float, min_px: int = _MIN_PANEL_PX) -> tuple[int, int]:
    """Integer (w, h) with w derived from h so w/h best matches `aspect`.

    Enforces the `min_px` floor on both dimensions while keeping the source
    aspect ratio: if either dimension would fall below the floor, the panel is
    grown (never squashed) so the ratio is preserved.
    """
    aspect = max(aspect, 1e-6)
    h = max(1.0, float(h))
    w = h * aspect
    if w < min_px:
        w = float(min_px)
        h = w / aspect
    if h < min_px:
        h = float(min_px)
        w = h * aspect
    return max(1, int(round(w))), max(1, int(round(h)))


def _fit_inside_aspect(
    aspect: float,
    max_w: float | None,
    max_h: float | None,
    min_px: int = _MIN_PANEL_PX,
) -> tuple[int, int]:
    aspect = max(aspect, 1e-6)
    if max_w is None and max_h is None:
        return _dims_from_height(aspect, _BASE_PANEL_H, min_px)
    if max_w is not None and max_h is None:
        return _dims_from_height(aspect, float(max_w) / aspect, min_px)
    if max_h is not None and max_w is None:
        return _dims_from_height(aspect, float(max_h), min_px)
    h = float(max_h)
    if h * aspect > max_w:
        h = float(max_w) / aspect
    return _dims_from_height(aspect, h, min_px)


def _panel_display_dims(aspect: float, base_h: int = _BASE_PANEL_H) -> tuple[int, int]:
    """Reference display size preserving source aspect ratio."""
    return _dims_from_height(aspect, base_h)


def _stacked_positions(sizes: list[int], gap: int) -> tuple[list[int], int]:
    """Lay out `sizes` with a uniform `gap` before, between, and after items."""
    starts: list[int] = []
    pos = gap
    for size in sizes:
        starts.append(pos)
        pos += size + gap
    return starts, max(1, pos)


def _row_image_heights(
    placements: list[tuple[int, int, int, int]],
    img_dims: list[tuple[int, int]],
    n_rows: int,
) -> list[int]:
    """Max image height per grid row."""
    heights = [0] * n_rows
    for (r, _c, rs, _cs), (_dw, dh) in zip(placements, img_dims):
        per_row = int(np.ceil(dh / rs))
        for rr in range(r, r + rs):
            heights[rr] = max(heights[rr], per_row)
    return heights


def _vertical_layout(
    row_dhs: list[int],
    *,
    pad: int,
    title_h: int,
    bottom_pad: int,
) -> tuple[list[int], int]:
    """Return (image_y per row, canvas_h) with a shared gutter between rows."""
    n_rows = len(row_dhs)
    gutter = max(title_h, bottom_pad) + pad if n_rows > 1 else 0
    tail = bottom_pad if bottom_pad else 0
    image_y: list[int] = []
    y = pad + title_h
    for r, dh in enumerate(row_dhs):
        image_y.append(y)
        y += dh
        if r < n_rows - 1:
            y += gutter
    canvas_h = y + tail + pad
    return image_y, max(1, canvas_h)


def _display_layout(
    panels: list[PanelData],
    placements: list[tuple[int, int, int, int]],
    aspects: list[float],
    *,
    figsize: tuple[int | None, int | None] | None = None,
    pad: int = _PAD,
    title_h: int = _TITLE_H,
    cbar: bool = True,
    cbar_w: int = _CBAR_W,
    cbar_label_w: int = _CBAR_LABEL_W,
    ticks: str = 'xy',
    ylabel_w: int = _YLABEL_W,
    xlabel_h: int = _XLABEL_H,
    max_canvas_w: int = _MAX_CANVAS_W,
    max_canvas_h: int = _MAX_CANVAS_H,
) -> tuple[list[dict[str, int]], list[dict[str, int] | None], tuple[int, int]]:
    """Compute display-space panel rects (reference CSS px, not image samples)."""
    if not panels:
        return [], [], (320, 200)

    left_pad = ylabel_w if 'y' in ticks else 0
    bottom_pad = xlabel_h if 'x' in ticks else 0
    n_rows = max(r + rs for r, _c, rs, _cs in placements)
    n_cols = max(c + cs for _r, c, _rs, cs in placements)

    def chrome_w(panel: PanelData) -> int:
        if cbar and panel.kind == 'scalar':
            return left_pad + cbar_w + cbar_label_w
        return left_pad

    def measure(img_dims: list[tuple[int, int]]) -> tuple[list[int], list[int], int, int]:
        row_dhs = _row_image_heights(placements, img_dims, n_rows)
        col_widths = [0] * n_cols
        for panel, (_r, c, _rs, cs), (dw, _dh) in zip(panels, placements, img_dims):
            per_col = int(np.ceil((chrome_w(panel) + dw) / cs))
            for cc in range(c, c + cs):
                col_widths[cc] = max(col_widths[cc], per_col)
        col_x, canvas_w = _stacked_positions(col_widths, pad)
        image_y, canvas_h = _vertical_layout(
            row_dhs, pad=pad, title_h=title_h, bottom_pad=bottom_pad,
        )
        return col_x, image_y, max(1, canvas_w), canvas_h

    if figsize is not None:
        fig_w, fig_h = figsize
        _cx, _iy, fix_w, fix_h = measure([(0, 0)] * len(panels))
        avail_w = (fig_w - fix_w) if fig_w is not None else None
        avail_h = (fig_h - fix_h) if fig_h is not None else None
        scaled: list[tuple[int, int]] = []
        for aspect, (_r, c, rs, cs) in zip(aspects, placements):
            box_w = (avail_w / n_cols * cs) if avail_w is not None else None
            box_h = (avail_h / n_rows * rs) if avail_h is not None else None
            scaled.append(_fit_inside_aspect(aspect, box_w, box_h))
        col_x, image_y, canvas_w, canvas_h = measure(scaled)
    else:
        natural = [_panel_display_dims(a) for a in aspects]
        _cx, _iy, nat_w, nat_h = measure(natural)
        _cx, _iy, fix_w, fix_h = measure([(0, 0)] * len(panels))
        img_scale = min(
            1.0,
            (max_canvas_w - fix_w) / (nat_w - fix_w) if nat_w > fix_w else 1.0,
            (max_canvas_h - fix_h) / (nat_h - fix_h) if nat_h > fix_h else 1.0,
        )
        scaled = [
            _dims_from_height(aspect, h * img_scale)
            for aspect, (_w, h) in zip(aspects, natural)
        ]
        col_x, image_y, canvas_w, canvas_h = measure(scaled)

    layouts: list[dict[str, int]] = []
    cbar_rects: list[dict[str, int] | None] = []
    for panel, (r, c, _rs, _cs), (disp_w, disp_h) in zip(panels, placements, scaled):
        region_x = col_x[c] + left_pad
        region_y = image_y[r]
        layouts.append({'x': region_x, 'y': region_y, 'w': disp_w, 'h': disp_h})
        if cbar and panel.kind == 'scalar':
            cbar_rects.append({
                'x': region_x + disp_w,
                'y': region_y,
                'w': cbar_w,
                'h': disp_h,
            })
        else:
            cbar_rects.append(None)

    return layouts, cbar_rects, (canvas_w, canvas_h)


def _pack_scalar(image: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(image, dtype=np.float32)


def _pack_rgb(image: np.ndarray) -> np.ndarray:
    if image.dtype != np.uint8:
        if image.max() <= 1.0:
            rgb = (np.clip(image, 0.0, 1.0) * 255).astype(np.uint8)
        else:
            rgb = np.clip(image, 0, 255).astype(np.uint8)
    else:
        rgb = image
    if rgb.shape[2] == 3:
        alpha = np.full(rgb.shape[:2] + (1,), 255, dtype=np.uint8)
        rgba = np.concatenate([rgb, alpha], axis=2)
    else:
        rgba = rgb
    return np.ascontiguousarray(rgba, dtype=np.uint8)


def prepare_grid_from_parsed(
    parsed: list[tuple[np.ndarray, Any]],
    *,
    grid: str | tuple | list | MosaicParser = 'auto',
    transp: bool = False,
    cmap: str | list[str] = 'rain',
    clim: Any = 'auto',
    max_pixels: int = 500_000,
    max_total_pixels: int | None = None,
    resize: Literal['no', 'up', 'down', 'error'] | bool = 'error',
    cbar: bool = True,
    ticks: str = 'xy',
    figsize: tuple[int | None, int | None] | None = None,
    max_zoom: float | Literal['full'] | None = None,
    downsample: int | None = None,
) -> PreparedGrid:
    """Build a :class:`PreparedGrid` from already-converted ``(array, title)`` pairs.

    Parameters
    ----------
    parsed
        Panel arrays in canonical form (from :func:`convert_pairs`).
    grid, transp, cmap, clim, resize
        Grid layout and display options (shared with :func:`prepare_grid`).
    max_pixels, max_total_pixels
        Per-panel and total pixel budgets for automatic downsampling when
        ``max_zoom`` and ``downsample`` are not set.
    cbar, ticks
        Colorbar and axis tick chrome included in layout measurement.
    figsize
        ``(width, height)`` target for the grid in reference CSS pixels.
        Either dimension may be ``None`` (fit the other). Panel aspect ratios
        match the source images; a 240 px minimum applies per dimension.
    max_zoom
        Crispness headroom: buffer resolution is at least ``panel_size * max_zoom``.
        Use ``'full'`` to send full-resolution buffers (factor 1).
    downsample
        Fixed integer downsample factor (mutually exclusive with ``max_zoom``).

    Returns
    -------
    PreparedGrid
        Layout rects, packed buffers, and byte/pixel accounting for the widget.
    """
    # Caller-facing shapes for update_data; must precede resize.
    source_ref = [(title, im.shape) for im, title in parsed]
    parsed = _resize_images(parsed, resize)
    grid_spec = grid_layout(len(parsed), grid, transp)
    clims = _to_clim_list(clim, parsed)
    cmaps = _assign_cmaps(cmap, len(parsed))

    if transp and not isinstance(grid_spec, MosaicParser):
        from iad.core.datatools import transpose

        grid_spec = grid_spec[::-1]
        parsed, clims, cmaps, source_ref = map(
            lambda seq: transpose(seq, int(grid_spec[0])),
            (parsed, clims, cmaps, source_ref),
        )

    n_panels = len(parsed)
    if max_total_pixels is not None and n_panels:
        max_pixels = max(1, min(max_pixels, max_total_pixels // n_panels))

    rows, cols = _grid_dims(grid_spec, n_panels)
    sources = [_collapse_grayscale(image) for image, _title in parsed]
    aspects = [
        max(src.shape[1], 1) / max(src.shape[0], 1) for src in sources
    ]

    panels: list[PanelData] = []
    for idx, ((image, title), clm, cm, src) in enumerate(
        zip(parsed, clims, cmaps, sources)
    ):
        src_h, src_w = src.shape[:2]
        lo, hi = clm if clm else (None, None)
        panels.append(
            PanelData(
                id=idx,
                title=title_str(title),
                kind='scalar',
                width=src_w,
                height=src_h,
                cmap=str(cm),
                clim=[float(lo) if lo is not None else None, float(hi) if hi is not None else None],
                buffer=np.array([], dtype=np.float32),
                source_width=src_w,
                source_height=src_h,
            )
        )

    placements = _cell_placements(grid_spec, len(panels))
    layouts, cbar_rects, canvas_size = _display_layout(
        panels, placements, aspects, figsize=figsize, cbar=cbar, ticks=ticks,
    )
    for panel, layout, cbar_rect in zip(panels, layouts, cbar_rects):
        panel.layout = layout
        panel.cbar = cbar_rect

    explicit_res = downsample is not None or max_zoom is not None
    sent_bytes = 0
    full_bytes = 0
    sent_pixels = 0
    full_pixels = 0

    for panel, src in zip(panels, sources):
        disp_w = max(1, panel.layout['w'])
        disp_h = max(1, panel.layout['h'])
        factor = _choose_downsample_factor(
            panel.source_width,
            panel.source_height,
            disp_w,
            disp_h,
            downsample=downsample,
            max_zoom=max_zoom,
            max_pixels=max_pixels,
        )
        prepared = downsample_by_factor(src, factor)
        if _is_rgb_image(prepared):
            kind = 'rgb'
            buffer = _pack_rgb(prepared)
        else:
            kind = 'scalar'
            buffer = _pack_scalar(prepared.astype(np.float32, copy=False))
        h, w = prepared.shape[:2]
        panel.kind = kind
        panel.width = w
        panel.height = h
        panel.buffer = buffer
        panel.factor = factor
        panel.sent_bytes = _panel_byte_size(w, h)
        panel.full_bytes = _panel_byte_size(panel.source_width, panel.source_height)
        sent_bytes += panel.sent_bytes
        full_bytes += panel.full_bytes
        sent_pixels += w * h
        full_pixels += panel.source_width * panel.source_height

    over_budget = explicit_res and sent_pixels > max_pixels * n_panels

    return PreparedGrid(
        panels=panels,
        grid=[rows, cols],
        images=parsed,
        cmaps=[str(c) for c in cmaps],
        canvas_size=canvas_size,
        sent_bytes=sent_bytes,
        full_bytes=full_bytes,
        sent_pixels=sent_pixels,
        full_pixels=full_pixels,
        data_over_budget=over_budget,
        source_ref=source_ref,
    )


def name_imgrid_images(
    *images,
    titles: list[str] | None = None,
) -> list[tuple[Any, Any]]:
    """Assign panel titles to raw image arguments (no array conversion)."""
    return assign_args_names(
        images,
        names=titles,
        func_name='imgrid',
        nest_level=2,
        enum_form='Stream_{}',
    )


def convert_pairs(
    titled_pairs: list[tuple[Any, Any]],
) -> list[tuple[np.ndarray, Any]]:
    """Normalize raw arrays to the canonical ``(ndarray, title)`` reference form.

    This is the single conversion step shared by grid creation and updates, so
    both paths produce identically prepared arrays before layout/packing.
    """
    return [convert_image_data(arr, title) for arr, title in titled_pairs]


def prepare_grid(
    *images,
    titles: list[str] | None = None,
    grid: str | tuple | list | MosaicParser = 'auto',
    transp: bool = False,
    cmap: str | list[str] = 'rain',
    clim: Any = 'auto',
    max_pixels: int = 500_000,
    max_total_pixels: int | None = None,
    resize: Literal['no', 'up', 'down', 'error'] | bool = 'error',
    cbar: bool = True,
    ticks: str = 'xy',
    figsize: tuple[int | None, int | None] | None = None,
    max_zoom: float | Literal['full'] | None = None,
    downsample: int | None = None,
) -> PreparedGrid:
    """Prepare a grid from raw image arguments (convenience wrapper).

    Parses ``*images`` with :func:`name_imgrid_images`, converts arrays via
    :func:`convert_pairs`, then delegates to :func:`prepare_grid_from_parsed`.
    Accepts the same layout and downsampling kwargs as that function.
    """
    parsed = convert_pairs(name_imgrid_images(*images, titles=titles))
    return prepare_grid_from_parsed(
        grid=grid,
        transp=transp,
        cmap=cmap,
        clim=clim,
        max_pixels=max_pixels,
        max_total_pixels=max_total_pixels,
        resize=resize,
        cbar=cbar,
        ticks=ticks,
        figsize=figsize,
        max_zoom=max_zoom,
        downsample=downsample,
    )
