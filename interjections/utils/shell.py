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


class Exectuable(object):
    """
    An exectuble from the shell.
    """
    def __init__(self, name):
        self._name = name

    def __call__(self, *args, **kwargs):
        stdin = kwargs.get('stdin')

        prefix = ("echo %s | " % stdin) if stdin else ""
        command = '%s%s %s' % (prefix, self._name, ' '.join(map(str, args)))
        proc = Popen(
            command,
            shell=True,
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
        )
        proc.wait()

        return (
            proc.stdout.read().decode('utf-8'),
            proc.stderr.read().decode('utf-8'),
            proc.returncode,
        )
