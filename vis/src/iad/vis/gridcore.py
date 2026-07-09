"""Matplotlib-independent helpers shared by imgrid backends."""

from __future__ import annotations

from typing import Any, Iterable, Literal, Union

import numpy as np
import regex as re

import iad.core.codetools as cdt


def hist_range(d: np.ndarray, bins=100, min_bin=0.05, ignore_tail=0.005, outlier=0.02, range_marg=0.05):
    """Histogram based calculation of the data dynamic range excluding outliers

    :param d: ndarray - the data
    :param bins:  number of bins for the histogram
    :param min_bin: bins filled with less than min_bin / bins are ignored (min_bins times less than average)
    :param ignore_tail: part of energy which may be ignored at the tails  of the distribution
    :param outlier: bins with bigger distance considered outliers and ignored
    :param range_marg: the final range is extended by this ratio if tails are cut
    :return: min_range, max_range
    """
    if d.dtype == bool:
        return 0, 1

    # Stage I: Calculate the histogram and data range parameters
    d = d[~(np.isnan(d) | np.isinf(d))]
    if not len(d):
        return -np.inf, np.inf
    hst, edges = np.histogram(d, bins)

    hst[hst < min_bin * d.size / bins] = 0  # ignore weakly populated bins altogether - set them to 0
    nz_ids = np.flatnonzero(hst)  # locations of non zero bins
    nz_dist = np.diff(nz_ids)

    i0, il = nz_ids[[0, -1]]  # indices of the first and last nz bins
    if (nz_dist == 1).sum() > 1:  # some of the significant bins are neighbors - not a discrete case
        outlier_dist = max(1, outlier * hst.size)
        if nz_dist[0] > outlier_dist:
            i0 = nz_ids[1]
        if nz_dist[-1] > outlier_dist:
            il = nz_ids[
                     -2] + 1  # add 1 bin to separate color of the last 'good' bin from the saturation 'bin'

    return tuple(edges[[i0, il + 1]])


