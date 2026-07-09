from pathlib import Path

import numpy as np
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


def test_prepare_grid_layout_and_cbar():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im1, im2 = rand(10, 10), rand(10, 10)
    prepared = prepare_grid_from_parsed([(im1, 'a'), (im2, 'b')], cbar=True, resize='no')
    assert prepared.canvas_size[0] > 0
    assert prepared.canvas_size[1] > 0
    for panel in prepared.panels:
        assert 'x' in panel.layout
        src_aspect = panel.width / panel.height
        lay_aspect = panel.layout['w'] / panel.layout['h']
        assert abs(src_aspect - lay_aspect) < 0.05
        assert panel.cbar is not None
        assert panel.cbar['x'] == panel.layout['x'] + panel.layout['w']
        assert panel.cbar['y'] == panel.layout['y']
        assert panel.cbar['h'] == panel.layout['h']


def test_prepare_grid_mosaic_layout():
    from iad.vis.imview.data import prepare_grid_from_parsed

    ims = [rand(8, 8) for _ in range(2)]
    prepared = prepare_grid_from_parsed(
        [(im, f'p{i}') for i, im in enumerate(ims)],
        grid='AB',
    )
    assert prepared.grid == [1, 2]
    assert prepared.panels[0].layout['x'] != prepared.panels[1].layout['x']


def test_prepare_grid_resize_up():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im1, im2 = rand(10, 10), rand(20, 20)
    prepared = prepare_grid_from_parsed([(im1, 'a'), (im2, 'b')], resize='up')
    assert prepared.panels[0].width == prepared.panels[1].width == 20
    assert prepared.panels[0].height == prepared.panels[1].height == 20


def test_prepare_grid_resize_error():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im1, im2 = rand(10, 10), rand(20, 20)
    with pytest.raises(ValueError, match='different sizes'):
        prepare_grid_from_parsed([(im1, 'a'), (im2, 'b')], resize='error')


def test_imgrid_show_grid_adj_clim_traits():
    from iad.vis.imview import imgrid

    result = imgrid(rand(6, 6), backend='widget', show_grid=True, adj_clim=True)
    assert result.widget.show_grid is True
    assert result.widget.adj_clim is True
    assert result.widget.canvas_width > 0
    assert result.widget.panels[0]['layout']


def test_mogrid_wgt_backend():
    from unittest.mock import patch

    from iad.vis.mutils import Backend, mogrid

    with patch('iad.vis.imview.imgrid', return_value='wgt-grid') as mock_imgrid:
        out = mogrid(rand(4, 4), backend=Backend.WGT)
    assert out == 'wgt-grid'
    mock_imgrid.assert_called_once()


def test_max_zoom_and_downsample_mutually_exclusive():
    from iad.vis.imview import imgrid

    with pytest.raises(ValueError, match='mutually exclusive'):
        imgrid(rand(4, 4), backend='widget', max_zoom=2, downsample=2)


def test_downsample_factor():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im = rand(100, 100)
    prepared = prepare_grid_from_parsed([(im, 'a')], downsample=4, resize='no')
    panel = prepared.panels[0]
    assert panel.factor == 4
    assert panel.width == 25
    assert panel.height == 25
    assert panel.source_width == 100
    assert panel.sent_bytes == panel.width * panel.height * 4
    assert panel.full_bytes == 100 * 100 * 4


def test_max_zoom_full():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im = rand(40, 40)
    prepared = prepare_grid_from_parsed([(im, 'a')], max_zoom='full', resize='no')
    assert prepared.panels[0].factor == 1
    assert prepared.panels[0].width == 40


def test_figsize_width_only():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im = rand(50, 100)
    prepared = prepare_grid_from_parsed(
        [(im, 'a')],
        figsize=(400, None),
        resize='no',
    )
    layout = prepared.panels[0].layout
    assert layout['w'] >= 240
    assert layout['h'] >= 240
    assert abs(layout['w'] / layout['h'] - 2.0) < 0.05


def test_figsize_both_fit_inside():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im = rand(50, 100)
    prepared = prepare_grid_from_parsed(
        [(im, 'a')],
        figsize=(800, 600),
        resize='no',
    )
    layout = prepared.panels[0].layout
    assert layout['w'] >= 240
    assert layout['h'] >= 240
    assert abs(layout['w'] / layout['h'] - 2.0) < 0.05
    assert layout['w'] <= 800
    assert layout['h'] <= 600


def test_prepared_grid_byte_totals():
    from iad.vis.imview.data import prepare_grid_from_parsed

    im1, im2 = rand(20, 20), rand(20, 20)
    prepared = prepare_grid_from_parsed(
        [(im1, 'a'), (im2, 'b')],
        downsample=2,
        resize='no',
    )
    assert prepared.sent_bytes == sum(p.sent_bytes for p in prepared.panels)
    assert prepared.full_bytes == sum(p.full_bytes for p in prepared.panels)
    assert prepared.sent_pixels == sum(p.width * p.height for p in prepared.panels)
    assert prepared.full_pixels == sum(p.source_width * p.source_height for p in prepared.panels)


