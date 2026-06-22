import pytest
from numpy.random import rand

plotly = pytest.importorskip('plotly')


def test_mpl_to_plotly_colorscale():
    from iad.vis.plgrid import mpl_to_plotly_colorscale

    scale = mpl_to_plotly_colorscale('viridis', n=8)
    assert len(scale) == 8
    assert scale[0][0] == 0.0
    assert str(scale[0][1]).startswith('rgb(')


def test_build_figure_heatmaps():
    from iad.vis.plgrid import build_figure

    im1, im2 = rand(10, 10), rand(10, 10)
    images = [(im1, 'a'), (im2, 'b')]
    fig = build_figure(
        images,
        grid=(1, 2),
        clims=[(0.0, 1.0), (0.0, 1.0)],
        cmaps=['rain', 'jet'],
        cbar=True,
        cmap_menu=True,
        clim_slider=True,
    )
    heatmaps = [trace for trace in fig.data if trace.type == 'heatmap']
    assert len(heatmaps) == 2
    assert heatmaps[0].zmin == 0.0
    assert heatmaps[0].zmax == 1.0
    assert fig.layout.updatemenus
    assert fig.layout.sliders


def test_build_figure_rgb():
    from iad.vis.plgrid import build_figure

    rgb = (rand(8, 8, 3) * 255).astype('uint8')
    fig = build_figure(
        [(rgb, 'rgb')],
        grid=(1, 1),
        clims=[(None, None)],
        cmaps=['rain'],
    )
    assert fig.data[0].type == 'image'


def test_imgrid_clim_parsing():
    from iad.vis.plgrid import imgrid

    im1, im2 = rand(10, 10), rand(10, 10)
    fig = imgrid(
        im1,
        im2,
        (im1 - im2),
        im1,
        clim=[(0, 7), 0, 'auto', 2],
        titles=['one', 'two', 'diff', 'four'],
        backend='figure',
        out='fig',
        cmap_menu=False,
        clim_slider=False,
    )
    heatmaps = [trace for trace in fig.data if trace.type == 'heatmap']
    assert len(heatmaps) == 4
    assert heatmaps[0].zmin == 0
    assert heatmaps[0].zmax == 7


def test_pixel_budget_splits_across_panels():
    from iad.vis.plgrid import _pixel_budget_per_image

    assert _pixel_budget_per_image(4, max_pixels=400_000, max_total_pixels=800_000, backend='figure') == 200_000
    marimo_cap = _pixel_budget_per_image(4, max_pixels=400_000, max_total_pixels=None, backend='marimo')
    assert marimo_cap == 125_000


def test_imgrid_downsample():
    from iad.vis.plgrid import build_figure

    big = rand(2000, 2000)
    fig = build_figure(
        [(big, 'big')],
        grid=(1, 1),
        clims=[(float(big.min()), float(big.max()))],
        cmaps=['gray'],
        max_pixels=10_000,
        cmap_menu=False,
        clim_slider=False,
    )
    z = fig.data[0].z
    assert z.shape[0] * z.shape[1] <= 10_000


def test_imgrid_out_images():
    from iad.vis.plgrid import imgrid

    im = rand(6, 6)
    images = imgrid(im, backend='figure', out='images')
    assert len(images) == 1
    assert images[0][0].shape == (6, 6)
    assert isinstance(images[0][1], str)


def test_readout_format():
    from iad.vis.plgrid import _format_readout

    im1 = rand(4, 4)
    im2 = rand(4, 4)
    text = _format_readout(1, 2, [(im1, 'a'), (im2, 'b')])
    assert '(2, 1)' in text
    assert 'a:' in text
    assert 'b:' in text


@pytest.mark.parametrize('backend', ['figure', 'jupyter'])
def test_backend_smoke(backend):
    from iad.vis.plgrid import imgrid

    if backend == 'jupyter':
        pytest.importorskip('ipywidgets')
        anywidget = pytest.importorskip('anywidget')
        _ = anywidget
    result = imgrid(rand(5, 5), rand(5, 5), backend=backend, inspect=False)
    assert result.figure is not None
    if backend == 'jupyter':
        assert result.ui is not None


def test_marimo_backend_smoke():
    marimo = pytest.importorskip('marimo')
    from iad.vis.plgrid import imgrid

    result = imgrid(rand(5, 5), backend='marimo', inspect=False)
    assert result.ui is not None
    assert hasattr(marimo.ui, 'plotly')
