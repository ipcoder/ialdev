import pytest

from types import SimpleNamespace

from iad.core.codetools import call_args_expr
from iad.core.datatools import zip_dict
from iad.core.wrap import name_func_outputs, namedtuple

dicts = {1: 11, 2: 12, 3: 13}, {1: 21, 2: 22, 4: 24}, {1: 31, 3: 33}


def test_zip_dict_strict():
    try:
        res = zip_dict(*dicts, strict=True)
    except KeyError:
        pass
    else:
        assert False  # Exception is expected for mismatched dicts in strict mode!


def test_zip_dict_fillvalue():
    fillvalue = 'XXX'
    assert zip_dict(*dicts, fillvalue=fillvalue)[4][::2] == (fillvalue,) * 2


def test_zip_dict_skip():
    assert len(zip_dict(*dicts, skip=True)) == 1


def test_namedtuple():
    vals = (1, 2, 3)
    fields = tuple('xyz')
    NT = namedtuple('Test', fields, vals)
    t = NT()
    assert t == vals
    assert t._fields == fields

    slc = slice(0, 2)
    assert t._part(slc) == t[slc]
    assert t._part(slc)._fields == fields[slc]


def test_name_outputs():
    f0 = lambda x: tuple(range(x)) if x > 1 else 0
    names = list('xyz')

    with pytest.raises(TypeError):
        f = name_func_outputs(f0, 'xyz')  # must be list of names

    f = name_func_outputs(f0, names)
    out = f(3)
    assert (out.x, out.y, out.z) == tuple(range(3))

    f2 = name_func_outputs(f, names)
    assert f is f2
    assert f2._name_outputs['nest'] == f._name_outputs['nest'] == 0

    with pytest.raises(RuntimeError):
        f2 = name_func_outputs(f, names, nest=False)

    f2 = name_func_outputs(f, names, nest=True)
    assert f2 is not f
    assert f2(3) == f(3) == f(3)
    assert f2._name_outputs['nest'] == 1

    f2 = name_func_outputs(f, names[:2])   # a different wrapping
    assert f is not f2
    assert f2._name_outputs['nest'] == 1

    with pytest.raises(RuntimeError):
        out = f(2)

    f = name_func_outputs(f0, names, adjust=True)
    out = f(2)
    assert (out.x, out.y) == tuple(range(2))

    f = name_func_outputs(f0, names, adjust=None)
    out = f(2)
    assert out == tuple(range(2)) and not hasattr(out, '_fields')
    out = f(1)


    # out dict
    f = name_func_outputs(f0, names, out_type=dict, adjust=True)
    out = f(2)
    assert (out['x'], out['y']) == (0, 1)
    assert f(1) == {'x': 0}

    f = name_func_outputs(f0, names, out_type=dict, adjust=None)
    out = f(2)
    assert out == tuple(range(2))
    assert f(1) == 0


def test_call_args_expr_direct():
    """Test Target: baseline recovery of positional arg source text via call_args_expr.
    Failure Triggers: AST match broken for plain Name callees; source segment extraction regresses."""
    captured = []

    def probe(a, b):
        captured.append(call_args_expr())

    x, y = 1, 2
    probe(x, y + 1)
    assert captured == [['x', 'y + 1']]


def test_call_args_expr_aliased():
    """Test Target: call_args_expr finds the call when the callee is an import/local alias.
    Failure Triggers: matching requires literal def name in source; alias resolution dropped."""
    captured = []

    def probe(a, b):
        captured.append(call_args_expr())

    alias = probe
    left, right = 3, 4
    alias(left, right)
    assert captured == [['left', 'right']]


def test_call_args_expr_attribute():
    """Test Target: call_args_expr finds calls made through module/object attributes.
    Failure Triggers: Attribute callees ignored; getattr chain lookup fails for SimpleNamespace."""
    captured = []

    def probe(a, b):
        captured.append(call_args_expr())

    ns = SimpleNamespace(probe=probe)
    u, v = 5, 6
    ns.probe(u, v)
    assert captured == [['u', 'v']]


def test_call_args_expr_nested_aliased():
    """Test Target: level=2 + name= recovery through an aliased outer function (imgrid chain).
    Failure Triggers: nest_level arithmetic wrong; alias breaks name= cross-check or AST match."""
    captured = []

    def outer(a, b):
        def inner():
            captured.append(call_args_expr(2, name='outer'))
        inner()

    aliased = outer
    p, q = 7, 8
    aliased(p, q)
    assert captured == [['p', 'q']]


def test_call_args_expr_assignment_form():
    """Test Target: arg source text when the call is an RHS of an assignment (not line-leading).
    Failure Triggers: get_source_segment applied to call substring with absolute col_offsets."""
    captured = []

    def probe(a, b):
        captured.append(call_args_expr())

    alias = probe
    left, right = 1, 2
    result = alias(left, right)
    assert captured == [['left', 'right']]
    assert result is None


def test_call_args_expr_unrecoverable_raises():
    """Test Target: NameError still raised when the callee expression cannot be resolved.
    Failure Triggers: getattr-dispatched calls silently accepted; guard in assign_args_names has nothing to catch."""
    def probe(a):
        return call_args_expr()

    ns = SimpleNamespace(probe=probe)
    with pytest.raises(NameError, match='not found on level'):
        # Call AST is Call(func=Call(getattr(...))) — no Name/Attribute path to resolve.
        getattr(ns, 'probe')(9)


if __name__ == '__main__':
    test_namedtuple()
