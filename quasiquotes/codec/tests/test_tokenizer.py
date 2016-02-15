import pytest

from quasiquotes.codec.tokenizer import (
    PeekableIterator,
)


@pytest.fixture
def piter():
    return PeekableIterator(iter(range(10)))


def test_peekable_iter_strict(piter):
    assert list(piter) == list(range(10))


def test_peekable_iter_strict_after_peek(piter):
    assert piter.peek(3) == (0, 1, 2)
    assert list(piter) == list(range(10))


def test_peek_more_than_length(piter):
    assert piter.peek(20) == tuple(range(10))


def test_lookahead_iter(piter):
    for n in piter.lookahead_iter():
        if n == 3:
            break

    assert list(piter) == list(range(3, 10))


def test_consume_peeked_all(piter):
    assert piter.peek(5) == (0, 1, 2, 3, 4)
    piter.consume_peeked()
    assert list(piter) == [5, 6, 7, 8, 9]


def test_consume_peeked_n(piter):
    assert piter.peek(5) == (0, 1, 2, 3, 4)
    piter.consume_peeked(3)
    assert list(piter) == list(range(3, 10))
