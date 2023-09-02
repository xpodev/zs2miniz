from contextlib import contextmanager
from enum import Enum
from typing import Iterable

from .token import Token, TokenType


__all__ = [
    "SeekMode",
    "TokenStream",
]


class SeekMode(int, Enum):
    Start = 0
    Current = 1
    End = 2


class SavePosition:
    _stream: "TokenStream"
    _restore: bool

    def __init__(self, stream: "TokenStream"):
        self._stream = stream
        self._restore = True
        self._position = stream.position

    @property
    def should_restore(self):
        return self._restore

    def restore(self):
        self._stream.seek(self._position, SeekMode.Start)
        self.commit()

    def commit(self):
        self._restore = False


class TokenStream:
    _tokens: list[Token]
    _current: int
    _file: str

    def __init__(self, tokens: Iterable[Token], file: str):
        super().__init__()
        self._tokens = list(filter(lambda t: not t.is_whitespace, tokens))
        self._current = 0
        self._file = file

    @property
    def position(self):
        return self._current

    @property
    def end(self):
        return self._current == len(self._tokens) or self.token.type == TokenType.EOF

    @property
    def token(self) -> Token:
        return self._tokens[self._current]

    @property
    def file(self):
        return self._file

    def peek(self, next_: int = 0) -> Token:
        return self._tokens[self._current + next_]

    def seek(self, pos: int, mode: SeekMode = SeekMode.Current):
        if mode == SeekMode.Start:
            self._current = pos
        elif mode == SeekMode.Current:
            self._current += pos
        elif mode == SeekMode.End:
            self._current = len(self._tokens) - pos
        else:
            raise ValueError(mode)

    def read(self) -> Token:
        if self.end:
            return self.token
        token = self.token
        self._current += 1
        return token

    def __iter__(self):
        return self._tokens[self._current:]

    @contextmanager
    def save_position(self):
        state = SavePosition(self)
        try:
            yield state
        finally:
            if state.should_restore:
                state.restore()