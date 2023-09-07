import io
from pathlib import Path
from typing import Literal

from utilz.debug.file_info import DocumentInfo


class SourceFile:
    _info: DocumentInfo
    _content_stream: io.TextIOBase | io.RawIOBase

    def __init__(self, info: DocumentInfo, source: io.TextIOBase | io.RawIOBase):
        super().__init__()
        self._info = info
        self._content_stream = source

    @property
    def info(self):
        return self._info

    @property
    def content_stream(self):
        return self._content_stream

    @classmethod
    def from_info(cls, info: DocumentInfo, mode: Literal['t'] | Literal['b'] = 't'):
        return cls.from_path(info.path_string, mode)

    @classmethod
    def from_path(cls, path: str | Path | DocumentInfo, mode: Literal['t'] | Literal['b'] = 't'):
        path = DocumentInfo.from_path(path)
        with open(path.path_string, mode + 'r') as source:
            return cls(path, (io.StringIO if mode == 't' else io.BytesIO)(source.read()))

    def __str__(self):
        return f"SourceFile @ {self._info.path}"
