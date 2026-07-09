from __future__ import annotations

__all__ = ['hist_range', 'cmp', 'imhist', 'imgrid', 'max_figsize', 'grid_layout']

import logging
from typing import Any, Literal
from warnings import warn

# import matplotlib as mpl
# mpl.use("Qt5Agg")
import matplotlib.pyplot as plt
import matplotlib.widgets as wdg
import numpy as np

from iad.core import as_list
from iad.vis.gridcore import (
    MosaicParser,
    _KEY_COLOR_MAP,
    _assign_cmaps,
    _optimal_fig_size,
    _resize_images,
    _to_clim_list,
    assign_args_names,
    convert_image_data,
    grid_layout,
    hist_range,
    max_figsize,
    title_str,
)

_log = logging.getLogger(__name__)
_log.debug('loading %s ...' % __name__)

_CMAPS_REGISTERED = False


def _register_cmap_if_missing(cmap, name: str) -> None:
    if name in plt.colormaps:
        return
    plt.colormaps.register(cmap, name=name)


def register_custom_colormaps(cpath=None):
    """Add custom colormaps into the workspace (no-op if already registered)."""
    global _CMAPS_REGISTERED
    if _CMAPS_REGISTERED:
        return
    from glob import glob
    from os import path
    import sys
    from matplotlib.colors import LinearSegmentedColormap, ListedColormap
    import importlib

    if not cpath:
        cpath = path.join(path.split(__file__)[0], 'colormaps')
    sys.path.append(cpath)

    sfx = '_cm.py'
    cmaps = [path.split(f)[1][:-len(sfx)] for f in glob(path.join(cpath, '*' + sfx))]
    _log.debug('registering custom colormaps: %s' % cmaps)
    for cm_name in cmaps:
        module = importlib.import_module(cm_name + sfx.split('.')[0])
        cmap = LinearSegmentedColormap.from_list(cm_name, module.cm_data)
        _register_cmap_if_missing(cmap, cm_name)

    cmaps = [
        ListedColormap(np.array(
            [[130, 215, 165], [110, 195, 225], [230, 195, 240], [235, 230, 100],
             [0, 150, 28], [0, 102, 195], [155, 50, 195], [210, 65, 5], [100, 0, 45]]
        ) / 255., name='durange', N=9)
    ]
    for cm in cmaps:
        _register_cmap_if_missing(cm, cm.name)

    _CMAPS_REGISTERED = True


def crop_hist_tails(hst, strength=0.5, show=False):
    """ Crop histogram tails including bins of insignificant energy.
    Finds an optimum of cutting more tails and keeping the energy.

    :param hst: the histogram to crop
    :param strength: bigger value - more aggressive cropping (0.1 to 5)
    :param show: bool - debugging graphs
    :return:
    """

    def cut_tail(ncs, FACT):
        score = np.linspace(0, 1, ncs.size) ** 2 - 2 ** (ncs / FACT)
        dd = np.diff(score)
        peaks, = np.nonzero((dd[:-1] > 0) & (dd[1:] < 0) & (score[1:-1] > score[0]))
        return np.amax(peaks) + 1 if len(peaks) else 0, score

    cs = np.cumsum(hst)
    cs = cs / cs[-1]  # normalize

    pos_l, score_l = cut_tail(cs, strength)
    pos_r, score_r = cut_tail(1 - cs[::-1], strength)

    if show:
        _, axs = plt.subplots(2, 1, figsize=(6, 7), tight_layout=0.5, sharex='all')
        ids = range(hst.size)
        axs[0].plot(ids, hst)
        axs[0].plot(ids[pos_l], hst[pos_l], 'r.')
        axs[0].plot(ids[-pos_r], hst[-pos_r], 'r.')
        axs[1].plot(ids, score_l, ids, score_r[::-1])

    if pos_l == hst.size - 1 or pos_r == 0 or pos_l >= pos_r:
        warn(f'Invalid histogram tails cropping results {(pos_l, pos_r)}: falling back to keep all.')
        pos_l, pos_r = 0, hst.size - 1
    return pos_l, pos_r


def cmp(a, b, *titles, sign=True):
    """
    Produce list of the inputs and the diff between them
    :param a:  first image
    :param b:  second image
    :param titles: optional names of a and b
    :param sign: use regular or absolute diff
    :return:
    """
    if a.dtype.kind == 'u' and b.dtype.kind == 'u':
        a = a.astype(int)
    dif = [a, b, a - b if sign else np.abs(a - b)]

    if len(titles) == 0 or len(titles) > 3:
        return dif
    if len(titles) == 2:
        titles = [*titles, ('' if sign else 'abs') + '([%s] - [%s]))' % titles]
    return zip(dif, titles)


def outmax(a):
    """
    :param a: array
    :return: maximal not oulier value
    """
    vals = np.unique(a)
    d = np.median(np.diff(vals))
    mx = np.amax(vals)
    mx2 = np.amax(vals[vals < mx])
    return mx2 if mx - mx2 > np.std(vals) else mx


