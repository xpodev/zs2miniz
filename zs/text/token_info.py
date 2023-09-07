__all__ = [
    "TokenInfo",
]

import dataclasses

from utilz.debug.file_info import Span


@dataclasses.dataclass(
    slots=True,
    frozen=True,
    init=False
)
class TokenInfo:
    @property
    def span(self):
        spans = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if value is not None:
                spans.append(value.span)
        return Span.combine(*spans)

    def __str__(self):
        try:
            return str(getattr(self, self.__slots__[0]))
        except AttributeError:
            return super().__str__()
