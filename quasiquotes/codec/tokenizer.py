from io import BytesIO
from itertools import islice, chain, repeat
from token import (
    ERRORTOKEN,
    INDENT,
    DEDENT,
    NAME,
    NEWLINE,
    NUMBER,
    OP,
    STRING,
)
from tokenize import (
    ENCODING,
    NL,
    TokenInfo,
    _tokenize,
    untokenize,
)
from queue import Queue, Empty


class FuzzyTokenInfo(TokenInfo):
    """A token info object that check equality only on ``type`` and ``string``.

    Parameters
    ----------
    type : int
        The enum for the token type.
    string : str
        The string represnting the token.
    start, end, line : any
        Ignored.
    """
    def __new__(cls, type, string, start=None, end=None, line=None):
        return super().__new__(cls, type, string, start, end, line)

    def __eq__(self, other):
        return self.type == other.type and self.string == other.string
    __req__ = __eq__

    def __ne__(self, other):
        return not self == other
    __rne__ = __ne__


with_tok = FuzzyTokenInfo(NAME, 'with')
dollar_tok = FuzzyTokenInfo(ERRORTOKEN, '$')
spaceerror_tok = FuzzyTokenInfo(ERRORTOKEN, ' ')
col_tok = FuzzyTokenInfo(OP, ':')
nl_tok = FuzzyTokenInfo(NEWLINE, '\n')
left_bracket_tok = FuzzyTokenInfo(OP, '[')
pipe_tok = FuzzyTokenInfo(OP, '|')
right_bracket_tok = FuzzyTokenInfo(OP, ']')
encoding_tok = FuzzyTokenInfo(ENCODING, string='quasiquotes')


class PeekableIterator(object):
    def __init__(self, stream):
        self._stream = iter(stream)
        self._peeked = Queue()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self._peeked.get_nowait()
        except Empty:
            return next(self._stream)

    def peek(self, n=1):
        peeked = tuple(islice(self, None, n))
        put = self._peeked.put_nowait
        for item in peeked:
            put(item)
        return peeked

    def lookahead_iter(self):
        while True:
            yield from self.peek(1)
            try:
                next(self)
            except StopIteration:
                break


def quote_stmt_tokenizer(name, start, tok_stream):
    """Tokenizer for quote_stmt.

    Parameters
    ----------
    name : str
        The name of the quasiquoter.
    start : TokenInfo
        The starting token.
    tok_stream : iterator of TokenInfo
        The token stream to pull from.

    Yields
    ------
    The tokens needed to generate a quote_stmt.
    """
    ls = []
    append = ls.append
    prev_line = name.start[0]
    stack = 1
    for u in tok_stream.lookahead_iter():
        if u.type == INDENT:
            stack += 1
        elif u.type == DEDENT:
            stack -= 1

        if not stack:
            break

        if u.start[0] > prev_line:
            prev_line = u.start[0]
            append(u.line)

            end = start.end[0], start.end[1] + len(name.string)
    yield name._replace(start=start.start, end=end, line='<line>')
    dot_end = end[0], end[1] + 1
    yield TokenInfo(
        type=OP,
        string='.',
        start=end,
        end=dot_end,
        line='<line>',
    )
    name_end = dot_end[0], dot_end[1] + len('_quote_stmt')
    yield TokenInfo(
        type=OP,
        string='_quote_stmt',
        start=dot_end,
        end=name_end,
        line='<line>',
    )
    open_end = name_end[0], name_end[1] + 1
    yield TokenInfo(
        type=OP,
        string='(',
        start=name_end,
        end=open_end,
        line='<line>',
    )
    offset_end = open_end[0], open_end[1] + len(str(open_end[1]))
    yield TokenInfo(
        type=NUMBER,
        string=str(start.start[1]),
        start=open_end,
        end=offset_end,
        line='<line>',
    )
    comma_end = offset_end[0], offset_end[1] + 1
    yield TokenInfo(
        type=OP,
        string=',',
        start=offset_end,
        end=comma_end,
        line='<line>',
    )
    if len(ls) == 1:
        str_end = comma_end[0], comma_end[1] + len(ls[-1]) + 2
    else:
        str_end = comma_end[0] + len(ls) - 1, len(ls[-1]) + 2
    yield TokenInfo(
        type=STRING,
        string=repr(''.join(ls)),
        start=comma_end,
        end=str_end,
        line='<line>',
    )
    close_end = str_end[0], str_end[1] + 1
    yield TokenInfo(
        type=OP,
        string=')',
        start=str_end,
        end=close_end,
        line='<line>',
    )
    nl_end = close_end[0], close_end[1] + 1
    yield TokenInfo(
        type=NEWLINE,
        string='\n',
        start=close_end,
        end=nl_end,
        line='<line>',
    )
    yield TokenInfo(
        type=NL,
        string='\n',
        start=(nl_end[0] + 1, 0),
        end=(nl_end[0] + 1, 1),
        line='<line>',
    )