def imhist(*imgs, titles=None, sharex=True, sharey=True, ax=None, grid=None,
           measure=None, prec=3, **kws):
    """
    Single histogram plot or grid-plot if multiple images provided.
    :param imgs: images (last may be bins as number or sequence)
    :param titles: per image
    :param sharex: for grid-plot
    :param sharey: for grid-plot
    :param ax:     only for single image - axes to draw in
    :param grid:   (rows, columns)
    :param measure: list of metrics to measure (see `algutils.nptools.stats`)
    :param prec:    measures precision
    :param kws:    arguments passed to plt.hist

    Examples:
    >>> imhist(im1, im2, bins=100)
    >>> imhist(im1, im2, 100)
    >>> imhist(im1, im2, range(100), cumulative=True)
    """
    # see if last unnamed arhument is bins:
    if 'bins' not in kws and len(imgs) > 1:
        v = imgs[-1]
        if not hasattr(v, '__len__') or (
                (not isinstance(v, np.ndarray) or v.ndim == 1)
                and len(v) < 256):
            kws['bins'] = v
            imgs = imgs[:-1]

    if ax:
        axs = [ax]
        assert len(imgs) == 1
    else:
        grid = (1, len(imgs)) if grid is None else grid
        fsz = kws.pop('fsz', kws.pop('figsize', (3 * grid[1], 3 * grid[0])))
        _, axs = plt.subplots(*grid, sharey=sharey, sharex=sharex, figsize=fsz)
        axs = axs.flatten() if isinstance(axs, np.ndarray) else [axs]

    if sharex:
        if not hasattr(kws.get('bins', None), '__len__'):
            kws['range'] = kws.get('range', None) or (
                np.nanmin([*map(np.nanmin, imgs)]),
                np.nanmax([*map(np.nanmax, imgs)])
            )

    if measure:
        measure = as_list(measure)
        from iad.core.data.nptools import stats

    for i, (im, ax) in enumerate(zip(imgs, axs)):
        plt.sca(ax)
        data = im[np.isfinite(im)]
        plt.hist(data, **kws)
        if titles:
            ax.set_title(titles[i])
        if measure:
            plt.text(  # position text relative to Axes
                1.0, 1.0,
                stats(im, measure=as_list(measure), out=str, sep='\n'),
                ha='right', va='top', c='c',
                transform=ax.transAxes
            )
    plt.tight_layout()


class ColorRangeControl:
    def __init__(self, ax, im, *, im_range=None, init_range=None, adjustable=False, cbar=True):
        from mpl_toolkits.axes_grid1 import make_axes_locatable
        from matplotlib.widgets import Slider

        # color bar
        divider = make_axes_locatable(ax)
        if cbar:
            cax = divider.append_axes("right", "2%", pad=".2%")
            plt.colorbar(im, cax=cax, ax=ax, orientation='vertical')

        if not adjustable:
            return

        if not im_range:
            im_range = im.get_array().min(), im.get_array().max()

        if not init_range:
            init_range = im_range

        self.ax_clim_min = divider.append_axes("bottom", "2%", pad="6.5%")
        self.slider_min = Slider(self.ax_clim_min, '', *im_range, valinit=init_range[0])
        self.ax_clim_max = divider.append_axes("bottom", "2%", pad="1%")
        self.slider_max = Slider(self.ax_clim_max, '', *im_range, valinit=init_range[1])

        self.ax_im = im
        self.ax_main = ax

        self.slider_min.on_changed(self.on_change_range)
        self.slider_max.on_changed(self.on_change_range)

    def on_change_range(self, val):
        if self.slider_min.val > self.slider_max.val:
            self.slider_min.val = self.slider_max.val
        if self.slider_max.val < self.slider_min.val:
            self.slider_max.val = self.slider_min.val
        self.ax_im.set_clim(self.slider_min.val, self.slider_max.val)


def hist_inset(ax, image, clm=None, bins=32):
    """
    Add inset with a histogram of given image into given axes.
    :param ax: axes to insert the inset into
    :param image: image to create the histogram from
    :param clm: limits of the histogram
    :param bins: bins number
    """
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    inax = inset_axes(ax, loc=1, width="15%", height="15%", borderpad=0,
                      axes_kwargs=dict(facecolor='k'))
    inax.patch.set_alpha(0.4)
    inax.set_xticks([])
    inax.set_yticks([])

    mx = clm[1] if clm else image[np.isfinite(image)].max()
    plt.hist(image[image <= mx], bins=bins, histtype='stepfilled',
             color=[0.7, 1, 0.5, 0.6])
    plt.sca(ax)  # make sure last subplot is the current axes - dosn't help - to be removed


