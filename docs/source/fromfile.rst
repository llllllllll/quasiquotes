fromfile
--------

:class:`quasiquotes.fromfile` is designed to take an existing quasiquoter and
return a new quasiquoter that reads its input from a file. For example, let's
write an "identity" quasiquoter that executes the body as python code.

.. code-block:: python

   from textwrap import dedent

   from quasiquotes import QuasiQuoter
   from quasiquotes.utils.instance import instance

   @instance
   class py(QuasiQuoter):
       def quote_stmt(self, code, frame, col_offset):
           exec(dedent(code), frame.f_globals, frame.f_locals)
           self.locals_to_fast(frame)

       def quote_expr(self, code, frame, col_offset):
           return eval(code, frame.f_globals, frame.f_locals)


We can use this silly quasiquoter as expected:

.. code-block:: python

   >>> a = 2
   >>> with $py:
   ...     print(a + 2)
   4
   >>> print([$py|a + 2|])
   4

We can now use this to inline python from another file in our function. For
example, let's imagine that ``other_file.py`` looks like:

.. code-block:: python

   print(a + 2)


We can then use this in our files like:

.. code-block:: python

   >>> inlinepy = fromfile(py)  # remember, we need to bind this before use.
   >>> a = 2
   >>> with $inlinepy:
   ...     other_file.py
   4
   >>> [$inlinepy|other_file.py|] is None
   4
   True