class MosaicParser:
    """
    Parse code in extended notations supported by the ``subplot_mosaic``.

    The rules are:
     - A valid ``subplot_mosaic`` code is accepted as is
     - Extended notation use additional special characters:
       ::
            !  instructs to transpose the given grid
            +  repeat row ended by it multiple times (also is a row separator)
    - Extended mode is activated automatically if those symbols are encountered in the code
    - In the extended mode only letters and ``.`` (dot) are allowed as areas indicators
    - Capital letters indicate image axes, and small - plot axes.
    - A row pattern followed by ``+`` separator is mutated into multiple rows of same structure
      ::

        * the multiplication factor is derived from the number of provided images
        * only rows with at least one image axes (capital letter) can be repeated
        * only one row can be marked as repeating
        * it can be followed only by plots-only rows

    The rows are separated into 3 groups: [fixed][repeats][plots]
     - Fixed (0+): may contain mix of images and plots in any proportion
     - Repeat (0|1+): optional row pattern with at least 1 image, repeated 1+ times
     - Plots (0+): arbitrary amount of rows with only plots

    Example:
    ::
        AB.a;CDcd+x..y

    - It describes 3+ rows patterns with 4 columns,
    - First row consists of 2 images, space, and a plot
    - Second row contains 2 images and 2 plots, and may be repeated
    - Third row contains two plots separated by double space

    """
    pattern: re.Pattern = None
    img: re.Pattern = re.compile(r'[A-Z]\d*')

    trp: str = '!'
    rep: str = r'\+'
    sep: str = r'[\s\n;]'

    @classmethod
    def set_pattern(cls, *, trp=trp, rep=rep, sep=sep):
        """
        Initialize parsing pattern given building elements.

        Calling this function changes state of the MosaicParser class
        and defines parsing rules.

        :param trp: transpose regex element
        :param rep: row repetition regex element
        :param sep: rows separator regex element
        """

        grp = lambda name, rex: f'(?P<{name}>{rex})'

        plt1, end_plt = (grp(n, "[.a-z]+") for n in ['plt1', 'end_plt'])
        mix, rep_mix = (grp(n, "[.a-z]*[A-Z][.A-Za-z]*") for n in ['mix', 'rep_mix'])
        fixed = grp('fixed', f'{plt1}|{mix}')

        pat = fr"{trp}?\s*(?:{fixed}(?:$|{sep}+))*(?:{rep_mix}{rep}{sep}*)?{end_plt}?"
        cls.pattern = re.compile(pat)

    def __init__(self, code: str):
        if not self.pattern: self.set_pattern()
        self.code = code.strip('\n \t')
        self.layout = None
        self.shape = None
        self.images = []
        self.plots = []
        self.match = self.pattern.fullmatch(self.code)
        self.code = code
        self.transpose = bool(re.search(self.trp, code))
        self.extended = self.transpose or bool(re.search(self.rep, code))

        found = self.match and self.match.capturesdict()
        self.fixed = found and found['fixed']

        if found and (com := set(self.fixed).intersection(found['rep_mix'])):
            raise ValueError(f"Symbols {com} appear in fixed and repeated rows!")

        def _images_in(grp: list[str]):
            return sum(len(set(self.img.findall(_))) for _ in grp)

        self.fix_ims = found and _images_in(found['mix'])
        self.rep_ims = found and _images_in(found['rep_mix'])

        self.repeat_row = found and found['rep_mix'] and found['rep_mix'][0]
        self.end_plots = found and found['end_plt']

        groups = (found[g] for g in ['fixed', 'rep_mix', 'end_plt'])
        columns = {len(r) for g in groups for r in g}
        if not columns:
            raise ValueError(f'No mosaic pattern is described by {code = }')
        if len(columns) > 1:
            raise ValueError(f'All rows must be of same length, found: {columns = }')
        self.columns = columns.pop()

    def __bool__(self):
        return bool(self.match)

    def __repr__(self):
        if not self.match: return f"Invalid code {self.code}"
        attrs = ['extended', 'transpose', 'fixed', 'repeat_row', 'end_plots']
        img_num = self.fix_ims + self.rep_ims
        nl = '\n  '
        kvs = nl.join(f"{attr}: {getattr(self, attr)}" for attr in attrs)
        return f"Mosaic for min {img_num} ({self.fix_ims} fix + {self.rep_ims}xN rep) images{nl}{kvs}\n"

    def accommodate(self, inp_img_num):
        """Accommodate given number of images in the dynamic mosaic defined by the object.

        Return list based form of mosaic description suitable for ``figure.subplot_mosaic()``.

        """
        if not self.match: raise ValueError(f"Invalid mosaic code {self.code}")
        # if not self.extended:
        #     self.layout = self.code
        #     return self.code
        space = '.'
        is_image = lambda _: 'A' <= _[0] <= 'Z'

        # Translate rows from letter code into list of lists.
        # The code may contain three parts of rows: [fixed][repeats][plots]
        rows = [list(r) for r in self.fixed]  # fixed part

        if self.rep_ims:  # repeating part
            repeat_num = (inp_img_num - self.fix_ims) / self.rep_ims
            if int(repeat_num) != repeat_num or repeat_num <= 0:
                raise ValueError(f"Received {inp_img_num} images, code {self.code} assumes:\n"
                                 f"num = {self.fix_ims} + {self.rep_ims} * N  ({repeat_num = })")

            if repeat_num == 1:
                rows.append(list(self.repeat_row))  # split row codes into list of symbols
            else:
                for rep in range(int(repeat_num)):
                    rows.append([c if c == space else f'{c}{rep}' for c in self.repeat_row])

        for r in self.end_plots:  # ending plots part
            rows.append(list(r))

        # Create lists of images and plots symbols in the order of their first appearance
        known = set()  # to track only the first appearance of symbols
        for r in rows:
            for c in r:  # full code name of the axes
                if c == space or c in known: continue
                known.add(c)
                (self.images if is_image(c) else self.plots).append(c)

        if self.transpose:
            from iad.core.datatools import transpose
            rows = transpose(rows)

        self.layout = rows
        self.shape = (len(rows), len(rows[0]))
        return rows

    def create_axes(self, fig: Any, img_num=None, *, sharex='images', sharey='images',
                    width_ratios=None, height_ratios=None,
                    subplot_kw=None, per_subplot_kw=None, gridspec_kw=None):
        if img_num:
            self.accommodate(img_num)
        if not self.layout:
            raise ValueError('Axes may be created only after images number is provided')

        if share_img_x := sharex == 'images': sharex = False
        if share_img_y := sharey == 'images': sharey = False

        axes = fig.subplot_mosaic(
            self.layout, sharex=sharex, sharey=sharey,
            width_ratios=width_ratios, height_ratios=height_ratios,
            subplot_kw=subplot_kw, per_subplot_kw=per_subplot_kw, gridspec_kw=gridspec_kw
        )

        if self.images and share_img_y or share_img_y:
            ax0 = axes[self.images[0]]
            for c in self.images[1:]:
                if share_img_x: axes[c].sharex(ax0)
                if share_img_y: axes[c].sharey(ax0)

        return axes


max_figsize = (14, 6)  # (x, y) inches - restricts imgrid (or other plotting functions)

_KEY_COLOR_MAP = {'P': 'pink', 'J': 'jet', 'W': 'wide', 'R': 'rain',
             'Y': 'gray', 'Z': 'coolworm', 'V': 'viridis', 'C': 'coolwarm'}


