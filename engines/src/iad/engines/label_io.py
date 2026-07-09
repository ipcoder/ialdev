from __future__ import annotations

import dataclasses as dcls
from typing import Iterator, Tuple, Any, Dict

from iad.core.data.labeled import Labeled, LabeledType
from iad.core.data.nptools import Array
from iad.core.strings import compact_repr, hash_str

MISSING = dcls.MISSING
_MISSING_TYPE = type(MISSING)
OPTIONAL = _MISSING_TYPE()


def labeled_type(data=Array, frozen_defaults=True, validate_type=True, **labels):
    """ alias: ``LT``, wraps ``LabeledType``

    Create Labeled data type from keyword arguments
    with default `data` label.

    >>> ShotType = LT(angle=int, axis='vertical')      # Defines data type
    >>> assert 'data' in ShotType         # type supports `contains` query
    >>> shot = ShotType(image, angle=60)               # create instance
    >>> assert shot.data is image                      # presumed data key
    >>> assert shot.axis == 'vertical'            # access as attribute
    >>> assert shot['angle'] == 60                # or like dictionary
    >>> shot['comment'] = "Add a new fields to the instance"
    >>> assert type(shot.comment) is str

    :param data: label reserved for the data container
    :param frozen_defaults: True - not allow change default values
    :param validate_type: True - ensure declared types of values
    :param labels: rest of the labels
    """
    return LabeledType(data=data,
                       frozen_defaults=frozen_defaults,
                       validate_type=validate_type, **labels)


LT = labeled_type


class DataC:
    """ Base Mix in class for DataStruct creation"""

    # FixMe: Make DataC pickleable! Reproduce, Low

    def __repr__(self):
        cls = self.__class__
        anns = cls.__annotations__

        def smart_join(lines):
            n = len(anns)
            max_len = max(map(len, lines))
            if n < 3 and max_len < 20:
                sep, frm = ', ', "({})"
            else:
                sep = '\n\t'
                frm = f':{sep}{{}}'
            return frm.format(sep.join(lines))

        def repr_item(v):
            is_compact = hasattr(v, '__repr__') and \
                         getattr(v.__repr__, 'is_compact', False)
            return (repr if is_compact else compact_repr
                    )(v).replace('\n', '\n\t')

        fields = [f"{k}={repr_item(v)}" for k, v in self]
        return cls.__name__ + smart_join(fields)

    def _set_field(self, key, value, tp=None):
        """ Set field value considering the type

        :param key: MUST be key in self.__dataclass_fields__
        :param value: value being assigned
        :param tp: type as declared for this dataclass field's or
                   acquires it from there if None
        """
        tp = tp or self.type(key)
        if issubclass(type(tp), type) and not isinstance(value, tp):
            from iad.core.data.pdtools import DataTable, DataSeries
            if isinstance(tp, DCType) and isinstance(value, (DataTable, DataSeries)):
                value = tp.from_table(value)
            else:
                value = tp(value)
        self.__dict__[key] = value

    def __post_init__(self):
        """
        Allows compact initialization of the fields with  by providing
        only data or dict to be passed to the constructor here
        instead of explicitly calling it in the code and passing
        instances of the
        :return:
        """
        pass

    def hash(self, sz: int = None) -> str:
        """Return hash of all the ietns using ony name and data field"""
        from xxhash import xxh64_hexdigest
        hashes = ''.join((hash_str(name) + xxh64_hexdigest(val.data))
                         for name, val in self)
        return hash_str(hashes, sz)

    def to_table(self, *, force=False, key='data') -> 'DataTable':
        """
        Converts to DataTable not missing fields assuming all the fields are LabeledData.
        If not - raise TypeError (unless forced explicitly!)

        :param force:  force not labeled values into {key: value}
        :param key: key used when forcefully label data
        :return: DataTable
        """
        if not type(self).all_labeled:
            if not force:
                raise TypeError(f"Failed to convert not labeled data {self} to table")
            fields = {k: (v if isinstance(v, dict) else {key: v})
                      for k, v in self.items()}
        else:
            fields = self.to_dict()

        from iad.core.data.pdtools import DataTable
        return DataTable.from_dict(fields, orient='index')

    def to_dict(self):
        return {k: (dict(v) if isinstance(v, Labeled) else v) for k, v in self}

    def __iter__(self):
        """Iterate over NOT MISSING fields (field, value) items"""
        return filter(DCType.not_missing, self.__dict__.items())

    def __len__(self):
        return sum(map(bool, self))

    def __contains__(self, name):
        """Check if a field with given name exists and initialized"""
        return name in self.__dict__ and DCType.not_missing(self.__dict__[name])

    def fields_names(self) -> Iterator[str]:
        """Iterator over not initialized fields names.
        Note: use vars(self) to see all the fields."""
        return (it[0] for it in self)

    def fields_values(self) -> Iterator:
        """Iterator over not initialized fields names.
        Note: use vars(self) to see all the fields."""
        return (it[1] for it in self)

    def flat_labels(self, *, names=False, sep='_', data='data') -> Iterator[Tuple[str, Any]]:
        """Return iterator over fields items (name, value) as they are
        unless value is ``Labeled`` data type, in which case
        it is flattened into single (string, data) item to be yielded.
        Prepend field's name if it does not appear in the labels.

        Useful to convert dataclass with labeled fields into
        ``dict`` with descriptive keys and homogeneous data values,
        for example for plotting.

        Note, that with no labeled field this iterator is equivalent
        to the ``self`` iterator.

        :param names: if True attempt to include fields names into keys
        :param sep: separator used for flattening
        :param data: data field name
        :return: iterator over tuple(name, data)
        """
        for name, val in self:
            if isinstance(val, Labeled):
                def in_values(x):
                    for v in val.values():
                        if isinstance(v, str) and x == v:
                            return True
                    return False

                pfx = "" if not names or in_values(name) else f"{name}{sep}"
                key, val = val.flat(sep=sep, data=data)
                name = pfx + key
            yield name, val

    def __setattr__(self, key, value):
        # apply type conversions if setting defined field with REAL value, or use standard way
        # for new attributes or when internal initializations are setting MISSING or OPTIONAL
        if key in self.__dataclass_fields__ and DCType.not_missing(value):
            self._set_field(key, value)
        else:
            super().__setattr__(key, value)

    @classmethod
    def from_table(cls: DCType, db: 'DataTable'):
        kws = {k: f.type.from_table(
            db, missing=OPTIONAL if f.default is OPTIONAL else KeyError
        ) for k, f in cls.defined_fields.items()}
        return cls(**kws)

    @classmethod
    def type(cls, field: str) -> type:
        """Return type of specific field.
        Useful for fields initializations:

        >>> DS.type('')(data, kind='disp')  # Init labeled data
        """
        return cls.__dataclass_fields__[field].type