class KeyProcessor:
    cmaps = _KEY_COLOR_MAP

    def __init__(self, figure, axis, toolbar=None):
        self.canvas = figure.canvas
        self.toolbar = toolbar
        self.multi_cursor = None
        figure.canvas.mpl_connect('key_press_event', self.on_key_press)
        figure.ctrl_axid = []  # currently selected axes
        figure.color_ranges = []
        axis = np.array(axis)
        self.axis = axis
        figure.sub_axis = axis.reshape(axis.size)
        figure.imgrid = self  # keep a reference to the object until the figure is destroyed # TODO: Check!

    def on_key_press(self, event):
        # aliases
        sub_axis = np.array(self.canvas.figure.sub_axis)
        selected_ids = self.canvas.figure.ctrl_axid

        def select_axes(aid, sel):
            """ change """
            axes = sub_axis[aid]
            spine = axes.spines['top']
            normal = axes.spines['bottom']
            operate, ec, lw = (selected_ids.append, 'red', 5) if sel else (
                selected_ids.remove, normal.get_facecolor(), normal.get_linewidth())
            operate(aid)
            spine.set_color(ec)
            spine.set_linewidth(lw)

        try:
            print(event.key)
            if event.key == 'escape':
                [select_axes(i, False) for i in selected_ids.copy()]
            elif event.key == 'ctrl+f' and selected_ids:
                for ax in sub_axis[selected_ids]:
                    imgrid(ax.images[0].get_array().data, titles=[ax.get_title()])
                    plt.show()
            elif ((event.key.startswith('ctrl+alt+') or
                   event.key.startswith('alt+ctrl+')) and '0' <= event.key[9:] <= '9'):
                ax_id = int(event.key[9:])
                if len(sub_axis) > ax_id:
                    select_axes(ax_id, ax_id not in selected_ids)
            elif event.key.startswith('ctrl+') and '0' <= event.key[5:] <= '9':
                ax_id = int(event.key[5:])
                if len(sub_axis) > ax_id:
                    # copy as select_axis modifies same list
                    [select_axes(i, False) for i in selected_ids.copy()]
                    select_axes(ax_id, True)
            elif event.key.startswith('alt+'):
                self.on_alt_key(event.key[4:])
            elif len(event.key) == 1:
                if event.key == '?':
                    cmaps_str = '\n'.join((' ' * 40 + f'{k} - {v}') for k, v in self.cmaps.items())
                    print(f"""
                    Select one axis:        Ctrl+<id>           (zero-based!)
                    Add another axis:       Ctrl+Alt+<id>
                    Clear selection:        Esc
                    Align Color Lims:       c                   (by the first selected)
                    Visible color limits:   v                   (all selected)
                    Apply Color Map: \n{cmaps_str}
                    """)
                elif event.key in self.cmaps:
                    ids = selected_ids or [*range(len(sub_axis))]
                    for ax in sub_axis[ids]:
                        ax.images[0].set_cmap(self.cmaps[event.key])
                elif event.key == 'c' and selected_ids:  # match [C]olor limit with the first selected
                    clim = sub_axis[selected_ids[0]].images[0].get_clim()
                    for ax in sub_axis[selected_ids[1:]]:
                        ax.images[0].set_clim(clim)
                elif event.key == 'v' and selected_ids:
                    for ax in sub_axis[selected_ids]:
                        x0, x1 = ax.get_xlim()
                        y0, y1 = ax.get_ylim()
                        im = ax.images[0].get_array().data[
                             max(0, int(y1)):int(y0) + 1,
                             max(0, int(x0)):int(x1) + 1]

                        ax.images[0].set_clim(np.nanmin(im), np.nanmax(im))
                elif event.key == 'm':
                    if self.multi_cursor:
                        self.multi_cursor = None
                    else:
                        self.multi_cursor = wdg.MultiCursor(self.canvas, sub_axis,
                                                            color='r', lw=1, horizOn=True, vertOn=True)

            self.canvas.draw()
        except Exception as e:
            print(e)

    def on_alt_key(self, key):
        """Override in subclasses to handle Alt+<key> events (e.g. annotations)."""
        pass


