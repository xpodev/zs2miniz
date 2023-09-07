from typing import Generic, TypeVar

from ..text.token_info import TokenInfo


TokenInfoT = TypeVar("TokenInfoT", bound=TokenInfo)

_T = TypeVar("_T")  # for the Node[TokenInfoT].node return type


class Node(Generic[TokenInfoT]):
    _token_info: TokenInfoT

    def __init__(self, token_info: TokenInfoT):
        self._token_info = token_info

    @property
    def token_info(self):
        return self._token_info

    @property
    def span(self):
        return self.token_info.span

    def __str__(self):
        return str(self._token_info)
