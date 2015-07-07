from io import BytesIO
from itertools import islice
from textwrap import dedent
from token import NAME, OP, STRING, NEWLINE, INDENT, DEDENT
from tokenize import tokenize as default_tokenize, TokenInfo, untokenize, NL
from queue import Queue, Empty


class FuzzyTokenInfo(TokenInfo):
    def __new__(cls, type, string, start=None, end=None, line=None):
        return super().__new__(cls, type, string, start, end, line)

    def __eq__(self, other):
        return self.type == other.type and self.string == other.string
    __req__ = __eq__

    def __ne__(self, other):
        return not self == other
    __rne__ = __ne__


with_tok = FuzzyTokenInfo(NAME, 'with')
at_tok = FuzzyTokenInfo(OP, '@')
col_tok = FuzzyTokenInfo(OP, ':')
nl_tok = FuzzyTokenInfo(NEWLINE, '\n')


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


def tokenize(readline):
    tok_stream = PeekableIterator(default_tokenize(readline))
    for t in tok_stream:
        if t != with_tok:
            yield t
            continue

        try:
            at, name, col, nl, indent = tok_stream.peek(5)
        except ValueError:
            continue

        if (at != at_tok or col != col_tok or
                nl != nl_tok or indent.type != INDENT):
            continue
        # pull the items out of the stream.
        tuple(islice(tok_stream, None, 5))

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

        end = t.end[0], t.start[1] + len(name.string)
        yield name._replace(start=t.start, end=end, line='<line>')
        open_end = end[0], end[1] + 1
        yield TokenInfo(
            type=OP,
            string='(',
            start=end,
            end=open_end,
            line='<line>',
        )
        if len(ls) == 1:
            str_end = open_end[0], open_end[1] + len(ls[-1]) + 2
        else:
            str_end = open_end[0] + len(ls) - 1, len(ls[-1]) + 2
        yield TokenInfo(
            type=STRING,
            string=repr(dedent(''.join(ls))),
            start=open_end,
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


def tokenize_bytes(bs):
    return tokenize(BytesIO(bs).readline)


def tokenize_string(cs):
    return tokenize_bytes(cs.encode('utf-8'))


def transform_bytes(bs):
    return untokenize(tokenize_bytes(bs))


def transform_string(cs):
    return untokenize(tokenize_string(cs)).decode('utf-8')
