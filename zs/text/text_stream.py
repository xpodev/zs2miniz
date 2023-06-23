import io

from .file_info import Position


__all__ = [
    "TextStream",
]


class TextStream:
    class TextStreamSavePosition:
        def __init__(self, stream: "TextStream"):
            self.stream = stream
            self.position = None
            self._offset = None
            self._restore = True

        def restore(self):
            self.stream._position.set(self.position)
            begin = self._offset - self.stream._file.tell()
            if begin:
                del self.stream._buffer[begin:]
            self.stream._file.seek(self._offset)

        def commit(self):
            self._restore = False

        def __enter__(self):
            self.position = self.stream.position.copy()
            self._offset = self.stream._file.tell()
            return self

        def __exit__(self, *_):
            if self._restore:
                self.restore()
            return False

    def __init__(self, file: io.TextIOBase) -> None:
        super().__init__()
        self._position = Position(1, 1)
        self._file = file
        self._buffer = []

    @property
    def text(self):
        return ''.join(self._buffer)

    @property
    def position(self) -> Position:
        return self._position.copy()

    def clear(self):
        self._buffer.clear()

    def peek(self, amount: int = 1) -> str:
        with self.save_position():
            return self.read(amount)

    def read(self, amount: int = 1) -> str:
        result = self._file.read(amount)
        self._buffer.append(result)
        for c in result:
            if c == '\n':
                self._position.next_line()
            else:
                self._position.next_column()
        return result

    def eof(self) -> bool:
        return not self.peek()

    def save_position(self):
        return self.TextStreamSavePosition(self)
