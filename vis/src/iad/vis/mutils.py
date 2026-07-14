"""Marimo notebook helpers for image grids and dataframe display."""

from __future__ import annotations

import importlib
import os
import sys
from enum import Enum

import marimo as mo


class Backend(str, Enum):
    MPL = 'mpl'
    PLY = 'ply'
    WGT = 'wgt'
    IMV = 'imv'

def iad_reloader():
    """Dynamically bootstraps the iad namespace package for marimo hot-reloading."""
    temp_mod = importlib.import_module("iad")
    spec = temp_mod.__spec__
    raw_locations = list(spec.submodule_search_locations or []) if spec else []
    for name in list(sys.modules):
        if name == "iad" or name.startswith("iad."):
            sys.modules.pop(name, None)
    for path in raw_locations:
        src_parent = os.path.dirname(path)
        if src_parent not in sys.path:
            sys.path.insert(0, src_parent)
    importlib.invalidate_caches()
    return importlib.import_module("iad")


class MogridOptions:
    def __init__(self) -> None:
        self._backend: Backend = Backend.PLY

    @property
    def backend(self) -> Backend:
        """Global default backend used by :func:`mogrid`.

        'mpl' - matplotlib via :func:`iad.vis.insight.imgrid`
        'ply' - Plotly via :func:`iad.vis.plgrid.imgrid`
        'wgt' - anywidget via :func:`iad.vis.imview.imgrid`
        """
        return self._backend

    @backend.setter
    def backend(self, value: Backend | str) -> None:
        try:
            value = Backend(value)
        except ValueError:
            raise ValueError(
                f"backend={value!r} must be one of {[b.value for b in Backend]}!"
            ) from None
        self._backend = value


class Option:
    """Descriptor that registers a :class:`DataframeOptions` setting."""

    def __init__(
        self,
        default=None,
        *,
        default_factory=None,
        overridable=True,
        copy=False,
        doc=None,
    ) -> None:
        self.default = default
        self.default_factory = default_factory
        self.overridable = overridable
        self.copy = copy
        if doc is not None:
            self.__doc__ = doc

    def __set_name__(self, owner, name: str) -> None:
        self.name = name
        self.attr = f"_{name}"
        registry = owner.__dict__.get("_OPTIONS")
        if registry is None:
            registry = []
            owner._OPTIONS = registry
        registry.append(self)

    def make_default(self):
        if self.default_factory is not None:
            return self.default_factory()
        return self.default

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        value = getattr(obj, self.attr)
        return dict(value) if self.copy else value

    def __set__(self, obj, value) -> None:
        if self.copy:
            value = dict(value or {})
        setattr(obj, self.attr, value)
        obj._apply()