def quote_expr_tokenizer(name, start, tok_stream):
    """Tokenizer for quote_expr.

    Parameters
    ----------
    name : str
        The name of the quasiquoter.
    start : TokenInfo
        The starting token.
    tok_stream : iterator of TokenInfo
        The token stream to pull from.

    Yields
    ------
    The tokens needed to generate a quote_expr.
    """
    ls = []
    append = ls.append
    prev_line = name.start[0] - 1
    was_pipe = False
    for u in tok_stream:
        if u == right_bracket_tok and was_pipe:
            break

        if u.start[0] > prev_line:
            prev_line = u.start[0]
            append(u.line)

        if u == pipe_tok:
            was_pipe = True
        else:
            was_pipe = False

    # remove the start and end quotes.
    ls[0] = (
        ' ' * (name.end[1] + 1) +
        ls[0].split('[$' + name.string + '|', 1)[-1]
    )
    ls[-1] = ls[-1].rsplit('|]', 1)[0]
    tok_pos = start.end[0], start.end[1] + len(name.string)
    yield name._replace(start=start.start, end=tok_pos, line='<line>')
    yield TokenInfo(
        type=OP,
        string='.',
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=OP,
        string='_quote_expr',
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=OP,
        string='(',
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=NUMBER,
        string=str(start.start[1]),
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=OP,
        string=',',
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=STRING,
        string=repr(''.join(ls)),
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )
    yield TokenInfo(
        type=OP,
        string=')',
        start=tok_pos,
        end=tok_pos,
        line='<line>',
    )


def tokenize(readline):
    """Tokenizer for the quasiquotes language extension.

    Parameters
    ----------
    readline : callable
        A callable that returns the next line to tokenize.

    Yields
    ------
    t : TokenInfo
        The token stream.
    """
    # force the token stream to use `utf-8` and ignore the encoding pragma.
    tok_stream = PeekableIterator(_tokenize(
        chain(iter(readline, b''), repeat(b'')).__next__,
        'utf-8',
    ))
    for t in tok_stream:
        if t == with_tok:
            try:
                sp, dol, name, col, nl, indent = tok_stream.peek(6)
            except ValueError:
                continue

            if (sp == spaceerror_tok and
                    dol == dollar_tok and
                    col == col_tok and
                    nl == nl_tok and
                    indent.type == INDENT):
                # pull the items out of the stream.
                tuple(islice(tok_stream, None, 6))
                yield from quote_stmt_tokenizer(name, t, tok_stream)
                continue

        elif t == left_bracket_tok:
            try:
                dol, name, pipe = tok_stream.peek(3)
            except ValueError:
                continue

            if dol == dollar_tok and pipe == pipe_tok:
                tuple(islice(tok_stream, None, 3))
                yield from quote_expr_tokenizer(name, t, tok_stream)
                continue

        yield t


def tokenize_bytes(bs):
    """Tokenize a bytes object.

    Parameters
    ----------
    bs : bytes
        The bytes to tokenize.

    Yields
    ------
    t : TokenInfo
        The token stream.
    """
    return tokenize(BytesIO(bs).readline)


def tokenize_string(cs):
    """Tokenize a str object.

    Parameters
    ----------
    cs : str
        The string to tokenize.

    Yields
    ------
    t : TokenInfo
        The token stream.
    """
    return tokenize_bytes(cs.encode('utf-8'))


def transform_bytes(bs):
    """Run bytes through the tokenizer and emit the pure python representation.

    Parameters
    ----------
    bs : bytes
        The bytes to transform.

    Returns
    -------
    transformed : bytes
        The pure python representation of bs.
    """
    return untokenize(tokenize_bytes(bs))


def transform_string(cs):
    """Run a str through the tokenizer and emit the pure python representation.

    Parameters
    ----------
    cs : str
        The string to transform.

    Returns
    -------
    transformed : bytes
        The pure python representation of cs.
    """
    return untokenize(tokenize_string(cs)).decode('utf-8')
