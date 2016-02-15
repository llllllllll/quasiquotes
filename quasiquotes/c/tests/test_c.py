# coding: quasiquotes

import pytest

from quasiquotes.c import c


qq = c(keep_c=False, keep_so=False)  # no caching
globalvar = 'globalvar'  # global lookup for checking scope resolution


def test_local_lookup_stmt():
    localvar = 'localvar'
    out = [None]

    with $qq:
        Py_INCREF(localvar);
        PyList_SetItem(out, 0, localvar);

    assert out[0] is localvar


def test_local_lookup_expr():
    localvar = 'localvar'
    assert [$qq|Py_INCREF(localvar); localvar|] is localvar


def test_local_reassign():
    localvar = 'original'

    with $qq:
        if (!(localvar = PyUnicode_FromString("updated"))) {
            return NULL;
        }

    assert localvar == 'updated'


def test_global_lookup_stmt():
    out = [None]

    with $qq:
        Py_INCREF(globalvar);
        PyList_SetItem(out, 0, globalvar);

    assert out[0] is globalvar


def test_global_lookup_expr():
    assert [$qq|Py_INCREF(globalvar); globalvar|] is globalvar


def test_builtin_lookup_stmt():
    out = [None]

    with $qq:
        Py_INCREF(id);
        PyList_SetItem(out, 0, id);

    assert out[0] is id


def test_builtin_lookup_expr():
    assert [$qq|Py_INCREF(id); id|] is id


def test_locals_over_globals_stmt():
    globalvar = 'localvar'
    out = [None]

    with $qq:
        Py_INCREF(globalvar);
        PyList_SetItem(out, 0, globalvar);

    assert out[0] is globalvar
    assert out[0] == 'localvar'


def test_locals_over_globals_expr():
    globalvar = 'localvar'
    result = [$qq|Py_INCREF(globalvar); globalvar|]
    assert result is globalvar
    assert result == 'localvar'


@pytest.yield_fixture
def patch_id():
    global id

    id = 'globalvar'
    try:
        yield id
    finally:
        del id


def test_globals_over_builtins_stmt(patch_id):
    out = [None]

    with $qq:
        Py_INCREF(id);
        PyList_SetItem(out, 0, id);

    assert out[0] is patch_id
    assert out[0] == 'globalvar'


def test_globals_over_builtins_expr(patch_id):
    result = [$qq|Py_INCREF(id); id|]
    assert result is patch_id
    assert result == 'globalvar'
