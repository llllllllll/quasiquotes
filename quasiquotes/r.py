from contextlib import contextmanager
from itertools import chain


import rpy2.robjects as ro
from rpy2.ipython.rmagic import converter, pyconverter

from ..quasiquoter import QuasiQuoter
from ..utils.instance import instance


@instance
class r(QuasiQuoter):
    """quasiquoter for inlining r.

    Parameters
    ----------
    pytor : callable, optional
        The converter to use to convert PyObjects to r objects.
    rtopy : callable, optional
        The converter to use when converting r objects into PyObjects.

    Methods
    -------
    quote_stmt
    quote_expr

    Notes
    -----
    You cannot pass arguments in the quasiquote syntax. You must construct
    a new instance of `r` and then use that as the quasiquoter. For example:

    ::

       with $r(converter=my_converter):
           print(c(1, 2, 3))

    is a syntax error. Instead, you must do:

    ::

       r_custom_converter = r(converter=my_converter)
       with $r_custom_converter:
           print(c(1, 2, 3))

    This is because of the way the quasiquotes lexer identifies quasiquote
    sections.
    """
    def __init__(self, *, pytor=pyconverter, rtopy=converter.ri2py):
        self._pytor = pyconverter
        self._rtopy = rtopy

    def __call__(self, *args, **kwargs):
        return type(self)(*args, **kwargs)

    @contextmanager
    def _tmprns(self, globals_, locals_, collect_updates):
        pytor = self._pytor
        items = dict(chain(globals_.items(), locals_.items())).items()
        wrote = []
        original_ns = {}
        for d in (locals_, globals_):
            is_locals = d is locals_
            for name, value in items:
                if name in wrote:
                    continue
                try:
                    original_ns[name] = rval = pytor(value)
                    ro.r.assign(name, rval)
                    ro.r.assign('._qq_orig_' + name, rval)
                    if is_locals:
                        wrote.append(name)
                except NotImplementedError:
                    pass

        updated_values = {}
        try:
            yield updated_values
        finally:
            rtopy = self._rtopy
            if collect_updates:
                updated_pred = rtopy(ro.r(('c(%s)' % (
                    ', '.join(map(
                        'identical(get({0!r}), ._qq_orig_{0})'.format,
                        wrote
                    )),
                ))))
                updated_values.update({
                    name: rtopy(ro.r('get(%r)' % name))
                    for name, pred in zip(wrote, updated_pred)
                    if not pred
                })
        ro.r('rm(list=ls())')

    def quote_expr(self, code, frame, col_offset):
        with self._tmprns(frame.f_globals, frame.f_locals, False):
            return self._rtopy(ro.r(code))

    def quote_stmt(self, code, frame, col_offset):
        with self._tmprns(frame.f_globals, frame.f_locals, True) as updates:
            self._rtopy(ro.r(code))
        frame.f_locals.update(updates)
        self.locals_to_fast(frame)