class DCType(type):
    """Extends dataclass generation capabilities with:

    - defining dataclass template as a python type
    - descriptive representation of such types
    - ``MISSING`` marker to indicate not initialized fields
    - methods to query the type structure:
      ``defined_fields``, ``fields_types``,

    - work with its instances like collections:
      ``__iter__``, iter
    - conversions: ``to_table``, ``from_table``

    **Safe mutable defaults**

    Detect default mutable values of fields and replace them with
    ``default_factory`` field initialization function,
    which call the constructor with this value as input.

    For example, instead of defining field like ``a`` (below) one may safely
    define it like ``b`` which actually will produce code like in ``c``,
    which also covers cases like ``d``.

    >>> @DCType
    >>> class C:
    >>>     a: dict = DCType.field(default_factory=dict)
    >>>     b: dict = {}            # makes that safe
    >>>     c: dict = DCType.field(default_factory=lambda: dict({1:2,3:4}))
    >>>     d: dict = {1:2,3:4}     # makes that safe

    For other than ``MutableSequence``, ``MutableSet``, ``MutableMapping`` types
    with straightforward initialization in constructor ``dc.field`` must be used!

    **Labeled Type Fields**

    From DEFINED fields' labels find common subset and return
    it and unique parts of the labels separately.

    >>> @DCType
    >>> class Inputs:
    ...     imL: LT(kind='image', alg='cam', view='L'),
    ...     imR: LT(kind='image', alg='cam', view='R'))

    Parsing separates the common set of labels as *input filter*
    from the unique labels specifying the *input labels*:

    >>> Inputs.common == dict(kind='image', alg='cam')
    >>> Inputs.unique == dict(
    ...     imL=dict(view='L')
    ...     imR=dict(view='R'))

    :param fields_labels: dict of the fields labels
    :return: common: labels unique: {fields: labels}
    """
    field = dcls.field  # to allow (... a: dict = DCType.field(default_factory=dict))

    @staticmethod
    def not_missing(v) -> bool:
        """Check if v is a missing kind of value or an item containing such

        :param v: value to check or item tuple (field, value)
        :return: False if MISSING kind else True
        """
        return not isinstance(v[1] if isinstance(v, tuple) else v, _MISSING_TYPE)

    @staticmethod
    def _safe_mutable_default(cls):
        """Update `cls` `__dict__`"""

        def construct_factory(tp, v):
            return lambda: tp(v)

        from typing import MutableSequence, MutableSet, MutableMapping
        for k, tp in cls.__annotations__.items():
            if k not in cls.__dict__:
                continue
            v = cls.__dict__[k]
            if type(tp) is type and issubclass(
                    type(v), (MutableSequence, MutableSet, MutableMapping)):
                type.__setattr__(cls, k, dcls.field(default_factory=construct_factory(tp, v)))

    def __repr__(cls):
        """Provides better description for Inputs class structure"""
        repr_type = lambda t: str(t).replace('\n', '\n\t')
        fields = '\n\t'.join(f"{k}: {repr_type(tp)}" for k, tp in cls.__annotations__.items())
        return f"Data class `{cls.__qualname__}`:\n\t{fields}"

    def __new__(mcs, name, bases=(), attrs=None, *,
                strict=True, globalns=None, localns=None):
        """
        Create new class, supporting two usage formats:
          1. regular `type` like arguments: (name, bases, attrs)
          2. `dataclass` like from class: (cls)

        As in the case of the dataclass definition fields may be defined
        with type hints.
        From python 3.10 or (3.7 with `from __future__ import annotation)
        the evaluation of the type hinting is postponed.
        To support this the metaclass may require contexts of class definition,
        in form of local and global namespaces, as in the example below
        where TypeA and TypeB definitions are presumable found.

        >>> class X(metaclass=DCType, globalns=globals(), localns=locals()):
        ...     a: TypeA
        ...     b: TypeB

        Which is equivalent to the alternative form:

        >>> class X:
        ...     a: TypeA
        ...     b: TypeB
        >>> X = DCType(X, globalns=globals(), localns=locals())

        :param name: name or class
        :param bases: tuple with bases (ignored if class)
        :param attrs: dict namespace (ignored if class)
        :param globalns: global namespace where class is defined
        :param localns: locsl namespace where class is defined
        """
        if isinstance(name, type):
            cls = name
            name = cls.__name__
            bases = cls.__bases__
            attrs = dict(cls.__dict__)
            qualname = cls.__qualname__
            for k in ('__dict__', '__weakref__', '__module__'):
                attrs.pop(k, None)
        else:
            qualname = name
            attrs = attrs or {}
        from typing import get_type_hints

        if not any(issubclass(b, DataC) for b in bases):
            bases = (DataC, *bases)
        new_cls = type.__new__(mcs, name, bases, attrs)
        new_cls.__qualname__ = qualname
        new_cls.__annotations__ = get_type_hints(new_cls, globalns=globalns, localns=localns)

        DCType._safe_mutable_default(new_cls)

        new_cls = dcls.dataclass(new_cls, repr=False)

        fields_types = new_cls.fields_types
        # all the fields attributes of the new class are types!
        # FixMe: @Ilya why to assign type as value. That ruins inheritance!
        for k, tp in fields_types.items():
            setattr(new_cls, k, tp)

        all_labeled = all(map(lambda t: isinstance(t, LabeledType), fields_types.values()))
        from iad.core.datatools import common_dict
        common, unique = all_labeled and common_dict(
            {k: t._defaults for k, t in fields_types.items()},
            unique=True) or ({}, {})

        setattr(new_cls, '_strict', strict)
        setattr(new_cls, '_all_labeled', all_labeled)
        setattr(new_cls, 'common_labels', common)
        setattr(new_cls, 'unique_labels', unique)
        return new_cls

    def __init__(self, *args, **kwargs):
        pass

    @property
    def defined_fields(cls) -> Dict[str, dcls.Field]:
        """Collection of fields' names"""
        return cls.__dataclass_fields__

    @property
    def fields_types(cls) -> Dict[str, type]:
        """{name: type} dict of the data fields"""
        return {k: f.type for k, f in cls.defined_fields.items()}

    @property
    def all_labeled(cls) -> bool:
        """Return True if all the fields are of LabeledType"""
        return cls._all_labeled

    @property
    def optional_fields(cls):
        """Set of optional fields names"""
        return {k for k, f in cls.defined_fields.items() if f.default is OPTIONAL}
