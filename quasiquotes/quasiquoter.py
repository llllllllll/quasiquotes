from sys import _getframe


class QQNotImplementedError(NotImplementedError):
    def __init__(self, kind):
        if kind not in ('stmt', 'expr'):
            raise ValueError("'kind' must be either 'stmt' or 'expr'")
        self._kind = kind

    def __str__(self):
        if self._kind == 'stmt':
            kind = 'statements'
            syntax = 'with $qq: ...'
        else:
            kind = 'expressions'
            syntax = '[$qq|...|]'

        return 'quasiquoter does not support quoted %s (%s syntax)' % (
            kind,
            syntax,
        )


class QuasiQuoter(object):
    """
    QuasiQuoter base class.
    """
    def _quote_expr(self, col_offset, expr, _getframe=_getframe):
        return self.quote_expr(expr, _getframe(1), col_offset)

    @staticmethod
    def _quote_default(frame, kind):
        # Circular import for bootstrapping reasons.
        from ._traceback import new_tb

        raise QQNotImplementedError(kind).with_traceback(new_tb(frame))

    def quote_expr(self, expr, frame, col_offset):
        """Quote an expression.

        This is called in the oxford brackets case.

        Parameters
        ----------
        expr : str
            The expression to quote.
        frame : frame
            The stack frame where this expression is being executed.
        col_offset : int
            The column offset for the quasiquoter.

        Returns
        -------
        v : any
            The value of the quoted expression
        """
        self._quote_default(frame, 'expr')

    def _quote_stmt(self, col_offset, stmt, _getframe=_getframe):
        self.quote_stmt(stmt, _getframe(1), col_offset)

    def quote_stmt(self, stmt, frame, col_offset):
        """Quote a statment.

        This is called in the enhanced with block case.

        Parameters
        ----------
        stmt : str
            The statement to quote.
            This will have the unaltered indentation.
        frame : frame
            The stack frame where this statement is being executed.
        col_offset : int
            The column offset for the quasiquoter.
        """
        self._quote_default(frame, 'stmt')


class fromfile(QuasiQuoter):
    """Create a new QuasiQuoter from an existing one that reads the body
    from the filename.

    Parameters
    ----------
    qq : QuasiQuoter
        The QuasiQuoter to wrap.

    Examples
    --------
    >>> from quasiquotes.quasiquoter import fromfile
    >>> from quasiquotes.c import c
    >>> include_c = fromfile(c)
    >>> [$include_c|mycode.c|]
    """
    def __init__(self, qq):
        self._qq = qq

    def quote_expr(self, filename, frame, col_offset):
        with open(filename.strip()) as f:
            return self._qq.quote_expr(
                ' ' * col_offset + f.read(), frame, col_offset
            )

    def quote_stmt(self, body, frame, col_offset):
        lines = body.splitlines()
        try:
            filename, = lines
        except ValueError:
            raise SyntaxError(
                'fromfile only accepts a single filename on the first line', (
                    frame.f_code.co_filename,
                    frame.f_lineno,
                    1,
                    lines[1].strip(),
                )
            ) from None

        with open(filename.strip()) as f:
            self._qq.quote_stmt(f.read(), frame, col_offset)
