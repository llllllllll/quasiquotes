from subprocess import Popen, PIPE, DEVNULL


class FlagMeta(type):
    def __getattr__(self, name):
        return Flag(name)


class Flag(metaclass=FlagMeta):
    def __init__(self, name):
        self._name = name
        self._arg = None

    def __str__(self):
        if self._arg is not None:
            fmtstr = (
                '-{name}{arg}' if len(self._name) == 1 else '-{name}={arg}'
            )
            return fmtstr.format(name=self._name, arg=self._arg)
        else:
            return '-{name}'.format(name=self._name)

    def __repr__(self):
        return '{cls}({name})'.format(cls=type(self).__name__, name=self._name)

    def __call__(self, arg):
        self._arg = arg
        return self


class Executable(object):
    """
    An executable from the shell.
    """
    def __init__(self, name):
        self._name = name

    def __call__(self, *args, **kwargs):
        stdin = kwargs.pop('stdin', None)
        if kwargs:
            raise TypeError(
                'unexpected keyword arguments: %s' % kwargs.keys(),
            )

        proc = Popen(
            '%s %s' % (self._name, ' '.join(map(str, args))),
            shell=True,
            stdin=PIPE if stdin else DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
        )
        out, err = proc.communicate(stdin)
        return out.decode('utf-8'), err.decode('utf-8'), proc.returncode