def test_imgrid_data_traits():
    from iad.vis.imview import imgrid

    result = imgrid(rand(8, 8), backend='widget', downsample=2)
    w = result.widget
    assert w.data_sent_bytes > 0
    assert w.data_full_bytes > w.data_sent_bytes
    assert w.panels[0]['factor'] == 2
    assert w.panels[0]['sourceWidth'] == 8


def test_imgrid_data_over_budget():
    from iad.vis.imview import imgrid

    big = rand(500, 500)
    result = imgrid(big, backend='widget', max_zoom='full', max_pixels=10_000)
    assert result.widget.data_over_budget is True


def test_mogrid_figsize_passthrough():
    from unittest.mock import patch

    from iad.vis.mutils import Backend, mogrid

    with patch('iad.vis.imview.imgrid', return_value='wgt-grid') as mock_imgrid:
        out = mogrid(rand(4, 4), backend=Backend.WGT, figsize=(800, 600), max_zoom=2)
    assert out == 'wgt-grid'
    kwargs = mock_imgrid.call_args.kwargs
    assert kwargs.get('figsize') == (800, 600)
    assert kwargs.get('max_zoom') == 2


def _buffer_scalar_sum(widget, panel_idx: int = 0) -> float:
    buf = widget.buffers[panel_idx]
    if isinstance(buf, memoryview):
        arr = np.frombuffer(buf, dtype=np.float32)
    else:
        arr = np.asarray(buf, dtype=np.float32).ravel()
    return float(arr.sum())


def test_update_data_sequence():
    from iad.vis.imview import imgrid

    im1, im2 = rand(8, 8), rand(8, 8)
    result = imgrid(im1, im2, titles=['a', 'b'], backend='widget', clim=[(0, 1), (0, 1)])
    before = _buffer_scalar_sum(result.widget, 0)
    new_im1 = np.full((8, 8), 0.5, dtype=np.float32)
    result.update_data([new_im1, im2])
    after = _buffer_scalar_sum(result.widget, 0)
    assert after != before
    assert result.widget.canvas_width > 0
    assert len(result.widget.panels) == 2


def test_update_data_dict_maps_by_title():
    from iad.vis.imview import imgrid

    im1, im2 = rand(6, 6), rand(6, 6)
    result = imgrid(im1, im2, titles=['left', 'right'], backend='widget', clim=[(0, 1), (0, 1)])
    new_left = np.full((6, 6), 0.25, dtype=np.float32)
    new_right = np.full((6, 6), 0.75, dtype=np.float32)
    # Dict in reversed order: mapping must be by title, not position.
    result.update_data({'right': new_right, 'left': new_left})
    assert _buffer_scalar_sum(result.widget, 0) == pytest.approx(0.25 * 36)
    assert _buffer_scalar_sum(result.widget, 1) == pytest.approx(0.75 * 36)


def test_update_data_dict_requires_all_titles():
    from iad.vis.imview import imgrid

    im1, im2 = rand(6, 6), rand(6, 6)
    result = imgrid(im1, im2, titles=['left', 'right'], backend='widget', clim=[(0, 1), (0, 1)])
    with pytest.raises(ValueError, match='titles'):
        result.update_data({'left': np.full((6, 6), 0.25, dtype=np.float32)})


def test_update_data_shape_mismatch():
    from iad.vis.imview import imgrid

    result = imgrid(rand(5, 5), backend='widget')
    with pytest.raises(ValueError, match='shape'):
        result.update_data([rand(6, 6)])


def test_update_data_auto_clim_recomputed():
    from iad.vis.imview import imgrid

    im = np.zeros((10, 10), dtype=np.float32)
    result = imgrid(im, backend='widget', clim='auto')
    lo0, hi0 = result.widget.panels[0]['clim']
    new_im = np.full((10, 10), 100.0, dtype=np.float32)
    result.update_data([new_im])
    lo1, hi1 = result.widget.panels[0]['clim']
    assert hi1 > hi0


def test_update_data_explicit_clim_preserved():
    from iad.vis.imview import imgrid

    im = rand(7, 7)
    result = imgrid(im, backend='widget', clim=[(0.0, 7.0)])
    result.update_data([rand(7, 7)])
    assert result.widget.panels[0]['clim'] == [0.0, 7.0]


def test_update_data_resize_up():
    from iad.vis.imview import imgrid

    im1, im2 = rand(10, 10), rand(20, 20)
    result = imgrid(im1, im2, titles=['small', 'large'], backend='widget', resize='up', clim=[(0, 1), (0, 1)])
    assert result.widget.panels[0]['width'] == 20
    new_im1 = np.full((10, 10), 0.3, dtype=np.float32)
    new_im2 = np.full((20, 20), 0.6, dtype=np.float32)
    result.update_data({'small': new_im1, 'large': new_im2})
    assert result.widget.panels[0]['width'] == 20
    assert result.widget.panels[0]['height'] == 20
