import io
from pathlib import Path
from typing import Literal


__all__ = [
    "SourceFile",
    "DocumentInfo",
    "Position",
    "Span",
]


class DocumentInfo:
    _path: Path

    def __init__(self, path: str | Path):
        super().__init__()
        if isinstance(path, str):
            path = Path(path)
        self._path = path

    @property
    def path(self):
        return self._path

    @property
    def path_string(self):
        return str(self._path)

    @classmethod
    def from_path(cls, path: "str | Path | DocumentInfo") -> "DocumentInfo":
        if isinstance(path, str):
            path = Path(path)
        if isinstance(path, Path):
            path = DocumentInfo(path.resolve())
        return path

    def __str__(self):
        return f"Document @ {self.path}"


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


class Position:
    _line: int
    _column: int

    def __init__(self, line: int, column: int):
        super().__init__()
        self._line = line
        self._column = column

    @property
    def line(self):
        return self._line

    @property
    def column(self):
        return self._column

    def move_by(self, line: int, column: int):
        self._line += line
        self._column += column

    def move_to(self, line: int, column: int):
        self._line = line
        self._column = column

    def next_line(self):
        self._line += 1
        self._column = 1

    def next_column(self):
        self._column += 1

    def copy(self):
        return Position(self._line, self._column)

    def set(self, position: "Position"):
        self._line = position._line
        self._column = position._column

    def __str__(self):
        return f'{self._line}:{self._column}'

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self._line}, {self._column})'


class Span:
    _start: Position
    _end: Position
    _text: str

    def __init__(self, start: Position, end: Position, text: str):
        super().__init__()
        self._start = start
        self._end = end
        self._text = text

    @property
    def start(self):
        return self._start

    @property
    def end(self):
        return self._end

    @property
    def text(self):
        return self._text

    def __str__(self):
        return f"Span: {self._start} -> {self._end} [{self._text}]"

    def __repr__(self):
        return f"Span({repr(self._start)}, {repr(self._end)}, text=[{self._text}])"
