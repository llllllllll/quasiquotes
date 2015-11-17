=====================
 ``quasiquotes 0.1``
=====================

Blocks of non-python code sprinkled in for extra seasoning.


What is a ``quasiquote``
========================

An ``quasiquote`` is a new syntactical element that allows us to embed non
python code into our existing python code. The basic structure is as follows:


.. code-block:: python


   # coding: quasiquotes

   [$name|some code goes here|]


This desuagars to:

.. code-block:: python

   name.quote_expr("some code goes here", frame, col_offset)

where ``frame`` is the executing stack frame and ``col_offset`` is the column
offset of the quasiquoter.

This allows us to use slightly nicer syntax for our code.
The ``# coding: quasiquotes`` is needed to enable this extension.
The syntax is chosen to match haskell's quasiquote syntax from GHC 6.12. We need
to use the older syntax (with the ``$``) because python's grammar would be
ambiguous without it at the quote open step. To simplify the tokenizer, we chose
to use slighly more verbose syntax.

We may also use statement syntax for quasiquotes in a modified with block:

.. code-block:: python

   # coding: quasiquotes

   with $name:
       some code goes here

This desuagars to:

.. code-block:: python

   name.quote_stmt("    some code goes here", frame, col_offset)



The ``c`` quasiquoter
=====================

The builtin ``c`` quasiquoter allows us to inline C code into our python.
For example:

.. code-block:: python

   >>> from quasiquotes.c import c
   >>> def f(a):
   ...     with $c:
   ...         printf("%ld\n", PyLong_AsLong(a));
   ...         a = Py_None;
   ...         Py_INCREF(a);
   ...     print(a)
   ...
   >>> f(0)
   0
   None
   >>> f(1)
   1
   None


Here we can see that the quasiquoter can read from and write to the local
scope.


We can also use mutli-statement expressions:

.. code-block:: python

   >>> def cell_new(n):
   ...     return [$c|PyCell_New(n);]
   ...
   >>> cell_new(1)
   <cell at 0x7f8dde6cd5e8: int object at 0x7f8ddf956780>


Here we can see that the ``c`` quasiquoter is really convenient as a python
interface into the C API.


IPython Integration
-------------------

We can use the ``c`` quasiquoter in the IPython repl or notebook as a cell or
line magic. When used as a line magic, it is quoted as an expression. When used
as a cell magic, it is quoted as a statement.


.. code-block:: python

   In [1]: import quasiquotes.c

   In [2]: a = 5

   In [3]: %c PyObject *b = PyLong_FromLong(3); PyObject *ret = PyNumber_Add(a, b); Py_DECRE   F(b); ret;
   Out[3]: 8

   In [4]: %%c
      ...: printf("%ld + %ld = %ld\n", 3, PyLong_AsLong(a), PyLong_AsLong(_3));
      ...: puts("reassigning 'a'");
      ...: a = Py_None;
      ...: Py_INCREF(a);
      ...:
   3 + 5 = 8
   reassigning 'a'

   In [6]: a is None
   Out[6]: True
