from typing import overload, Generic, TypeVar, Callable

from zs.ast.node import Node
from zs.text.parser import SubParser, Parser
from zs.text.token import TokenType, Token

_T = TypeVar("_T")
_U = TypeVar("_U")


class _SubParserWrapper(SubParser, Generic[_T]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @overload
    def __call__(self, parser: Parser, **kwargs) -> _T | None: ...
    @overload
    def __call__(self, parser: Parser, left: Node, **kwargs) -> _T | None: ...

    def __call__(self, parser: Parser, left: None = None, **kwargs) -> _T | None:
        if left is None:
            return self.nud(parser, **kwargs)
        return self.led(parser, left, **kwargs)


def _is_not(a, b, v=None):
    return a if a is not v else b


def subparser(token: TokenType | str) -> Callable[[Callable[[Parser], _T]], _SubParserWrapper[_T]]:
    def wrapper(fn: Callable[[Parser], _T]):
        return _SubParserWrapper(-1, token, nud=fn)
    return wrapper


def modifier(name: str):
    def wrapper(fn: Callable[[Token, _T], _U]):
        @subparser
        def parse(parser: Parser) -> _U:
            _modifier = parser.eat(name)

            node = parser.next()

            return fn(_modifier, node)
        return parse
    return wrapper


def separated(token: str | TokenType, binding_power: int, context: type | str = None):
    def wrapper(parser: Parser, left):
        if not parser.token(token):
            return [left] if not isinstance(left, list) else left

        if not isinstance(left, list):
            left = [left]

        parser.eat(token)
        right = parser.next(context, binding_power)
        return [*left, right]

    return wrapper


def copy_with(
        original: SubParser,
        *,
        binding_power: int = None,
        token: str | TokenType = None,
        nud: Callable[[Parser], Node] = None,
        led: Callable[[Parser, Node], Node] = None
) -> SubParser:
    return SubParser(
        _is_not(binding_power, original.binding_power),
        _is_not(token, original.token),
        nud=_is_not(nud, original.nud),
        led=_is_not(led, original.led)
    )
