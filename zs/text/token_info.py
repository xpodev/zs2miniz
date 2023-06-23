__all__ = [
    "TokenInfo",
]


class TokenInfo:
    def __str__(self):
        try:
            return str(getattr(self, self.__slots__[0]))
        except AttributeError:
            return super().__str__()
