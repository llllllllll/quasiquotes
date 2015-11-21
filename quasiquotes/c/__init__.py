from distutils.sysconfig import get_python_inc
from hashlib import md5
import operator as op
import os
import re
from sysconfig import get_config_var
from textwrap import dedent
from warnings import warn


from ._loader import create_callable
from ..quasiquoter import QuasiQuoter
from ..utils.instance import instance
from ..utils.shell import Executable, Flag


gcc = Executable('gcc')


class CompilationError(Exception):
    """An exception that indicates that gcc failed to compile the given C code.
    """
    def __str__(self):
        return '\n' + self.args[0]


class CompilationWarning(UserWarning):
    """A warningthat indicates that gcc warned when compiling the given C code.
    """
    def __str__(self):
        return '\n' + self.args[0]


@instance
class c(QuasiQuoter):
    """quasiquoter for inlining c.

    Parameters
    ----------
    keep_c : bool, optional
        Keep the generated .c files. Defaults to False.
    keep_so : bool, optional
        Keep the compiled .so files. Defaults to True.
    extra_compile_args : iterable[str or Flag]
        Extra command line arguments to pass to gcc.

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
    def __init__(self, *, keep_c=False, keep_so=True, extra_compile_args=()):
        self._keep_c = keep_c
        self._keep_so = keep_so
        self._extra_compile_args = tuple(extra_compile_args)
        self._stmt_cache = {}
        self._expr_cache = {}

    def __call__(self, **kwargs):
        return type(self)(**kwargs)

    _basename_template = '_qq_{type}_{base}_{md5}.%s' % get_config_var('SOABI')
    _missing_name_pattern = re.compile(
        r'^.+: error: ‘(.+)’ undeclared'
        r' \(first use in this function\)$',
        re.MULTILINE,
    )
    _error_pattern = re.compile('^.+:\d+: error.*', re.MULTILINE)

    _read_scope_template = dedent(
        """\
            if (!({name} = PyDict_GetItemString(__qq_locals, "{name}"))) {{
                if (!({name} = PyDict_GetItemString(__qq_globals,
                                                    "{name}"))) {{
                    PyErr_SetString(PyExc_NameError,
                                    "name '{name}' is not defined");
                }}
            }}
        """,
    )

    _shared = dedent(
        """\
        #include <Python.h>

        static PyObject *
        __qq_f(PyObject *__qq_self, PyObject *__qq_args)
        {{
            PyObject *__qq_globals;
            PyObject *__qq_locals;
        {localdecls}

            if (PyTuple_GET_SIZE(__qq_args) != 2) {{
                PyErr_SetString(PyExc_TypeError,
                                "quoted func needs 2 args (globals, locals)");
                return NULL;
            }}
            __qq_globals = PyTuple_GET_ITEM(__qq_args, 0);
            __qq_locals = PyTuple_GET_ITEM(__qq_args, 1);

        {read_scope}
        """,
    )

    _stmt_template = _shared + dedent(
        """\

            /* BEGIN USER BLOCK */
            #line {lineno} "{filename}"
            {{
        {code}
            }}
            /* END USER BLOCK */

        {localassign}

            Py_INCREF(__qq_locals);
            return __qq_locals;
        }}

        PyMethodDef __qq_methoddef = {{
            "quoted_stmt", (PyCFunction) __qq_f, METH_VARARGS, "",
        }};
        """,
    )

    _expr_template = _shared + dedent(
        """\

            /* BEGIN USER BLOCK */
            return ({{
            #line {lineno} "{filename}"
        {code}
            /* END USER BLOCK */
            ;}});
        }}

        PyMethodDef __qq_methoddef = {{
            "quoted_expr", (PyCFunction) __qq_f, METH_VARARGS, "",
        }};
        """
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
        locals_ = frame.f_locals
        self._resolve_stmt(code, frame, col_offset)(
            frame.f_globals,
            locals_,
        )
        self.locals_to_fast(frame)

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
            frame.f_globals,
            frame.f_locals,
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

    def _resolve(self, code, frame, col_offset, cache, kind):
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
        kind : {'expr', 'stmt'}
            The type of quasiquote being invoked.

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

        f_code = frame.f_code
        try:
            f = cache[entry] = create_callable(
                self._soname(code, f_code, kind),
            )
            return f
        except OSError:
            pass

        try:
            f = cache[entry] = self._compile(code, f_code, kind)
            return f
        except FileNotFoundError:
            pass

        f = cache[entry] = self._make_func(code, frame, col_offset, kind)
        return f

    def _dir_and_basename(self, code, f_code, kind):
        filename = f_code.co_filename
        return (
            os.path.abspath(os.path.dirname(filename)),
            self._basename_template.format(
                type=kind,
                base=os.path.basename(filename).split('.', 1)[0],
                md5=md5(code.encode('utf-8')).hexdigest(),
            ),
        )

    def _soname(self, code, f_code, kind):
        return os.path.join(
            *self._dir_and_basename(code, f_code, kind)
        ) + '.so'

    def _cname(self, code, f_code, kind):
        return os.path.join(
            *self._dir_and_basename(code, f_code, kind)
        ) + '.c'

    def _resolve_stmt(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._stmt_cache, 'stmt',
        )

    def _resolve_expr(self, code, frame, col_offset):
        return self._resolve(
            code, frame, col_offset, self._expr_cache, 'expr',
        )

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
                        '    {0} && PyDict_SetItemString(__qq_locals,'
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

        cname = self._cname(code, frame.f_code, kind)
        with open(cname, 'w+') as f:
            f.write(template.format(
                fmt='"{}"'.format('O' * len(names)),
                keywords=(
                    '{' + ', '.join(map('"{}"'.format, names)) + ', NULL}'
                ),
                kwargs=', '.join(map('&{}'.format, names)),
                localdecls='\n'.join(
                    map('    PyObject *{} = NULL;'.format, names),
                ),
                read_scope='\n'.join(
                    self._read_scope_template.format(name=name)
                    for name in names,
                ),
                lineno=frame.f_lineno,
                filename=frame.f_code.co_filename,
                code=code,
                **extra_template_args
            ))
            f.flush()

        try:
            return self._compile(code, frame.f_code, kind)
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

    def _compile(self, code, f_code, kind):
        cname = self._cname(code, f_code, kind)
        soname = self._soname(code, f_code, kind)
        os.stat(cname)  # raises FileNotFoundError if doesn't exist
        _, err, status = gcc(
            Flag.O(3),
            Flag.I(get_python_inc()),
            Flag.f('PIC'),
            Flag.std('gnu11'),
            Flag.shared,
            Flag.o(soname),
            *(cname,) + self._extra_compile_args
        )
        if not self._keep_c:
            os.remove(cname)
        if err:
            if self._error_pattern.findall(err):
                raise CompilationError(err)
            else:
                warn(CompilationWarning(err))

        f = create_callable(soname)

        if not self._keep_so:
            os.remove(soname)
        return f

    def cleanup(self, path='.', recurse=True):
        """Remove cached shared objects and c code generated by the
        c quasiquoter.

        Parameters
        ----------
        path : str, optional
            The path to the directory that will be searched.
        recurse : bool, optional
            Should the search recurse through subdirectories of ``path``.

        Returns
        -------
        removed : list[str]
            The paths to the files that were removed.
        """
        paths = (
            os.path.join(parent, f)
            for parent, _, fs in os.walk(path)
            for f in fs
        ) if recurse else (
            os.path.join(path, f) for f in os.listdir(path)
        )
        pattern = re.compile(r'.*_qq_.+.+\.(c|so)$')
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
