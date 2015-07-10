from sys import _getframe


class QQNotImplementedError(NotImplementedError):
    pass


class QuasiQuoter(object):
    """
    QuasiQuoter base class.
    """
    def _quote_expr(self, col_offset, expr):
        return self.quote_expr(expr, _getframe(1), col_offset)

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

        raise QQNotImplementedError('quote_expr')

    def _quote_stmt(self, col_offset, stmt):
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
        raise QQNotImplementedError('quote_stmt')


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
