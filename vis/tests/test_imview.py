from pathlib import Path

import pytest
from numpy.random import rand

anywidget = pytest.importorskip('anywidget')


def _static_js() -> Path:
    return Path(__file__).resolve().parents[1] / 'src' / 'iad' / 'vis' / 'imview' / 'static' / 'imgrid.js'


def test_static_bundle_exists():
    js = _static_js()
    assert js.is_file()
    assert js.stat().st_size > 1000
    text = js.read_text(encoding='utf-8')
    assert 'export' in text


def test_mpl_lut_bytes():
    from iad.vis.imview.colormaps import mpl_lut_bytes

    blob = mpl_lut_bytes('viridis')
    assert len(blob) == 256 * 4


def test_build_lut_map_custom():
    from iad.vis.imview.colormaps import build_lut_map

    luts = build_lut_map(['rain', 'wide'])
    assert 'rain' in luts
    assert len(luts['rain']) == 256 * 4


def test_prepare_grid_scalar():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im1, im2 = rand(10, 10), rand(10, 10)
    prepared = prepare_grid_from_parsed(
        [(im1, 'a'), (im2, 'b')],
        clim=[(0.0, 1.0), (0.0, 1.0)],
    )
    assert len(prepared.panels) == 2
    assert prepared.panels[0].kind == 'scalar'
    assert prepared.panels[0].buffer.dtype == 'float32'
    assert prepared.grid == [1, 2]


def test_prepare_grid_rgb():
    from iad.vis.imview.data import prepare_grid_from_parsed

    rgb = (rand(8, 8, 3) * 255).astype('uint8')
    prepared = prepare_grid_from_parsed([(rgb, 'rgb')])
    assert prepared.panels[0].kind == 'rgb'
    assert prepared.panels[0].buffer.dtype == 'uint8'


def test_downsample():
    from iad.vis.imview.data import prepare_grid_from_parsed

    big = rand(2000, 2000)
    prepared = prepare_grid_from_parsed([(big, 'big')], max_pixels=10_000)
    assert prepared.panels[0].width * prepared.panels[0].height <= 10_000


def test_imgrid_widget_traits():
    from iad.vis.imview import imgrid

    im1, im2 = rand(12, 12), rand(12, 12)
    result = imgrid(
        im1,
        im2,
        titles=['one', 'two'],
        cmap=['rain', 'jet'],
        clim=[(0, 7), (0, 1)],
        backend='widget',
    )
    w = result.widget
    assert len(w.panels) == 2
    assert len(w.buffers) == 2
    assert type(w.buffers[0]).__name__ in {'memoryview', 'ndarray'}
    assert w.luts
    assert 'rain' in w.luts or len(w.luts) > 0
    assert w.grid == [1, 2]


def test_imgrid_clim_parsing():
    from iad.vis.imview import imgrid

    im1, im2 = rand(10, 10), rand(10, 10)
    result = imgrid(
        im1,
        im2,
        (im1 - im2),
        im1,
        clim=[(0, 7), 0, 'auto', 2],
        titles=['one', 'two', 'diff', 'four'],
        backend='widget',
    )
    assert len(result.widget.panels) == 4
    assert result.widget.panels[0]['clim'][0] == 0
    assert result.widget.panels[0]['clim'][1] == 7


def test_imgrid_out_images():
    from iad.vis.imview import imgrid

    im = rand(6, 6)
    images = imgrid(im, backend='widget', out='images')
    assert len(images) == 1
    assert images[0][0].shape == (6, 6)


def test_imgrid_out_widget():
    from iad.vis.imview import imgrid

    w = imgrid(rand(5, 5), backend='widget', out='widget')
    assert hasattr(w, 'panels')


def test_image_grid_value():
    from iad.vis.imview import imgrid

    result = imgrid(rand(4, 4), backend='widget')
    assert 'cursor' in result.value
    assert 'view' in result.value