# Idea: Convert imgrid to class
def imgrid(*images,
            # ToDO In Imgrid - Include all labels of image inside the ax
           labels: dict | list[dict] = None,
           titles: list[str] = None,
           grid: str | tuple | list | MosaicParser = 'auto', transp=False,
           cmap: str | list[str] = 'rain', cbar=True,
           window_title: str = None,
           out: bool | Literal['axs', 'fig', 'ims', 'all'] = False,
           adj_clim=False, ticks='xy', mosaic=None, show_grid=False,
           pad=None, fig=None, toolbar=None, key_processor_cls=None,
           block=None, hist=False, dpi=None, tight=True,
           resize: Literal['no', 'up', 'down', 'error'] | bool = 'error',
           **imkw) -> None | list | dict:
    """Show titled images or histogram. Return axis list.

    Grid may be defined in one of the following forms:
        - string:  'vertical'|'horizontal'|'auto' (or first letters)
        - tuple: (rows, columns)
        - mosaic

    :param images: arguments list of images in form of:
            arrays, tuples, dictionaries, datacast.Labeled items
            [image1, image2, (image3, 'title'), image4, dict].
                dictionary must be in form of {'title': image}
    :param titles: allows to override or complete missing image titles.
    :param grid: 'vertical'|'horizontal'|'auto' (first letters) or
                 tuple: (rows, columns) or ``subplot_mosaic`` form

    :param transp: transpose grid if True. Rearranges the images without
            need to change any other arguments.
    :param cbar:  (bool) show or hide colorbars near the axes
    :param window_title: window title.
    :param out:  [False]|True|'axs'|'fig'|'ims'|'all' - what to return:
                  - 'axs' | True  - list of axes with images
                  - 'fig' - container figure
                  - 'ims' - image objects
                  - 'all' - list of all above in order: axs, fig, ims
    :param adj_clim: [False]|True - Should add clim sliders or not
    :param ticks:  (str) may only include 'x' or 'y' letters
                    to control ticks and categories appearance.
    :param show_grid: show or hide grid on the axes
    :param mosaic: True|False|'titles'. macro-parameter.
                  True for ticks='', cbar=False, titles=['']*len(images)
                  If 'titles' - leaves titles as usual.
    :param pad:   parameters for tight_layout.
                  a number - then its `pad` argument
                  a dict - may include h_pad, w_pad, pad keys
    :param fig:   figure object - if not provided a new one is created #FixMe no fig in input, on purpose?
    :param toolbar: toolbar object (needed only in QT App)
    :param cmap:  cmap to use with imshow.
                  May be list (for every image). In this case
                    - if len(cmap) < len(images) - use last for the rest
                    - if len(cmap) > len(images) - ignore
                    elements may be
                      -- matplotlib.colors.Colormap objects
                      -- Registered colormap names
                      -- index in the list as a reference to another cmaps element
    :param block: if True or False show(block=block)
    :param hist: Show histogram. [False]|True|None|bins.
                - False - don't show histogram (or if unqies < 8)
                - bins - argument to hist(..., bins=bins)
                - None - automatic decision based on number of unique values
                - True - like None, for backward compatibility
    :param resize: how to handle images of different size.
                - 'error' (default) - raise ValueError on size mismatch
                - 'no' - leave sizes unchanged
                - 'up' - resize all to largest height and width (nearest neighbour)
                - 'down' - resize all to smallest height and width (nearest neighbour)
                - True is treated as 'up', False as 'no'
                Raises ValueError if resize would be non-proportional in x/y beyond 1%.
    :param tight
    :param dpi
    :param imkw: imshow arguments.

    :return: (accorging to 'out' value)
                 None | list of axes with images
                 | container figure|image
                 | list containing axs, fig, ims objects
    """
    import logging
    mpl_logger = logging.getLogger('matplotlib')
    mpl_logger.setLevel(logging.WARNING)

    caption = imkw.pop('cap', None)
    figsize = imkw.pop('fsz', None) or imkw.pop('figsize', None)
    if figsize is not None:
        imkw['figsize'] = figsize

    if mosaic:
        cbar, ticks = False, ''
        if mosaic != 'titles':
            titles = [''] * len(images)
    if pad is None:
        padding = dict(pad=0, h_pad=0, w_pad=0) if mosaic else dict(pad=0.1)
    elif isinstance(pad, dict):
        padding = pad
    else:
        padding = dict(pad=pad)

    if not set(ticks).issubset('xy'):
        raise TypeError("String argument `ticks` may only include 'x' or 'y' letters.")

    # # TODO: remove hard dependence on torch
    # if torch is not False:
    #     images = [ im.cpu().numpy() if torch.is_tensor(im) else im for im in images]

    images = assign_args_names(images, names=titles, func_name='imgrid', nest_level=1,
                               enum_form='Stream_{}')

    images = [convert_image_data(*item) for item in images]
    images = _resize_images(images, resize)

    # Consider: streamline grid layout logic
    grid = grid_layout(len(images), grid, transp)
    clims = _to_clim_list(imkw.pop('clim', 'auto'), images)
    cmaps = _assign_cmaps(cmap, len(images))

    if transp:  # that happens only if grid is not mosaic!
        from iad.core.datatools import transpose
        grid = grid[::-1]
        images, clims, cmaps = map(lambda _: transpose(_, int(grid[0])),
                                   (images, clims, cmaps))

    is_mosaic = isinstance(grid, MosaicParser)
    shape = grid.shape if is_mosaic else grid
    figsize = imkw.pop('figsize', _optimal_fig_size(shape, images[0][0].shape))
    if not fig:  # that allows to use a figure created externally
        fig = plt.figure(figsize=figsize, dpi=dpi)
        if window_title: fig.suptitle(window_title)
    else:
        fig.set_figheight(figsize[1])
        fig.set_figwidth(figsize[0])

    img_axs = {}
    plt_axs = {}
    kp_cls = key_processor_cls or KeyProcessor
    if is_mosaic:
        all_axes = grid.create_axes(fig, sharex='images', sharey='images')
        axs = [all_axes[code] for code in grid.images]
        for k, v in all_axes.items():
            (img_axs if k in grid.images else plt_axs).update({k: v})
        kp_cls(fig, axs, toolbar)
    else:
        axs = fig.subplots(*grid, sharex='all', sharey='all')
        kp_cls(fig, axs, toolbar)  # connect key-processor

        # Make axes list flat and leave in there only those with images
        axs = list(axs.flat) if isinstance(axs, np.ndarray) else [axs, ]
        while len(axs) > len(images):
            axs.pop().remove()

    ims = []
    for (image, title), ax, clm, cm in zip(images, axs, clims, cmaps):
        kwclim = {'clim': clm} if clm else {}
        if len(image.shape) == 3 and np.all(image[:, :, 0] == image[:, :, 1]) \
                and np.all(image[:, :, 0] == image[:, :, 2]):
            image = image[:, :, 0]

        if title == 'cam':
            cmap = 'gray' if len(image.shape) == 2 else None
            im = ax.imshow(image, interpolation='nearest', cmap=cmap, **imkw, **kwclim)
        else:
            if len(image.shape) == 3:
                cmap = 'gray' if np.all(image[:, :, 0] == image[:, :, 1]) \
                                 and np.all(image[:, :, 0] == image[:, :, 2]) else cm
            else:
                cmap = cm
            im = ax.imshow(image, interpolation='nearest', cmap=cmap, **imkw, **kwclim)
        ims.append(im)

        ax.set_adjustable('box')
        if title:
            ax.set_title(title_str(title), pad=5)
        ax.grid(visible=show_grid)

        if 'x' not in ticks:
            ax.set_xticks([])
        if 'y' not in ticks:
            ax.set_yticks([])

        fig.color_ranges.append(ColorRangeControl(ax, im, init_range=clm, adjustable=adj_clim, cbar=cbar))
        fig.sca(ax) # Make data axes the current one ( instead of the color ranges), to be used with fig.gca()
        if hist:  # True option provides backward compatibility
            hist_inset(ax, image, clm, 32 if hist is True else hist)

    # ToDO labels include information on the scene for each axes. How to use them? Consult Ilya
    if labels:
        pass

    if caption:
        plt.suptitle(caption)

    # import warnings
    # with warnings.catch_warnings():
    #     warnings.simplefilter("ignore")
    if tight: fig.tight_layout(**padding)

    if block is not None:
        plt.show(block=block)

    if out:
        from collections import namedtuple
        res = {
            'axs': axs,
            'img_axs': img_axs,
            'plt_axs': plt_axs,
            'fig': fig,
            'data': images,
            'ims': ims,
        }
        if out == 'msc':
            return namedtuple('MosaicAxes', ['img_axs', 'plt_axs'])(img_axs, plt_axs)
        if out is True or out == 'axes':
            out = 'axs'
        if out in res:
            return res[out]

        elif out == 'all':
            return namedtuple('ImgridOut', res.keys())(**res)


