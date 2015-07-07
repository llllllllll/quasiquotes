from collections import ChainMap
from ctypes import pythonapi, c_int, py_object
from distutils.sysconfig import get_python_inc
import os
import sys
from tempfile import NamedTemporaryFile


from .utils.shell import Executable, Flag
from .utils.path import temp_path


cc = Executable('cc')


_template = """\
#include <Python.h>

static PyObject *
__f(PyObject *self, PyObject *__args, PyObject *__kwargs)
{{
    PyObject *__return;
    char *__keywords[] = {keywords};
{localdecls}

    if (!PyArg_ParseTupleAndKeywords(
            __args, __kwargs, {fmt}, __keywords, {kwargs})) {{
        return NULL;
    }}

    /* BEGIN USER BLOCK */
{code}
    /* END USER BLOCK */

    if (!(__return = PyDict_New())) {{
        return NULL;
    }}
{localassign}
    return __return;
}}


static struct PyMethodDef module_functions[] = {{
    {{"f", (PyCFunction) __f, METH_VARARGS | METH_KEYWORDS, ""}},
    {{NULL}},
}};

static struct PyModuleDef module = {{
    PyModuleDef_HEAD_INIT,
    "{modname}",
    "",
    -1,
    module_functions,
    NULL,
    NULL,
    NULL,
    NULL
}};

PyMODINIT_FUNC
PyInit_{modname}(void)
{{
    return PyModule_Create(&module);
}}
"""


def _notdunder(name):
    return not (name.startswith('__') and name.endswith('__'))


def _make_c_func(code, frame):
    """Create the C function based off of the user code.

    Parameters
    ----------
    code : str
        The user code to use to create the function.
    frame : frame
        The first stackframe where this code is being compiled.

    Returns
    -------
    f : callable
        The C function from user code.
    """
    names = tuple(sorted(
        frame.f_locals.keys() | filter(_notdunder, frame.f_globals.keys()),
    ))

    with NamedTemporaryFile(suffix='.c') as f, \
            NamedTemporaryFile(suffix='.so') as object_file, \
            temp_path(os.path.dirname(f.name)):

        modname = os.path.basename(object_file.name)[:-3]
        f.write(_template.format(
            modname=modname,
            fmt='"{}"'.format('O' * len(names)),
            keywords='{' + ', '.join(map('"{}"'.format, names)) + ', NULL}',
            kwargs=', '.join(map('&{}'.format, names)),
            localdecls='\n'.join(
                map('    PyObject *{} = NULL;'.format, names),
            ),
            code='\n'.join(map('    '.__add__, code.splitlines())),
            localassign='\n'.join(map(
                '    {0} &&'
                ' PyDict_SetItemString(__return, "{0}", {0});'.format,
                names,
            )),
            ).encode('utf-8'),
        )
        f.flush()
        _, err, status = cc(
            Flag.O(3),
            Flag.I(get_python_inc()),
            Flag.f('PIC'),
            Flag.shared,
            Flag.o(object_file.name),
            f.name,
        )
        if err:
            raise ValueError(err)

        return __import__(modname).f


def c(code):
    """Execute inline C code respecting scoping rules.

    Parameters
    ----------
    code : str
        C source code to execute.
    """
    frame = sys._getframe().f_back
    entry = frame.f_code, frame.f_lineno
    cache = c._cache
    locals_ = frame.f_locals
    ns = ChainMap(
        locals_,
        {k: v for k, v in frame.f_globals.items() if _notdunder(k)},
    )

    try:
        f = cache[entry]
    except KeyError:
        f = cache[entry] = _make_c_func(code, frame)

    local_keys = locals_.keys()
    locals_.update({k: v for k, v in f(**dict(ns)).items() if k in local_keys})
    pythonapi.PyFrame_LocalsToFast(py_object(frame), c_int(1))

c._cache = {}
