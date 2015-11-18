from contextlib import contextmanager
import sys


@contextmanager
def tmp_path(path):
    """Temporarily add ``path`` to sys.path.

    Parameters
    ----------
    path : str
        The filepath to add to ``sys.path``.

    Notes
    -----
    Prepends this new filepath to the existing path. This will cause this
    filepath to be searched before all other paths.
    """
    sys.path.insert(0, path)
    try:
        yield
    finally:
        sys.path = sys.path[1:]