def hist_grid(hists: dict[str, np.ndarray] | np.ndarray,
              edges: dict[str, np.ndarray], title: str = None, ticks: int | tuple[int, int] = 5,
              norm: Literal['asinh', 'log', 'logit', 'symlog'] = None,
              grid='auto', cmap='terrain', **kws):
    """
    Plot grid of `N` 2d histograms, each of two variable `V1 × V2` (rows, columns).

    Histograms data may be represented as:
     - `dict[name, [V1×V2] array]` of len `N`
     - *collection* of `N × [V1×V2]` arrays

    Edges of the bins along every variable are same for all the histograms, and passed as
     - `{name1:, edges2[V2], name1: edges1[V1]}`
     -  *collection*, `[edges2[V2], edges1[V2]]` arrays
    *Notice* the order of edges follows `xy` notation

    :param hists: dict of 2D [V1 × V2] arrays or N x 2D arrays (as 3D array or list of 2Ds) or 1 × 2D ≡ 2D
    :param edges: dict of 2 items {name: vector} for every of the hists 2 variables, ordered as hist[K × M]

    :param title: to put on the top of the plot
    :param ticks: number of ticks of both or each of the axes
    :return:
    """
    from iad.core.datatools import split_dict
    from matplotlib import pyplot as plt, ticker

    _fig_kws = {'figsize', 'dpi', 'layout', 'tight_layout'}
    fig_kws, im_kws = split_dict(dict(layout='tight', norm=norm, cmap=cmap) | kws,
                                 lambda k, _: k in _fig_kws)

    if len(ticks := as_list(ticks)) == 1:
        ticks *= 2
    ticks = np.array(ticks) + 1
    title = (title or 'Hist2D') + (f' ({norm})' if norm else '')

    if isinstance(hists, dict):
        names = list(hists)
        hists: list[np.ndarray] = list(hists.values())
    else:
        names = [f"hist_{i}" for i in range(len(hists))]

    hists: np.ndarray = np.asarray(hists)  # fail here if different dimensions
    if hists.ndim == 2:
        hists = hists[None, :, :]
    if hists.ndim != 3:
        raise ValueError("Invalid histogram data shape")
    hists: dict[str, np.ndarray] = dict(zip(names, hists))

    if edges is None:
        edges = {}
    elif not isinstance(edges, dict):
        edges = dict(zip(['var_2', 'var_1'], edges, strict=True))
    if not len(edges) in (0, 2):
        raise ValueError("Edges must be for 2 variables, or None")

    grid = grid_layout(len(hists), grid, False)
    fig, axs = plt.subplots(*grid, sharex='all', sharey='all', **fig_kws, squeeze=False)
    fig.suptitle(title)

    def idx_to_val_maper(values):
        index = np.arange(len(values))
        return lambda x, _: '{:.3g}'.format(np.interp(x, values, index))

    formatters = {k: idx_to_val_maper(v) for k, v in edges.items()}

    for ax, (name, hist) in zip(axs.flat, hists.items()):
        plt.sca(ax)
        ax.set_title(name)
        plt.imshow(hist, **im_kws)
        ticks = [ticks + 1] * 2 if isinstance(ticks, int) else ticks
        for label, axis, loc in zip(edges, [ax.xaxis, ax.yaxis],
                                    map(ticker.MaxNLocator, ticks)):
            axis.set_label(label)
            # axis.set_major_locator(loc)
            axis.set_major_formatter(formatters[label])

    return fig, axs


