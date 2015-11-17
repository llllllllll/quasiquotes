from collections import ChainMap
from ctypes import pythonapi, c_int, py_object
from distutils.sysconfig import get_python_inc
from hashlib import md5
import operator as op
import os
import re
from textwrap import dedent


from .quasiquoter import QuasiQuoter
from .utils.instance import instance
from .utils.shell import Executable, Flag


cc = Executable('cc')


class CompilationError(Exception):
    """An exception that indicates that cc failed to compile the given C code.
    """
    def __str__(self):
        return '\n' + self.args[0]


@instance
class c(QuasiQuoter):
    """Quasiquoter for inlining C.

    Parameters
    ----------
    keep_c : bool, optional
        Keep the generated *.c files. Defaults to False.
    keep_so : bool, optional
        Keep the compiled *.so files. Defaults to True.

    Methods
    -------
    quote_stmt
    quote_expr

    Notes
    -----
    You cannot pass arguments in the quasiquote syntax. You must construct
    a new instance of `c` and then use that as the quasiquoter. For example:

    ::

       with $c(keep_so=False):
           Py_None;

    is a syntax error. Instead, you must do:

    ::

       c_no_keep_so = c(keep_so=False)
       with $c_no_keep_so:
           Py_None;

    This is because of the way the quasiquotes lexer identifies quasiquote
    sections.
    """
    def __init__(self, *, keep_c=False, keep_so=True):
        self._keep_c = keep_c
        self._keep_so = keep_so
        self._stmt_cache = {}
        self._expr_cache = {}

    def __call__(self, **kwargs):
        return type(self)(**kwargs)

    _modname_template = '_qq_{base}_{line}_{col_offset}_{md5}'
    _missing_name_pattern = re.compile(
        r'^.+:\d+:\d+: error: ‘(.+)’ undeclared'
        r' \(first use in this function\)$',
        re.MULTILINE,
    )
    _modname_pattern = re.compile('[^0-9a-zA-Z]')

    _stmt_template = dedent(
        """\
        #include <Python.h>

        static PyObject *
        __qq_f(PyObject *__qq_self, PyObject *__qq_scope)
        {{
        {localdecls}
        {read_scope}

            /* BEGIN USER BLOCK */
            #line {lineno} "{filename}"
        {{
        {code}
        }}
            /* END USER BLOCK */

        {localassign}

        __qq_cleanup:
        {xdecrefs}

            Py_INCREF(__qq_scope);
            return __qq_scope;
        }}


        static struct PyMethodDef module_functions[] = {{
            {{"_quasiquoted", (PyCFunction) __qq_f, METH_O, ""}},
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
        """,
    )

    _expr_template = dedent(
        """\
        #include <Python.h>

        static PyObject *
        __qq_f(PyObject *__qq_self, PyObject *__qq_scope)
        {{
            PyObject *__qq_return;
        {localdecls}
        {read_scope}

            /* BEGIN USER BLOCK */
            #line {lineno} "{filename}"
            __qq_return = ({{
            #line {lineno} "{filename}"
        {code}
            /* END USER BLOCK */
        ;}});

        __qq_cleanup:
        {xdecrefs}

            return __qq_return;
        }}


        static struct PyMethodDef module_functions[] = {{
            {{"_quasiquoted", (PyCFunction) __qq_f, METH_O, ""}},
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
        """,
    )

    def quote_stmt(self, code, frame, col_offset):
        """Execute inline C code respecting scoping rules.

        Parameters
        ----------
        code : str
            C source code to execute.
        frame : frame
            The stackframe this is being executed in.
        col_offset : int
            The column offset of the code.
        """
        ns, locals_ = self._ns_from_frame(frame)
        self._resolve_stmt(code, frame, col_offset)(ns)  # mutates ns
        locals_.update(ns)
        pythonapi.PyFrame_LocalsToFast(py_object(frame), c_int(1))

    def quote_expr(self, code, frame, col_offset):
        """Execute an inline C expression respecting scoping rules.

        Parameters
        ----------
        code : str
            C source code to execute.
        frame : frame
            The stackframe this is being executed in.
        col_offset : int
            The column offset of the code.

        Returns
        -------
        result : any
            The result of the C expression.
        """
        return self._resolve_expr(code, frame, col_offset)(
            self._ns_from_frame(frame)[0]
        )

    @staticmethod
    def _entry_from_frame(frame, col_offset):
        """The tuple format for storing cached functions.

        Parameters
        ----------
        frame : frame
            The frame the code is in.
        col_offset : int
            The column offset of the code.

        Returns
        -------
        entry : tuple
            The cache key for the code.
        """
        return frame.f_code, frame.f_lineno, col_offset

    def _resolve(self, code, frame, col_offset, cache, mkfunc):
        """Find the function for the given entry.

        If the function is not already cached, then create it.

        Parameters
        ----------
        code : str
            The code string to compile.
        frame : frame
            The stack frame we are executing in
        col_offset : int
            The column offset of the quasiquoter.
        cache : dict
            The cache to use for lookups.
        mkfunc : callable
            The callable to use to create the new function if missing.

        Returns
        -------
        f : callable
            The compiled C function.
        """
        entry = self._entry_from_frame(frame, col_offset)

        try:
            return cache[entry]
        except KeyError:
            pass

        dir_, modname = self._dir_and_modname(code, *entry)
        try:
            f = cache[entry] = __import__(modname)._quasiquoted
            return f
        except ImportError:
            pass

        try:
            f = cache[entry] = self._compile(dir_, modname)
            return f
        except FileNotFoundError:
            pass

        f = cache[entry] = mkfunc(code, frame, col_offset)
        return f

    def _dir_and_modname(self, code, f_code, f_lineno, col_offset):
        name = self._modname_pattern.sub('_', f_code.co_filename)
        return (
            os.path.dirname(name),
            self._modname_template.format(
                base=os.path.basename(name).split('.', 1)[0],
                line=f_lineno,
                col_offset=col_offset,
                md5=md5(code.encode('utf-8')).hexdigest(),
            ),
        )

    def _resolve_stmt(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._stmt_cache, self._make_stmt,
        )

    def _resolve_expr(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._expr_cache, self._make_expr,
        )

    def _ns_from_frame(self, frame):
        """Construct a namespace from the given stack frame.

        Parameters
        ----------
        frame : frame
            The stack frame to use.

        Returns
        ns : dict
            The namespace.
        locals_ : dict
            The frame locals.
        """
        locals_ = frame.f_locals
        return dict(ChainMap(
            locals_,
            {k: v for k, v in frame.f_globals.items() if self._notdunder(k)},
        )), locals_

    @staticmethod
    def _notdunder(name):
        """Checks if name is not a magic name.

        Parameters
        ----------
        name : str
            The name to check.

        Returns
        -------
        notdunder : bool
            If the name is a magic name or not.
        """
        return not (name.startswith('__') and name.endswith('__'))

    def _make_func(self,
                   code,
                   frame,
                   col_offset,
                   kind,
                   *,
                   names=(),
                   _first=True):
        """Create the C function based off of the user code.

        Parameters
        ----------
        code : str
            The user code to use to create the function.
        frame : frame
            The first stackframe where this code is being compiled.
        col_offset : int
            The column offset of the code.
        kind : {'stmt', 'expr'}
            The type of function to create.
        names : iterable[str], optional
            The names to capture from the closing scope.

        Returns
        -------
        f : callable
            The C function from user code.
        """
        if kind == 'stmt':
            template = self._stmt_template
            extra_template_args = {
                'localassign': '\n'.join(
                    map(
                        '    {0} && PyDict_SetItemString(__qq_scope,'
                        ' "{0}", {0});'.format,
                        names,
                    ),
                ),
            }
        elif kind == 'expr':
            template = self._expr_template
            extra_template_args = {}
        else:
            raise ValueError(
                "incorrect kind ('{}') must be 'stmt' or 'expr'".format(kind),
            )

        dir_, modname = self._dir_and_modname(
            code,
            frame.f_code,
            frame.f_lineno,
            col_offset,
        )
        read_scope = '\n'.join(
            map(
                '    if (!({0} = PyDict_GetItemString(__qq_scope, "{0}"))) {{\n'
                '        PyErr_SetString(PyExc_NameError,\n'
                '                        "name \'{0}\' is not defined");\n'
                '        goto __qq_cleanup;\n'
                '    }}'.format,
                names,
            ),
        )
        cname = os.path.join(dir_, modname) + '.c'
        with open(cname, 'w+') as f:
            f.write(template.format(
                modname=modname,
                fmt='"{}"'.format('O' * len(names)),
                keywords=(
                    '{' + ', '.join(map('"{}"'.format, names)) + ', NULL}'
                ),
                kwargs=', '.join(map('&{}'.format, names)),
                localdecls='\n'.join(
                    map('    PyObject *{} = NULL;'.format, names),
                ),
                read_scope=read_scope,
                xdecrefs='\n'.join(map('    Py_XDECREF({});'.format, names)),
                lineno=frame.f_lineno,
                filename=frame.f_code.co_filename,
                code=code,
                **extra_template_args
            ))
            f.flush()

        try:
            return self._compile(dir_, modname)
        except CompilationError as e:
            if not _first:
                try:
                    os.remove(cname)
                except FileNotFoundError:
                    pass
                raise
            return self._make_func(
                code,
                frame,
                col_offset,
                kind,
                names=tuple(map(
                    op.methodcaller('group', 1),
                    self._missing_name_pattern.finditer(str(e)),
                )),
                _first=False,
            )

    def _compile(self, dir_, modname):
        basename = os.path.join(dir_, modname)
        cname = basename + '.c'
        soname = basename + '.so'
        os.stat(cname)  # raises FileNotFoundError if doesn't exist
        _, err, status = cc(
            Flag.O(3),
            Flag.I(get_python_inc()),
            Flag.f('PIC'),
            Flag.shared,
            Flag.o(soname),
            cname,
        )
        if not self._keep_c:
            os.remove(cname)
        if err:
            raise CompilationError(err)
        f = __import__(modname)._quasiquoted
        if not self._keep_so:
            os.remove(soname)
        return f

    def _make_stmt(self, code, frame, col_offset):
        """Create the C statement function based off of the user code.

        Parameters
        ----------
        code : str
            The user code to use to create the function.
        frame : frame
            The first stackframe where this code is being compiled.
        col_offset : int
            The column offset of the code.

        Returns
        -------
        f : callable
            The C function from user code.
        """
        return self._make_func(code, frame, col_offset, 'stmt')

    def _make_expr(self, code, frame, col_offset):
        """Create the C expression function based off of the user code.

        Parameters
        ----------
        code : str
            The user code to use to create the function.
        frame : frame
            The first stackframe where this code is being compiled.
        col_offset : int
            The column offset of the code.

        Returns
        -------
        f : callable
            The C function from user code.
        """
        return self._make_func(code, frame, col_offset, 'expr')

    def cleanup(self, path='.', recurse=True):
        paths = (
            os.path.join(parent, f)
            for parent, _, fs in os.walk(path)
            for f in fs
        ) if recurse else (
            os.path.join(path, f) for f in os.listdir(path)
        )
        pattern = re.compile(r'.*_qq_.+_\d+_\d+_.+\.(c|so)$')
        removed = []
        for p in paths:
            if pattern.match(p):
                removed.append(p)
                os.remove(p)

        return removed


try:
    __IPYTHON__
except NameError:
    pass
else:
    import sys

    from IPython.core.magic import register_line_cell_magic

    _c = c  # hold a reference to the quasiquoter

    @register_line_cell_magic
    def c(line, cell=None, *, sys=sys, qq=c(keep_c=False, keep_so=False)):
        ns = get_ipython().user_ns  # noqa
        frame = sys._getframe()
        if cell is None:
            lineno = frame.f_lineno + 1
            ret = qq._resolve_expr(line, frame, 0)(ns)
            cache = qq._expr_cache
        else:
            ret = None
            cache = qq._stmt_cache
            lineno = frame.f_lineno + 1
            qq._resolve_stmt(cell, frame, 0)(ns)

        del cache[frame.f_code, lineno, 0]
        return ret

    del register_line_cell_magic
    del sys

    c = _c  # reassign the quasiquoter to the name 'c'


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--path',
        default='.',
        help='The path to run c.cleanup on',
    )
    parser.add_argument(
        '--no-recurse',
        action='store_false',
        dest='recurse',
        default=True,
        help='Should cleanup recurse down from PATH?',
    )
    for removed in c.cleanup(**vars(parser.parse_args())):
        print(removed)
