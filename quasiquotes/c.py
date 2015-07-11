from collections import ChainMap
from ctypes import pythonapi, c_int, py_object
from distutils.sysconfig import get_python_inc
import os
from tempfile import NamedTemporaryFile
from textwrap import dedent


from .quasiquoter import QuasiQuoter
from .utils.instance import instance
from .utils.shell import Executable, Flag
from .utils.path import temp_path


cc = Executable('cc')


class CompilationError(Exception):
    """An exception that indicates that cc failed to compile the given C code.
    """
    def __str__(self):
        return '\n' + self.args[0]


@instance
class c(QuasiQuoter):
    _stmt_cache = {}
    _expr_cache = {}

    _stmt_template = dedent(
        """\
        #include <Python.h>

        static PyObject *
        __f(PyObject *__self, PyObject *__args, PyObject *__kwargs)
        {{
            PyObject *__return;
            char *__keywords[] = {keywords};
        {localdecls}

            if (!PyArg_ParseTupleAndKeywords(
                    __args, __kwargs, {fmt}, __keywords, {kwargs})) {{
                return NULL;
            }}

            /* BEGIN USER BLOCK */
            #line {lineno} "{filename}"
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
        """,
    )

    _expr_template = dedent(
        """\
        #include <Python.h>

        static PyObject *
        __f(PyObject *__self, PyObject *__args, PyObject *__kwargs)
        {{
            char *__keywords[] = {keywords};
        {localdecls}

            if (!PyArg_ParseTupleAndKeywords(
                    __args, __kwargs, {fmt}, __keywords, {kwargs})) {{
                return NULL;
            }}

            /* BEGIN USER BLOCK */
            #line {lineno} "{filename}"
            return ({{
            #line {lineno} "{filename}"
        {code}
            /* END USER BLOCK */
        ;}});
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
        local_keys = locals_.keys()
        locals_.update(
            {
                k: v for k, v in self._resolve_stmt(
                    code, frame, col_offset)(**ns).items() if k in local_keys
            },
        )
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
            **self._ns_from_frame(frame)[0]
        )

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
        entry = frame.f_code, frame.f_lineno, col_offset
        try:
            f = cache[entry]
        except KeyError:
            f = cache[entry] = mkfunc(code, frame, col_offset)

        return f

    def _resolve_stmt(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._stmt_cache, self._make_stmt,
        )

    def _resolve_expr(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._stmt_cache, self._make_expr,
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

    def _make_func(self, code, frame, col_offset, kind):
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

        Returns
        -------
        f : callable
            The C function from user code.
        """
        names = tuple(sorted(
            frame.f_locals.keys() |
            filter(self._notdunder, frame.f_globals.keys()),
        ))
        if kind == 'stmt':
            template = self._stmt_template
            extra_template_args = {
                'localassign': '\n'.join(
                    map(
                        '    {0} && PyDict_SetItemString('
                        '__return, "{0}", {0});'.format,
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

        with NamedTemporaryFile(suffix='.c') as f, \
                NamedTemporaryFile(suffix='.so') as object_file, \
                temp_path(os.path.dirname(f.name)):

            modname = os.path.basename(object_file.name)[:-3]
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
                lineno=frame.f_lineno,
                filename=frame.f_code.co_filename,
                code=code,
                **extra_template_args
            ).encode('utf-8'))
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
                raise CompilationError(err)

            return __import__(modname).f

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