register_custom_colormaps()


class SubplotsPointInfo(object):
    """
    plot_data_info_tool cis used to aff information to set of axis that were created as sub plots (potentially by \
    imgrid)
    It add two type of information:
    Per axis info: for each axis additional text box is added (above its left upper corner) with the information: the \
    cursor location and the value in this location
    Annotation information: by clicking on the mouse you can get annotation with the cursor location and all the values \
    in all the axis for this location. This mode can be enable./disable
    """

    def __init__(self, axs, named_annotation=False):
        """
        initial plot_data_info_tool object
        :param axs:                a list of axis that will be treated by the tool
        :param named_annotation:   the way the annotation display the value in each axis. In default the values \
        are given in the same grid as the axis (so their correspondence is clear). If named_annotation=true  you \
        get get each axis by its title name
        """

        self.axs = axs
        self.per_axis_value = []
        self.lhor = []
        self.lver = []

        self.ann_active = False

        self.static_ann = []
        self.ann = None

        self.is_sub_plot_info = False
        self.is_annotation = False

        self.on_motion_connect = None
        self.on_click_connect = None
        self.on_key_press_connect = None

        self.sub_plot_layout = self.calc_sub_plot_grid_layout()

        self.help_text = None

        # choose if to output the sub plot names in the annotation according to its location (no real name)
        # or according to the sub plot name
        if named_annotation:
            self.annotation_name_formatter = self.create_annotation_name_formatter()
        else:
            self.annotation_name_formatter = None

    # -----------------------------------------------------------------------------------------------
    # class constants

    MAX_ALLOWED_LABEL_SIZE_FOR_ANNOTATION = 10
    DELTA = 0.1

    # -----------------------------------------------------------------------------------------------
    # init helping functions

    # get sub plot grid layout
    def calc_sub_plot_grid_layout(self):
        curr_y = self.axs[0].get_position().y0
        num_sub_plot_x = 1

        if isinstance(self.axs, (list,)):
            return 1, 1

        for curr_axe in self.axs[1:]:
            if np.absolute(curr_axe.get_position().y0 - curr_y) > 0.01:
                break
            num_sub_plot_x += 1

        num_sub_plot_y = int(np.ceil(self.axs.shape[0] / num_sub_plot_x))

        return num_sub_plot_y, num_sub_plot_x

    # get the maximal size of subplots titles and create formatter accordingly
    def create_annotation_name_formatter(self):

        max_title_length = 0
        for curr_axe in self.axs:
            if len(curr_axe.get_title()) > max_title_length:
                max_title_length = len(curr_axe.get_title())

        if max_title_length <= SubplotsPointInfo.MAX_ALLOWED_LABEL_SIZE_FOR_ANNOTATION:
            formatter = '{:' + str(max_title_length) + '}'
        else:
            formatter = '{:' + str(SubplotsPointInfo.MAX_ALLOWED_LABEL_SIZE_FOR_ANNOTATION) + '}'

        return formatter

    # -------------------------------------------------------------------------------------------------------------------------
    # activate tools

    def activate_dynamic_sub_plot_info(self):
        """
         activate the per axis info
        """
        for curr_axe in self.axs:
            t = curr_axe.text(0, 1.04, '', transform=curr_axe.transAxes, va='top')
            self.per_axis_value.append(t)

            self.lhor.append(curr_axe.axhline(0))
            self.lver.append(curr_axe.axvline(0))

        self.on_motion_connect = self.axs[0].figure.canvas.mpl_connect('motion_notify_event', self.on_motion)

        self.is_sub_plot_info = True

    def activate_dynamic_annotation(self):
        """
         activate annotation tool
         to activate/deactivate the annotation you must press the m key
         to get temporary annotation you need to clock once on the mouse. This annotation will be \
         disappear when mouse is moved
         to get static annotation that do not disappear with mouse move or zooming you need to double click
         to clear all static annotation press d key
         to improve annotation location after zooming or image shifting press u key
        """
        self.on_motion_connect = self.axs[0].figure.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.on_click_connect = self.axs[0].figure.canvas.mpl_connect('button_press_event', self.on_click)
        self.on_key_press_connect = self.axs[0].figure.canvas.mpl_connect('key_press_event', self.key_press)

        self.is_annotation = True

    # -------------------------------------------------------------------------------------------------------------------------
    # remove tools

    def remove_tools(self):
        """
        close all information that were added by the tool
        """
        self.axs[0].figure.canvas.mpl_disconnect(self.on_motion_connect)
        self.axs[0].figure.canvas.mpl_disconnect(self.on_click_connect)
        self.axs[0].figure.canvas.mpl_disconnect(self.on_key_press_connect)

        self.on_motion_connect = None
        self.on_click_connect = None
        self.on_key_press_connect = None

        self.delete_all_static_ann()

        for t, curr_hor, curr_ver in zip(self.per_axis_value, self.lhor, self.lver):
            curr_hor.remove()
            curr_ver.remove()
            t.remove()

        self.per_axis_value = []
        self.lhor = []
        self.lver = []

        self.ann_active = False
        self.ann = None

        self.is_sub_plot_info = False
        self.is_annotation = False

    # -------------------------------------------------------------------------------------------------------------------------
    # event handlers

    ##################################
    def on_motion(self, event):
        print(event)
        x = int(np.round(event.xdata))
        y = int(np.round(event.ydata))

        if self.is_sub_plot_info:
            for t, curr_axe, curr_hor, curr_ver in zip(self.per_axis_value, self.axs, self.lhor, self.lver):
                t.set_text('({0:d},{1:d}), {2:5.2f}'.format(y, x, curr_axe.images[0].get_array()[y, x]))
                curr_hor.set_ydata(y)
                curr_ver.set_xdata(x)

        if self.is_annotation and (self.ann is not None):
            self.ann.set_visible(False)
            self.ann = None

        if self.help_text is not None:
            self.help_text.set_visible(False)
            self.help_text = None

        self.axs[0].canvas.draw()

    ##################################
    def on_click(self, event):

        if self.ann_active:

            # ------------------------------------------------------------
            # get click info

            work_axe = event.inaxes

            x_data = int(np.round(event.xdata))
            y_data = int(np.round(event.ydata))

            # ------------------------------------------------------------
            # build the annotation text

            # the x,y location
            ann_text = '({0:d}, {1:d})\n'.format(x_data, y_data)

            # run on all axes and add its name: value to the annotation text
            curr_axe_index = 0
            for curr_axe in self.axs:

                value = '{0:5.2f}'.format(curr_axe.images[0].get_array()[x_data, y_data])

                label = curr_axe.get_title()

                if self.annotation_name_formatter is not None:
                    ann_text += self.annotation_name_formatter.format(label) + ': ' + value

                    if curr_axe != self.axs[-1]:
                        ann_text += '\n'

                else:
                    x = int(np.mod(curr_axe_index, self.sub_plot_layout[1]))
                    if x == 0:
                        ann_text += '{}'.format(value)
                    elif x == (self.sub_plot_layout[1] - 1):
                        ann_text += ', {}\n'.format(value)
                    else:
                        ann_text += ', {}'.format(value)

                curr_axe_index += 1

            # ------------------------------------------------------------
            # get annotation and its text location

            x_axis, y_axis = self.data_to_axis(x_data, y_data)
            x_data_range, y_data_range = self.data_range()

            dx, dy, hor, var = self.get_ann_text_shift(x_axis, y_axis)

            # ------------------------------------------------------------
            # do annotation

            if self.ann is None:
                self.ann = work_axe.annotate(
                    ann_text, xy=(x_axis, y_axis), xycoords='axes fraction',
                    xytext=(x_axis + dx, y_axis + dy), textcoords='axes fraction',
                    color="purple", fontsize=12, fontname='Courier New',
                    bbox=dict(boxstyle="round", fc="0.8"),
                    arrowprops=dict(facecolor='purple', shrink=0.05, width=1.3),
                    horizontalalignment=hor, verticalalignment=var,
                    multialignment='left')
            else:
                self.ann.set_visible(False)
                self.ann = None
                new_ann = work_axe.annotate(
                    ann_text, xy=(x_data, y_data), xycoords='data',
                    xytext=(x_data + dx * x_data_range, y_data + dy * y_data_range),
                    textcoords='data', color="purple", fontsize=12,
                    fontname='Courier New',
                    bbox=dict(boxstyle="round", fc="0.8"),
                    arrowprops=dict(facecolor='purple', shrink=0.05, width=1.3),
                    horizontalalignment=hor, verticalalignment=var,
                    multialignment='left')
                self.static_ann.append(new_ann)

    ##################################
    def key_press(self, event):
        if event.key == 'm':
            if self.ann_active:
                self.ann_active = False
                self.delete_all_static_ann()
            else:
                self.ann_active = True
        elif (event.key == 'd') and self.ann_active:
            self.delete_all_static_ann()
        elif (event.key == 'u') and self.ann_active:
            self.update_static_ann_text_loc()
        else:
            self.help_text = event.inaxes.text(
                0, 0.5,
                'anotation tool:\nuse h key for help\nuse m key to enable/disable '
                'annotation\nuse one click for temporary annotation\nuse double click '
                'for static annotation\nuse d key to delete all static annotation\nuse '
                'u key to update stastic annotation locations',
                transform=event.inaxes.transAxes, va='top',
                backgroundcolor='white')

    # -------------------------------------------------------------------------------------------------------------------------
    # methods for update or clean up static annotations

    def delete_all_static_ann(self):

        for curr_ann in self.static_ann:
            curr_ann.remove()

        self.axs[0].canvas.draw()
        self.static_ann = []

    def update_static_ann_text_loc(self):

        for curr_ann in self.static_ann:
            (x_data, y_data) = curr_ann.xy

            x_axis, y_axis = self.data_to_axis(x_data, y_data)
            x_data_range, y_data_range = self.data_range()

            dx, dy, hor, var = self.get_ann_text_shift(x_axis, y_axis)

            curr_ann.set_position((x_data + dx * x_data_range, y_data + dy * y_data_range))

            curr_ann.set_horizontalalignment(hor)
            curr_ann.set_verticalalignment(var)

            self.axs[0].canvas.draw()

    # -------------------------------------------------------------------------------------------------------------------------
    # coordinate tools

    @staticmethod
    def get_ann_text_shift(x_axis, y_axis):

        if (x_axis > 0.5) and (y_axis > 0.5):
            dx = -SubplotsPointInfo.DELTA
            dy = -SubplotsPointInfo.DELTA
            hor = 'right'
            var = 'top'
        elif (x_axis > 0.5) and (y_axis <= 0.5):
            dx = -SubplotsPointInfo.DELTA
            dy = SubplotsPointInfo.DELTA
            hor = 'right'
            var = 'bottom'
        elif (x_axis <= 0.5) and (y_axis > 0.5):
            dx = SubplotsPointInfo.DELTA
            dy = -SubplotsPointInfo.DELTA
            hor = 'left'
            var = 'top'
        else:
            dx = SubplotsPointInfo.DELTA
            dy = SubplotsPointInfo.DELTA
            hor = 'left'
            var = 'bottom'

        return dx, dy, hor, var

    def data_to_axis(self, xin, yin):

        x_lim = self.axs[0].get_xlim()
        y_lim = self.axs[0].get_ylim()

        x_delta = x_lim[1] - x_lim[0]
        y_delta = y_lim[1] - y_lim[0]

        x_delta2 = xin - x_lim[0]
        y_delta2 = yin - y_lim[0]

        x_out = x_delta2 / x_delta
        y_out = y_delta2 / y_delta

        return x_out, y_out

    def data_range(self):

        x_lim = self.axs[0].get_xlim()
        y_lim = self.axs[0].get_ylim()

        x_delta = x_lim[1] - x_lim[0]
        y_delta = y_lim[1] - y_lim[0]

        return x_delta, y_delta


def cross_viewer(im, ax=None):
    """
    View cross-section of image along x-axis at some y-point
    :param im:
    :param ax: if provided draws there, otherwise creates new figure
    :return:
    """
    if ax:
        plt.sca(ax)
    else:
        plt.figure(figsize=(5, 3));

    x, y = im.shape[1] // 2, im.shape[0] // 2
    line = plt.plot(im[y, :])[0]
    mark = plt.plot([x], [y], 'r+')[0]
    vals = im[~(np.isnan(im) | np.isinf(im))]
    mn, mx = vals.min(), vals.max()
    ax.set_ylim(mn, mx + (mx - mn) * 0.05)

    def update_plot(xy):
        x, y = xy
        if 0 <= y < im.shape[0]:
            line.set_ydata(im[int(y), :])
            mark.set_xdata([x])
            mark.set_ydata(im[int(y), int(x)])

    return update_plot
