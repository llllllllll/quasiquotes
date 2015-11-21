Quasiquotes API
---------------

.. module:: quasiquotes.quasiquoter


quasiquotes is designed to make it easy to extend python syntax with arbitrary
parsing logic. To define a new syntax enhancement, create an instance of a
subclass of :class:`~quasiquotes.quasiquoter.QuasiQuoter` that overrides the
``quote_expr`` or ``quote_stmt`` methods.

.. autoclass:: QuasiQuoter
   :members:


``quote_stmt`` has no value. It is used to run normal imperitive code like you
would normally put in the body of a context manager.

``quote_expr`` has a value. It is used to create expressions that can be plugged
into other expressions.

Both ``quote_stmt`` and ``quote_expr`` are passed 3 arguments:

1. String representing the body of either the expression or statement
2. Stackframe where this is being executed
3. Column offset of the quasiquoter


The string will be the pre-built string literal the we constructed at decode
time. The stackframe will be the python stackframe where the quoted statement or
expression is being used. Finally the column offset will be the pre-built
integer constant that represents the offset of the quasiquote token.

Each quasiquoter is free to do whatever it wants with this information,
including mutation of the calling frame's locals, compiling new code, or just
ignoring the body.

A quasiquoter does not need to implement both ``quote_stmt`` and
``quote_expr``. In some cases, it only makes sense to support one of these
features. If a quote type is used syntactically; however, the runtime
quasiquoter does not support this featere then a
:class:`quasiquotes.quasiquoter.QQNotImplementedError` exception will be
raised.
