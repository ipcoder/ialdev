from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .label import Labels

if TYPE_CHECKING:
    from .pdtools import DTable

__all__ = ['Labeled', 'LabeledType']


class Labeled(Labels):
    """
    Base ABSTRACT class for Labeled data types - an extended dict containing data
    in one field and descriptive labels in the others.

    Actual Labeled Data types are created for specific collection of labels
    (by ``LabeledType`` metaclass) using ``labeled_type()`` or ``LT`` alias
    """

    @classmethod
    def type_keys(cls) -> tuple:
        return *cls._defaults, *cls._undefined

    UNDEF = object()

    def __eq__(self, other):
        if not (isinstance(other, dict) and len(self) == len(other)):
            return False
        no_key = object()
        try:
            for k, vo in other.items():
                if (v := self.get(k, no_key)) is no_key:
                    return False
                na = isinstance(v, np.ndarray) + isinstance(vo, np.ndarray)
                if na == 1 or na == 0 and vo != v or na == 2 and not np.array_equal(vo, v):
                    return False
        except Exception as ex:  # various not comparable types
            print(ex)
            return False
        return True

    def __init__(self, data=UNDEF, **kws):
        """
        Support dict-like initializations:
            A(data=2, b=3) and A({'data':2, 'y':3})
        and silent data field:
            A(2, b=3)  == A(data=2, b=3)
        :param data: not defined or data or dict with labels (like kws)
        :param kws: labels key, values
        """
        cls = type(self)
        if cls is Labeled:
            raise RuntimeError(f"Class {cls} is a mixin class not intended for instantiation.")

        # ---- STEP 1 - convert inputs into homogeneous form
        if data is not self.UNDEF:
            # support Labeled(dict) like initialization
            if isinstance(data, dict) and self._all_keys.issuperset(data):
                kws.update(data)
            else:
                assert 'data' in self._all_keys, "unnamed argument allowed only if 'data' field defined!"
                kws['data'] = data

        # ---- STEP 2 - check all the conditions are met
        if missing := set(self._undefined).difference(kws):
            raise KeyError(f"labels {missing} not initialized in {cls}!")

        if violated := '\n\t'.join(
                f"{k}={assigned} ({expected=})"
                for k in self._frozen_defaults.intersection(kws)
                if (expected := self._defaults[k]) != (assigned := kws[k])
        ): raise KeyError(f"Initialization of {cls} violates frozen defaults:\n {violated}")

        if self._frozen_keys and not self._all_keys.issuperset(kws):
            raise KeyError(f"Undefined keys {set(kws).difference(self._all_keys)} in frozen {cls}")

        # ---- STEP 3 - initialize the items
        super().__init__(self._defaults)  # first fill with defaults
        # then assign from the arguments
        for k, v in kws.items():
            if self._validate_type and \
                    (tp := self._undefined.get(k, False)) and \
                    type(tp) is type and not isinstance(v, tp):
                v = tp(v)
            self[k] = v

    def flat(self, *, sep='_', exclude='data', data='data', fmt=None) -> tuple[str, np.ndarray]:
        """
        Merge labels into a single string and produce a tuple (flatten_label, data)

        :param sep: separator when joining
        :param exclude: keys exclude from the join
        :param data: key of the data field returned as second item in the tuple
        :param fmt: optional str.format sting, if provided ignores arguments:
                sep, exclude, keys
        :return: tuple(joint_label, data_item)
        """
        from iad.core import as_iter
        data = self[data]
        if fmt:
            return fmt.format(**self), data

        excluded = set(as_iter(exclude))
        included = lambda _: _[0] not in excluded
        str_val = lambda _: str(_[1])
        return sep.join(map(str_val, filter(included, self.items()))), data

    def __setattr__(self, item, val):
        if item in self:
            self[item] = val
        else:
            super().__setattr__(val)

    @classmethod
    def from_table(cls, db: DTable, *, missing=KeyError, undef=()):
        """
        Create instance of this Labeled type from :cls:`iad.core.data.pdtools.DataTable`
        All the pre-defined keys are used to query the index.
        All the undefined keys must be in the table and are initialized

        If table does not contain given label, then depending on the value of ``missing``:
         - `issubclass(missing, BaseException)` - raise `missing(f"{type(ex)}({ex.args})")`
         - `isinstance(missing, BaseException)` - raise `missing`
         - otherwise, return `missing`

        :param db:
        :param missing: Exception class, instance, or value to return
        :param undef: keys listed here are forced to be considered as undefined
        :return:
        """
        if undef:
            undef = set(undef)
            if undef := undef.difference(cls._undefined):  # undef not already undefined
                if not_defined := undef.difference(cls._defaults):  # must be defined!
                    raise KeyError(f"Unknown keys: {not_defined}")
            # move defined undef from defined into undefined
            defined = {k: v for k, v in cls._defaults.items() if k not in undef}
            undefined = [*undef, cls._undefined]
        else:
            defined = cls._defaults
            undefined = [*cls._undefined]

        try:
            res = db.select(defined)
        except (KeyError, LookupError) as ex:
            if isinstance(missing, BaseException):
                raise missing
            elif isinstance(missing, type) and issubclass(missing, BaseException):
                raise missing(f"{type(ex)}({ex.args})")
            return missing
        if hasattr(res, 'columns'):
            res = res[undefined]
        elif not (len(undefined) == 1 and res.name == undefined[0]):
            raise KeyError(f"Table does not contain required keys {undefined}")
        return cls(**res.reset_index().iloc[0].to_dict())