def _assign_cmaps(cmaps, num):
    """ Parse cmap argument """
    if not isinstance(cmaps, list):
        return [cmaps] * num

    if len(cmaps) < num:
        cmaps = cmaps + [cmaps[-1]] * (num - len(cmaps))
    elif len(cmaps) > num:
        cmaps = cmaps[:num]

    cmaps = [cmaps[cm] if isinstance(cm, int) else cm for cm in cmaps]
    for cm in cmaps:
        if isinstance(cm, int):
            raise TypeError('Color maps list must not contain reference to another reference index!')
    return cmaps


def title_str(obj: Union[str, dict, Iterable, Any]) -> str:
    """Convert several kinds of objects into string form good for title"""
    if isinstance(obj, str):
        return obj
    if hasattr(obj, 'items'):
        return ' '.join(f"{k}: {v}" for k, v in obj.items())
    if hasattr(obj, '__iter__'):
        return ' '.join(map(str, obj))
    return str(obj)


def assign_args_names(args, *, names, func_name, nest_level, enum_form):
    """
    Assign names to arguments using several possible sources of the information.
    :param args: iterable of elements of several possible types: (elm_type|tuple|namedtuple|dict)
    :param names:
    :param func_name:
    :param nest_level:
    :return: List of tuples (pairs):  [(arg, name), ...]

    (in the order of priority and if available):
     - explicitly given names list in the `names` argument
     - one element of the tuple of every `inputs` elements (if provided as a tuple)
     - ``datacast.Labeled`` objects, name will be automatically 'flatten'
     - keys of the dictionary (if the element is a dict)
     - variables names as passed to the the upper level function call
     - enumerated formatted string, where sequential index of the argument is passed to format the provided string
    """

    def is_tuple_ref(arg_str):
        if '*' not in arg_str:
            return False

        tmp = "".join(arg_str.split())
        if tmp.index("*") == 0:
            return True

        if tmp[tmp.index("*") - 1] in '[{(,':
            return True

        return False

    call_var_names = cdt.call_args_expr(nest_level + 1, name=func_name)
    parse_id = 0
    arg_id = 0

    # bring all the input formats to the canonical form of list of tuples: # [(image, title), ...]
    pairs = []
    for inp in args:
        if isinstance(inp, tuple):  # (image3, 'title'):
            if hasattr(inp, '_fields'):
                pairs.extend(zip(inp, inp._fields))
                arg_id += len(inp)
            else:
                pairs.append(inp)
                arg_id += 1
        elif isinstance(inp, dict) and hasattr(inp, 'flat'):  # Labeled data type
            pairs.append(inp.flat())  # inp: datacast.label.Labeled
        elif hasattr(inp, 'items'):  # dictionary must be in form of {'title': image}
            pairs.extend((val, key) for key, val in inp.items())  # swap key-val order!
            arg_id += len(inp)
        else:  # then its assumed to be an image !!!
            name = enum_form.format(arg_id)
            if parse_id < len(call_var_names):
                if is_tuple_ref(call_var_names[parse_id]):
                    parse_id = len(call_var_names)  # Stop processing
                else:
                    name = call_var_names[parse_id]
            pairs.append((inp, name))
            arg_id += 1
        parse_id += 1

    if names:
        com_len = min(len(pairs), len(names))
        pairs[:com_len] = [(im, new_t if new_t is not None else old_t)
                           for (im, old_t), new_t in zip(pairs[:com_len], names[:com_len])]

    return pairs


def convert_image_data(im, name):
    if isinstance(im, str):
        im, name = name, im
    if not hasattr(im, 'shape'):
        raise TypeError(f"Can't find image in {(im, name)}")

    if hasattr(im, 'magnitude'):
        im = im.magnitude  # strip units and leave only magnitude - much TODO here
    if hasattr(im, 'device'):
        dev = im.device
        if hasattr(dev, 'type'):
            if dev.type != 'cpu' and hasattr(im, 'to'):
                im = im.to('cpu')
        elif dev not in (None, 'cpu'):
            if hasattr(im, 'to'):
                im = im.to('cpu')
    if hasattr(im, 'numpy'):
        im = im.numpy()
    if (np.array(im.shape) == 1).any():
        im = im.squeeze()
    if not (im.ndim == 2 or im.ndim == 3 and (im.shape[2] == 3 or im.shape[0] == 3 or im.shape[2] == 4)):
        raise TypeError(f'Not a valid shape {im.shape} of image {name}')
    if im.ndim == 3 and im.shape[0] == 3:
        im = np.moveaxis(im, 0, 2)
    return im, name


_PROP_TOLERANCE = 0.01


def _nn_resize(im: np.ndarray, height: int, width: int) -> np.ndarray:
    ys = np.clip((np.arange(height) * im.shape[0] / height).astype(int), 0, im.shape[0] - 1)
    xs = np.clip((np.arange(width) * im.shape[1] / width).astype(int), 0, im.shape[1] - 1)
    return im[ys[:, None], xs[None, :]]


