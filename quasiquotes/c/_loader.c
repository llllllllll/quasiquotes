#include <Python.h>
#include <dlfcn.h>

static PyObject *
create_callable(PyObject *self, PyObject *args, PyObject *kwargs)
{
    char* keywords[] = {"filename", NULL};
    char *filename;
    void *sohandle;
    PyMethodDef *qq_methoddef;

    if (!(PyArg_ParseTupleAndKeywords(args,
                                      kwargs,
                                      "s:create_callable",
                                      keywords,
                                      &filename))) {
        return NULL;
    }

    if (!(sohandle = dlopen(filename, RTLD_LAZY))) {
        PyErr_SetString(PyExc_OSError, dlerror());
        return NULL;
    }
    if (!(qq_methoddef = dlsym(sohandle, "__qq_methoddef"))) {
        PyErr_SetString(PyExc_OSError, dlerror());
        return NULL;
    }
    return PyCFunction_NewEx(qq_methoddef, NULL, NULL);
}

static PyMethodDef methods[] = {
    {"create_callable",
     (PyCFunction) create_callable,
     METH_VARARGS | METH_KEYWORDS,
     ""},
    {NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "quasiquotes.c._loader",
    "",
    -1,
    methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__loader(void)
{
    return PyModule_Create(&module);
}