class DataframeOptions:
    precision = Option(2)
    series = Option(True, overridable=False)
    datetime_format = Option(
        "%H:%M:%S",
        doc="Display format for datetime columns (``datetime.strftime`` format, default ``'%H:%M:%S'``).",
    )
    column_summaries = Option(
        False,
        doc="Header column summaries (histogram/stats). "
            "``False`` (default) hides them, which lets columns shrink below the"
            "chart's minimum width. ``True`` shows both, ``'stats'`` shows only"
            "stats, ``'chart'`` only the histogram, ``None`` uses marimo's default."
    )
    data_types = Option(
        True,
        doc="Show the data-type badge under each column header (default ``True``). "
            "Set to ``False`` to drop the badge row, which lets column headers"
            "(and thus columns) shrink a bit further.",
    )
    column_widths = Option(default_factory=dict, copy=True)
    default_width = Option(None)

    def __init__(self) -> None:
        for opt in self._OPTIONS:
            setattr(self, opt.attr, opt.make_default())
        self._apply()

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{opt.name}={getattr(self, opt.attr)!r}" for opt in self._OPTIONS
        )
        return f"DataframeOptions({parts})"

    @classmethod
    def _option_keys(cls):
        return tuple(opt.name for opt in cls._OPTIONS if opt.overridable)

    @staticmethod
    def _column_key(col):
        return ",".join(map(str, col)) if isinstance(col, tuple) else col

    @staticmethod
    def _css_width(width):
        return f"{width}px" if isinstance(width, int) else width

    @classmethod
    def _format_mapping(cls, df, precision, datetime_format) -> dict:
        key = cls._column_key
        fmt = f"{{:.{precision}f}}".format

        def dt_fmt(value):
            if hasattr(value, "strftime"):
                return value.strftime(datetime_format)
            return str(value)

        mapping = {
            key(c): fmt for c in df.select_dtypes(include="float").columns
        }
        for c in df.select_dtypes(include=["datetime", "datetimetz"]).columns:
            mapping[key(c)] = dt_fmt
        return mapping

    @classmethod
    def _native_widths(cls, df, column_widths, default_width):
        """Integer pixel widths sizing the actual column track (header included)."""
        key = cls._column_key
        resolved = {}
        for c in df.columns:
            w = column_widths.get(c, default_width)
            if isinstance(w, int) and not isinstance(w, bool) and w > 0:
                resolved[key(c)] = w
        return resolved or None

    @classmethod
    def _style_cell(cls, column_widths, default_width):
        key, css_width = cls._column_key, cls._css_width
        widths = {key(c): css_width(w) for c, w in column_widths.items()}

        def style_cell(_row_id, column_name, _value):
            width = widths.get(column_name, css_width(default_width))
            if width is None:
                return {}
            return {
                "width": width,
                "minWidth": width,
                "maxWidth": width,
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            }

        return style_cell

    def table(self, data, **overrides):
        """Build a ``mo.ui.table`` for *data* applying the current options.

        *data* may be a pandas ``DataFrame`` or ``Series``.

        Keyword *overrides* may name any :class:`DataframeOptions` setting
        (``precision``, ``datetime_format``, ``column_summaries``,
        ``data_types``, ``column_widths``, ``default_width``) to override it
        for this call only. Any other keyword is forwarded to
        ``mo.ui.table`` as ``**kwargs``:

        ``pagination``, ``selection``, ``initial_selection``, ``page_size``,
        ``show_column_summaries``, ``show_data_types``, ``format_mapping``,
        ``freeze_columns_left``, ``freeze_columns_right``,
        ``text_justify_columns``, ``wrapped_columns``, ``column_widths``,
        ``hidden_columns``, ``visible_columns``, ``header_tooltip``,
        ``show_download``, ``max_columns``, ``show_search``, ``label``,
        ``on_change``, ``style_cell``, ``hover_template``, ``max_height``.

        (Keyword list generated for marimo 0.23.13.)

        As a convenience, ``header_tooltip=True`` populates the tooltip of
        every column with its full name (useful when narrow widths truncate
        the header). Column names are never renamed.
        """
        import pandas as pd

        option_keys = self._option_keys()
        opt = {k: getattr(self, f"_{k}") for k in option_keys}
        for k in option_keys:
            if k in overrides:
                opt[k] = overrides.pop(k)

        if isinstance(data, pd.Series):
            data = data.to_frame(name="value" if data.name is None else data.name)

        column_widths, default_width = opt["column_widths"], opt["default_width"]
        has_widths = bool(default_width) or bool(column_widths)
        kwargs = dict(
            selection=None,
            pagination=None,
            show_column_summaries=opt["column_summaries"],
            show_data_types=opt["data_types"],
            format_mapping=self._format_mapping(
                data, opt["precision"], opt["datetime_format"]
            ),
            column_widths=(
                self._native_widths(data, column_widths, default_width)
                if has_widths else None
            ),
            style_cell=(
                self._style_cell(column_widths, default_width)
                if has_widths else None
            ),
        )
        kwargs.update(overrides)
        # ``header_tooltip=True`` -> show each column's full name on hover, handy
        # when narrow widths truncate the header. marimo renders the table inside
        # a shadow DOM, so injected CSS cannot reach the header; a tooltip is the
        # only external lever for reading long/overlapping names.
        if kwargs.get("header_tooltip") is True:
            key = self._column_key
            kwargs["header_tooltip"] = {key(c): str(c) for c in data.columns}
        return mo.ui.table(data, **kwargs)

    def _apply(self) -> None:
        """Register marimo's opinionated DataFrame/Series formatters."""
        import pandas as pd
        from marimo._output import formatting

        @formatting.opinionated_formatter(pd.DataFrame)
        def _show_dataframe(df):
            return self.table(df)._mime_()

        if self._series:
            @formatting.opinionated_formatter(pd.Series)
            def _show_series(s):
                return self.table(s)._mime_()


class MoOptions:
    def __init__(self) -> None:
        self.mogrid = MogridOptions()
        self.df = DataframeOptions()


mopt = MoOptions()


def mogrid(*args, backend: Backend | str | None = None, **kws):
    """Show an image grid in marimo, using the configured backend.

    :param backend: 'mpl' - matplotlib via :func:`iad.vis.insight.imgrid`
                    'ply' - Plotly via :func:`iad.vis.plgrid.imgrid`
                    'wgt' - anywidget via :func:`iad.vis.imview.imgrid`
                    'imv' - imv via :func:`iad.vis.imview.imgrid`
                    None - use ``mo_options.mogrid.backend`` (default)
    """
    backend = Backend(backend) if backend is not None else mopt.mogrid.backend

    if backend == Backend.PLY:
        from iad.vis.plgrid import imgrid
        return imgrid(*args, **kws)
    if backend == Backend.WGT:
        from iad.vis.imview import imgrid
        return imgrid(*args, **kws)
    if backend == Backend.IMV:
        from iad.vis.imview import imgrid
        return imgrid(*args, **kws)
    else:
        from iad.vis.insight import imgrid
        return mo.mpl.interactive(imgrid(*args, **kws, out='fig'))
