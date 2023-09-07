__all__ = [
    "TokenInfo",
]


from utilz.debug.file_info import Span
class TokenInfo:
    def __str__(self):
        try:
            return str(getattr(self, self.__slots__[0]))
        except AttributeError:
            return super().__str__()
