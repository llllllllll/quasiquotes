Implementation
--------------

Tokens
~~~~~~

quasiquotes works by hooking into the file encoding logic. Every file is marked
with an encoding type, defaulting to utf-8. This is shown with the ``# coding:
<encoding>`` coments at the top of some files. This encoding defines the
functions needed to convert the raw bytes that come in from the filesystem into
python ``str`` objects. Users are also able to register their own encoding types
by providing their own conversion functions. quasiquotes sits on top of the
utf-8 encoding functions; however, it tokenizes the files coming in so that it
can rewrite certian patterns.


Let's look at some source code and the tokens that come out of it:

.. code-block:: python

   with $qq:
       this should not parse
       but it will

::

   NAME('with')
   ERROR(' ')
   ERROR('$')
   NAME('qq')
   OP(':')
   NEWLINE('\n')
   <body>
   DEDENT


This says we have the string 'with' followed by 2 errors. These tokens appear as
``ERROR`` because this would normally be an invalid token in python. The next
part is the actual name of the quasiquoter you would want to use. Finally we
have the colon and newline. The body is whatever sequence of tokens make up the
indented region in the quasiquoter, and then we have the ``DEDENT`` token
marking the end of the body.


By manipulating the tokens, we can change this into something that looks like:


.. code-block:: python

   cc._quote_stmt(0,'    this should not parse\n    but it will')


Here the ``0`` is the column offset of this quoted expression, and the string is
the body of the context manager. The lack of space after the comma accuratly
reflects the column offsets of the tokens that the quasiquotes tokenizer emits.

.. note::

   The original indentation is preserved.


We can do this because we still have access to the raw text that makes up each
line between the ``NEWLINE`` and the ``DEDENT``.

Let's also look at the quoted expressions:

.. code-block:: python

   [$qq|this is also invalid|]


::

   OP('[']
   ERROR('$')
   NAME('qq')
   OP('|')
   <body>
   OP('|')
   OP(']')


 Just like with quoted statements, we can rewrite this to look more like:


 .. code-block:: python

    qq._quote_expr(0,'    this is also invalid')


.. note::

   Indentation is also preserved in a quoted expression.


Runtime Lookups
~~~~~~~~~~~~~~~

An important thing to notice about the implementation is that it builds source
that has method calls of a dynamic object. While we are doing static work to
make the parser see the quoted block as valid python, we do *not* load the
quasiquoter until the function is being executed and we have a running
frame. This means that the current value for the name of the quasiquoter will be
used.


Expressions as ``QuasiQuoter``\s
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``QuasiQuoter``\s are instances, so one might think that they should be able to
do:

.. code-block:: python

   with $MyQQ(some_arg=some_value):
       ...


Unfortunately, this changes the token stream. We no longer have an ``OP(':'),
NEWLINE('\n')`` following the name of the quoter. Currently, we do not detect
this case and the normal python syntax error will be thrown. This is also true
for quoted expressions.
