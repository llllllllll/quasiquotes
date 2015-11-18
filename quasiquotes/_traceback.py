# coding: quasiquotes


from .c import c


def new_tb(frame):
    """Create a traceback object starting at the given stackframe.

    Parameters
    ----------
    frame : frame
        The frame to start the traceback from.

    Returns
    -------
    tb : traceback
        The new traceback object.
    """
    return [$c|
        #include "frameobject.h"
        PyFrameObject *frame_ = (PyFrameObject*) frame;  /* cast input frame */
        PyTracebackObject *tb;

        if (!PyFrame_Check(frame_)) {
            PyErr_BadInternalCall();
            return NULL;
        }
        tb = PyObject_GC_New(PyTracebackObject, &PyTraceBack_Type);
        if (tb != NULL) {
            tb->tb_next = NULL;
            Py_XINCREF(frame_);
            #pragma GCC diagnostic ignored "-Wincompatible-pointer-types"
            tb->tb_frame = frame_;
            tb->tb_lasti = frame_->f_lasti;
            tb->tb_lineno = PyFrame_GetLineNumber(frame_);
            PyObject_GC_Track(tb);
        }
        (PyObject*) tb;
    |]
