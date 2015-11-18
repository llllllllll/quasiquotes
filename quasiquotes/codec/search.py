from codecs import CodecInfo
from encodings import utf_8
from io import StringIO

from .tokenizer import transform_string

utf8 = utf_8.getregentry()


def decode(input, errors='strict'):
    cs, errors = utf_8.decode(input, errors)
    return transform_string(cs), errors


class IncrementalDecoder(utf_8.IncrementalDecoder):
    def decode(self, input, final=False):
        return transform_string(super().decode(input, final))


class StreamReader(utf_8.StreamReader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream = StringIO(transform_string(self.stream.getvalue()))


def search_function(encoding):
    if encoding != 'quasiquotes':
        return None

    return CodecInfo(
        name='quasiquotes',
        encode=utf8.encode,
        decode=decode,
        incrementalencoder=utf8.incrementalencoder,
        incrementaldecoder=IncrementalDecoder,
        streamreader=StreamReader,
        streamwriter=utf8.streamwriter,
    )
