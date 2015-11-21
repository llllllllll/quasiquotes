Inline c
--------

The most fully featured quasiquoter and the the reason that this project
exists is the :data:`~quasiquotes.c.c` quasiquoter. The c quasiquoter is designed to be a way to
seamlessly use the CPython API while preserving code locality and avoiding
boilerplate.

When optimizing python, we often find that very few functions are hotspots that
require us to rewrite in c. Good practice says to start in python and then
slowly port the slow functions into c one at a time. We don't just want to
rewrite all of it because then we lose the maintainability of python for a
trivial gain. The c quasiquoter gives us even more fine control over which parts
of our program can be in c by allowing us to weave sections of c into our python
functions. We can even do things like rewrite a single loop in a function
in c.

One of the main benifits of this approach is that we can keep the optimized c
code right next to the python that it is supporting. This is a huge benifit for
maintainability.

Namespace Management
~~~~~~~~~~~~~~~~~~~~

The c quasiquoter allows us to manipulate the python namespace of the enclosing
scope. For example:

.. code-block:: python

   >>> a = 1
   >>> b = 'test'
   >>> with $c:
   ...     printf("%ld\n%s\n",
   ...            PyLong_AsLong(a),
   ...            PyUnicode_AsUTF8(b));
   1
   test

Here we can see that the variables from the enclosing scope have been passed
into our function. All python values will have the standard type of
``PyObject*`` and can be used like normal.

We can also change the namespace just like a normal context manager.

.. code-block:: python

   >>> a = 1
   ... with $c:
   ...     printf("%ld\n", PyLong_AsLong(a));
   ...     a = Py_None;
   ...     Py_INCREF(a);
   1
   >>> a is None
   True

Here we can see that the enhanced with block can reassign the names in
scope. This even works for the locals of a function.


Quoted Expressions
~~~~~~~~~~~~~~~~~~

The c quasiquoter also allows for quoted expressions. Just like the enhanced
with statment, the quoted expression can use the names from the enclosing scope.
For example:

.. code-block:: python

   >>> [$c|PyLong_FromLong(2)|] + 2
   4
   >>> a = 2
   >>> [$c|PyLong_FromLong(PyLong_AsLong(a) + 2)|]
   4

Quoted expressions are built on compound statements, a gnu extension to c. These
look like:

.. code-block:: c

   int a = ({
       int b = 1;  /* This is a new block, new declarations are allowed
       int c = 2;
       b + c;  /* The final expression is the result of the block.
   });

We need this because most quoted expressions that will return to python need to
remember to incref the return. For example:


.. code-block:: python

   >>> [$c|Py_INCREF(Py_None); Py_None|] is None
   True

We need to remember to call ``Py_INCREF`` or we will get a segfault somewhere in
the garbage collector at interpreter shutdown.

.. note::

   The last semicolon is optional in c quoted expression.


Type Conversion
~~~~~~~~~~~~~~~

Because one intended use case of the c quasiquoter is optimization, there is no
implicit object conversion. All names passed from the outside scope will have
type ``PyObject*``. This matches the normal CPython API conventions. There are
many type specific conversion functions, for example: ``PyLong_AsLong`` or
``PyUnicode_AsUTF8``.

This is also true for the quoted expression return value. a
:class:`quasiquotes.c.CompilationError` will be raised if the final expression
does not have type ``PyObject*``.


Reference Counting
~~~~~~~~~~~~~~~~~~

CPython uses a reference counting garbage collection strategy. This means that
every ``PyObject`` has an ``ob_refcnt`` field (of type ``Py_ssize_t``. This
measures the number of objects that can refer to this object. Whenever an object
is added to some container, the container will ``Py_INCREF`` the object,
increasing the reference count by 1. When the object is removed from the
container the container will ``Py_DECREF`` the object, reducing the reference
count by 1. When an object with exactly 1 reference is ``Py_DECREF``\ed it will
be destroyed immediatly by calling
``((PyTypeObject*) Py_TYPE(ob))->tp_dealloc(ob)``. This will deallocate the
object.

CPython documentation will also refer to the concept of borrowed references. A
borrowed reference is a reference to an object that the current scope does not
own. This means that the current scope is not responsible for calling
``Py_DECREF`` on this object. For example, when arguments are passed to a
function, they are passed as a borrowed reference, if one wishes to hold onto
the object, they must ``Py_INCREF`` it to take ownership. Some CPython API
functions will return borrowed references.

Similar to the idea of borrowed reference is the idea of stealing
references. This means that a function will not ``Py_INCREF`` the object but it
will ``Py_DECREF`` it when it releases ownership. It is the job of the caller to
ensure that they want to release ownership to the function.

quasiquotes does not help the programmer with reference counting. It is still
the user's responsibility to manage the lifetimes on their objects.


Exceptions
~~~~~~~~~~

When a function or quoted block raises an exception, the user should call
``PyErr_SetString``, ``PyErr_Format``, or one of the other functions used for
setting the exception state. These will mark that a failure has occurred so that
the interpreter knows which type of failure happened. This is very similar to
the ``raise`` keyword in python.

When an exception has been set, the function should return ``NULL`` to show that
an exception as occured. After calling most CPython API functions, the user
should verify that the return is not ``NULL``. Often the user should bubble the
return of ``NULL`` up, making sure to ``Py_DECREF`` all of the values they had
temporary ownership of.

Compilation Caching
~~~~~~~~~~~~~~~~~~~

Whenever a quoted statement or expression is compiled, it will create a shared
object next to the python source of the file. The name of the shared object will
start with ``_qq_<kind>`` where kind can be either ``stmt`` or ``expr``. This
marks the type of quasiquote that was used. Then it will have the name of the
module it is in. After that is an md5 hash of the body of the quoted
section. Finally, there is the ABI compat string, like ``cpython-34m`` that says
that this was CPython major version 3 minor version 4 compiled with PyMalloc
enabled.

The quasiquoter can also be configured to cache the generated c source code or
to not cache the shared objects with the ``keep_c`` and ``keep_so`` keyword
arguments to the ``c`` quasiquoter.

Every compiled chunk will be cached in memory after the quasiquote has been
executed once.

Every so often you will want to cleanup stale compiled shared objects. This can
be done with the :meth:`~quasiquotes.c.c.cleanup` method, or by executing:
``python -m quasiquotes.c`` Both of these accept two arguments: ``path`` and
``recurse`` defaulting to ``.`` and ``True`` respectivly. This marks where the
search for cached c and shared objects should begin and if the search should
recurse through subdirectories.

Compilation Options
~~~~~~~~~~~~~~~~~~~

The c quasiquoter accepts a keyword argument: ``extra_compile_args`` which
should be a sequence of string to pass to ``gcc``. This can be used to add
include directories or link against other libraries.