class LabeledType(type):
    """ Metaclass to create Labeled Data classes extending ``dict``,
    but built around predefined keys with optional default values.

    Main purpose of such classes to ensure that during instantiation all
    those keys are initialized either by their defaults or as arguments.

    Note: additional keys except those defined in the class may be added.

    Classes are supposed to be created by directly calling this meta:

    >>> LabeledXY = LabeledType(x=10, y=int)
    >>> d = LabeledXY(y=2)   # LT(x=2) raise exception for undefined y!
    >>> assert d['y'] == 10
    >>> assert type(d.__name__) == 'Labeled'  # default class name
    >>> LabeledData = LabeledType('LabeledData', x=10, y=int)
    >>> assert LabeledData.__name__ == 'LabeledData'  # custom class name

    To encorage usage of 'data' key for data its positional initialization
    is supported if data key is introduced explicitely or using `LD` function
    >>> LabeledData = LabeledType(data=NDArray, y=int) # equivalent = LD(y=int)
    >>> d = LabeledData([1,2,3], y=20)
    >>> assert d['data'] == [1,2,3]
    """

    def __repr__(cls):
        undefined = (f"{k}: {v.__name__}" for k, v in cls._undefined.items())
        defaults = (f"{k}={v}" for k, v in cls._defaults.items())
        return f"{cls.__qualname__}<{', '.join((*undefined, *defaults))}>"

    def __new__(mcs, _name=None, *, validate_type=False,
                frozen_defaults=False, frozen_keys=False,
                **labels):
        """
        :param _name: Name of the created class
        :param validate_type: perform casting on keys initialization if possible
        :param frozen_defaults: allow change default values (False)
               use True to define templates
        :param frozen_keys: allow not defined keys
        :param labels: dict with {key: default_value} and {key: type} items
        """
        _name = _name or f"Labeled"
        # 'undefined' are keys assigned by types, not
        # default values which would be called 'defaults'.
        cls = super().__new__(mcs, _name, (Labeled,), {})

        cls._undefined = {k: labels.pop(k) for k in
                          [_ for _, v in labels.items() if type(v) is type]}
        cls._defaults = labels
        cls._all_keys = {*cls._undefined, *cls._defaults}

        frozen_defaults = cls._defaults if frozen_defaults is True else \
            [] if frozen_defaults is False else frozen_defaults
        cls._frozen_defaults = {*frozen_defaults}
        cls._frozen_keys = frozen_keys
        cls._validate_type = validate_type
        return cls

    def __init__(mcs, _name=None, *, validate_type=False,
                 frozen_defaults=False, frozen_keys=False,
                 **labels):
        """
        :param _name: Name of the created class
        :param validate_type: perform casting on keys initialization if possible
        :param frozen_defaults: allow change default values (False)
               use True to define templates
        :param frozen_keys: allow not defined keys
        :param labels: dict with {key: default_value} and {key: type} items
        """
        pass  # to avoid calling type.__init__ with unusual arguments

    def __contains__(cls, item):
        return item in cls._defaults or item in cls._undefined

    @property
    def undefined(cls):
        """keys with undefined default values"""
        return cls._undefined.keys()

    @property
    def default(cls):
        """keys with defined default values"""
        return cls._defaults.keys()

    @property
    def defined(cls):
        """set of ALL the keys with undefined AND default values"""
        return cls._all_keys
