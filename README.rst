``interjections 0.1``
=====================

Blocks of non-python code sprinkled in for extra seasoning.


What is an ``interjection``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

An ``interjection`` is a new syntactical element that allows us to embed non
python code into our existing python code. The basic structure is as follows:


.. code-block:: python


    # coding: interjections

    with @name:
        some code goes here


This desuagars to:


.. code-block:: python

    name("some code goes here")


This allows us to use slightly nicer syntax for our blocks.
The ``# coding: interjections`` is needed to enable this extension.


The ``@c`` interjection
~~~~~~~~~~~~~~~~~~~~~~~

The builtin ``@c`` interjection allows us to inline C code into our python.
For example:

.. code-block:: python

    >>> def f(a):
    ...     with @c:
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


Here we can see that the interjection can read from and write to the local
scope.
