"""Parse imgrid inputs and pack binary panel buffers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from iad.vis.insight import (
    MosaicParser,
    _assign_cmaps,
    _to_clim_list,
    assign_args_names,
    convert_image_data,
    grid_layout,
    title_str,
)


def _is_grayscale_rgb(image: np.ndarray) -> bool:
    if image.ndim != 3 or image.shape[2] < 3:
        return False
    return bool(
        np.all(image[:, :, 0] == image[:, :, 1])
        and np.all(image[:, :, 0] == image[:, :, 2])
    )


def _is_rgb_image(image: np.ndarray) -> bool:
    return image.ndim == 3 and image.shape[2] in (3, 4) and not _is_grayscale_rgb(image)


def downsample_image(image: np.ndarray, max_pixels: int) -> np.ndarray:
    h, w = image.shape[:2]
    if h * w <= max_pixels:
        return image
    factor = int(np.ceil(np.sqrt(h * w / max_pixels)))
    factor = max(factor, 1)
    h_trim = (h // factor) * factor
    w_trim = (w // factor) * factor
    image = image[:h_trim, :w_trim]
    if image.ndim == 2:
        view = image.reshape(h_trim // factor, factor, w_trim // factor, factor)
        return view.mean(axis=(1, 3))
    view = image.reshape(
        h_trim // factor, factor, w_trim // factor, factor, image.shape[2]
    )
    return view.mean(axis=(1, 3)).astype(image.dtype)


def prepare_image(image: np.ndarray, max_pixels: int) -> np.ndarray:
    if _is_grayscale_rgb(image):
        image = image[:, :, 0]
    return downsample_image(image, max_pixels)


@dataclass
class PanelData:
    id: int
    title: str
    kind: str
    width: int
    height: int
    cmap: str
    clim: list[float | None]
    buffer: np.ndarray


@dataclass
class PreparedGrid:
    panels: list[PanelData]
    grid: list[int]
    images: list[tuple[np.ndarray, Any]]
    cmaps: list[str]


def _grid_dims(grid_spec: tuple[int, int] | MosaicParser, n_panels: int) -> tuple[int, int]:
    if isinstance(grid_spec, MosaicParser):
        return int(grid_spec.shape[0]), int(grid_spec.shape[1])
    return int(grid_spec[0]), int(grid_spec[1])


def _pack_scalar(image: np.ndarray) -> np.ndarray:
    data = np.ascontiguousarray(image, dtype=np.float32)
    return data


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
    max_pixels: int = 400_000,
) -> PreparedGrid:
    grid_spec = grid_layout(len(parsed), grid, transp)
    clims = _to_clim_list(clim, parsed)
    cmaps = _assign_cmaps(cmap, len(parsed))

    if transp and not isinstance(grid_spec, MosaicParser):
        from iad.core.datatools import transpose

        grid_spec = grid_spec[::-1]
        parsed, clims, cmaps = map(
            lambda seq: transpose(seq, int(grid_spec[0])),
            (parsed, clims, cmaps),
        )

    rows, cols = _grid_dims(grid_spec, len(parsed))
    panels: list[PanelData] = []
    for idx, ((image, title), clm, cm) in enumerate(zip(parsed, clims, cmaps)):
        prepared = prepare_image(image, max_pixels)
        h, w = prepared.shape[:2]
        if _is_rgb_image(prepared):
            kind = 'rgb'
            buffer = _pack_rgb(prepared)
        else:
            kind = 'scalar'
            buffer = _pack_scalar(prepared)
        lo, hi = clm if clm else (None, None)
        panels.append(
            PanelData(
                id=idx,
                title=title_str(title),
                kind=kind,
                width=w,
                height=h,
                cmap=str(cm),
                clim=[float(lo) if lo is not None else None, float(hi) if hi is not None else None],
                buffer=buffer,
            )
        )
    return PreparedGrid(
        panels=panels,
        grid=[rows, cols],
        images=parsed,
        cmaps=[str(c) for c in cmaps],
    )


def parse_imgrid_images(
    *images,
    titles: list[str] | None = None,
) -> list[tuple[np.ndarray, Any]]:
    parsed = assign_args_names(
        images,
        names=titles,
        func_name='imgrid',
        nest_level=2,
        enum_form='Stream_{}',
    )
    return [convert_image_data(*item) for item in parsed]


def prepare_grid(
    *images,
    titles: list[str] | None = None,
    grid: str | tuple | list | MosaicParser = 'auto',
    transp: bool = False,
    cmap: str | list[str] = 'rain',
    clim: Any = 'auto',
    max_pixels: int = 400_000,
) -> PreparedGrid:
    parsed = parse_imgrid_images(*images, titles=titles)
    return prepare_grid_from_parsed(
        parsed,
        grid=grid,
        transp=transp,
        cmap=cmap,
        clim=clim,
        max_pixels=max_pixels,
    )
