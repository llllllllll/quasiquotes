from contextlib import contextmanager
import sys


@contextmanager
def temp_path(path):
    sys.path.append(path)
    try:
        yield
    finally:
        sys.path.remove(path)
