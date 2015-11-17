from codecs import CodecInfo
from encodings import utf_8
from io import StringIO

from .tokenizer import transform_bytes, transform_string

utf8 = utf_8.getregentry()


def decode(input, errors='strict'):
    if isinstance(input, memoryview):
        input = input.tobytes().decode('utf-8')
    if isinstance(input, str):
        input = input.encode('utf-8')
    return utf8.decode(transform_bytes(input), errors)


class IncrementalDecoder(utf_8.IncrementalDecoder):
    def decode(self, input, final=False):
        return super().decode(transform_bytes(input), final)


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