def _resize_images(
    images: list[tuple[np.ndarray, str]],
    resize: Literal['no', 'up', 'down', 'error'] | bool,
) -> list[tuple[np.ndarray, str]]:
    if resize is True:
        resize = 'up'
    elif resize is False:
        resize = 'no'
    allowed = ('no', 'up', 'down', 'error')
    if resize not in allowed:
        raise ValueError(f"resize must be one of {allowed} or bool, got {resize!r}")
    shapes = [im.shape[:2] for im, _ in images]
    if len(set(shapes)) == 1:
        return images
    if resize == 'no':
        return images
    if resize == 'error':
        raise ValueError(f"Images have different sizes: {shapes}")
    if resize == 'up':
        target_h = max(h for h, w in shapes)
        target_w = max(w for h, w in shapes)
    else:
        target_h = min(h for h, w in shapes)
        target_w = min(w for h, w in shapes)
    result = []
    for (im, title), (h, w) in zip(images, shapes):
        if h == target_h and w == target_w:
            result.append((im, title))
            continue
        sx = target_w / w
        sy = target_h / h
        if abs(sx / sy - 1) > _PROP_TOLERANCE:
            raise ValueError(
                f"Resize to {(target_h, target_w)} is not proportional for image "
                f"shape {(h, w)} (scale x/y ratio {sx / sy:.6f})"
            )
        result.append((_nn_resize(im, target_h, target_w), title))
    return result


def _to_clim_list(clim_arg, images):
    """ Convert clim argiment notations into explicit list of clim for every image """

    clim_arg = [clim_arg, ] * len(images) if type(clim_arg) is not list else clim_arg
    clim_arg = clim_arg[:len(images)] + ['auto'] * (len(images) - len(clim_arg))
    clim_list = [(None, None)] * len(clim_arg)
    for i in range(len(clim_arg)):
        if clim_list[i] != (None, None):
            continue
        if clim_arg[i] == 'auto':
            clim_list[i] = hist_range(images[i][0])
            continue
        if type(clim_arg[i]) is tuple:
            clim_list[i] = clim_arg[i] if len(clim_list[i]) == len(clim_arg[i]) else Exception(
                "Wrong clim_arg tuple len")
            continue

        chain = [i]
        curr = clim_arg[i]
        while curr != 'auto' and type(curr) is not tuple:
            if curr > len(clim_arg):
                KeyError("Ref index in clim_arg list is out of range")

            if curr in chain and curr != i:
                KeyError("Circular ref indexes in clim_arg list")

            next_init = clim_arg[curr]
            if type(next_init) is int:
                if next_init == curr:  # allow to clim_arg index to point to itself, treating as 'auto'
                    next_init = 'auto'
                else:
                    chain.append(curr)
                    curr = next_init
                    continue

            for index in chain:
                if type(next_init) is tuple:
                    clim_list[index] = next_init
                elif next_init == 'auto':
                    clim_list[index] = hist_range(images[curr][0])
                else:
                    Exception("Unsupported clim_arg in clims list")
            break
    return clim_list


def grid_layout(num, grid_in, transp) -> tuple | MosaicParser:
    """
    Return grid layout as tuple for subplots or mosaic_subplots
    :param num:
    :param grid_in:
    :param transp:
    :return: (rows, cols) | MosaicParser instance
    """
    if isinstance(grid_in, MosaicParser):
        if transp: raise ValueError("Use `!` prefix to transpose grid in mosaic form")
    elif isinstance(grid_in, str):
        for opt, r in {'auto': np.floor(num ** (1 / 2)).astype(int),
                       'horizontal': 1, 'vertical': num}.items():
            if opt.startswith(grid_in):
                return r, num // r + bool(num % r)
        if p := MosaicParser(grid_in):
            if transp: raise ValueError("Use `!` prefix to transpose grid in mosaic form")
            p.accommodate(num)  # raises if any problem is detected
            return p
        raise ValueError(f'Invalid grid argument value {grid_in}')

    return grid_in


def _optimal_fig_size(grid, im_shape):
    def fig_ratio(i):
        j = int(not i)
        return grid[i] / grid[j] * im_shape[i] / im_shape[j]

    im_h, im_w = im_shape[:2]
    fig_w = max_figsize[0]
    fig_h = fig_w * fig_ratio(0)
    if fig_h > max_figsize[1] * 1.05:
        fig_h = max_figsize[1]
        fig_w = fig_h * fig_ratio(1)
    fig_size = fig_w, fig_h

    if grid[0] == grid[1] == 1:  # make a single almost square image smaller
        if fig_w / max_figsize[0] > 0.7 and fig_h / max_figsize[1] > 0.9:
            fig_size = fig_w * 0.6, fig_h * 0.6

    return fig_size
