from contextlib import contextmanager
from typing import Callable, overload, TypeVar, Generic, Type

from .token import TokenType, Token
from .token_stream import TokenStream
from ..ast.node import Node
from ..ast.node_lib import Binary, Expression, Unary
from ..processing import StatefulProcessor, State
from ..text.errors import ParseError

_T = TypeVar("_T")

__all__ = [
    "ContextualParser",
    "Parser",
    "SubParser",
]


class SubParser:
    _binding_power: int
    _token: str | TokenType
    _nud: Callable[["Parser"], Node | None] | None
    _led: Callable[["Parser", Node], Node | None] | None

    def __init__(
            self,
            binding_power: int,
            token: str | TokenType,
            *,
            nud: Callable[["Parser"], Node | None] | None = None,
            led: Callable[["Parser", Node], Node | None] | None = None
    ):
        super().__init__()
        self.binding_power = binding_power
        self._token = token if not isinstance(token, TokenType) else token
        self._nud = nud
        self._led = led

    @property
    def binding_power(self):
        return self._binding_power

    @binding_power.setter
    def binding_power(self, value: int):
        self._binding_power = value

    @property
    def token(self):
        return self._token

    @property
    def nud(self):
        return self._nud

    @nud.setter
    def nud(self, value: Callable[[TokenStream], Node | None] | None):
        self.nud = value

    @nud.deleter
    def nud(self):
        self.nud = None

    @property
    def led(self):
        return self._led

    @led.setter
    def led(self, value: Callable[[TokenStream, Node], Node | None] | None):
        self._led = value

    @led.deleter
    def led(self):
        self.led = None

    @staticmethod
    def _infix_func(binding_power: int, token: str, expr_fn: Callable[["Parser", int], Expression], factory=Binary):
        return lambda stream, left: factory(left, stream.eat(str(token)), expr_fn(stream, binding_power))

    @staticmethod
    def _prefix_func(binding_power: int, token: str, expr_fn: Callable[["Parser", int], Expression]):
        return lambda stream: Unary(stream.eat(token), expr_fn(stream, binding_power))

    @classmethod
    def infix_l(cls, binding_power: int, token: str | TokenType, expr_fn: Callable[["Parser", int], Expression], factory=Binary):
        return cls(binding_power, token, led=cls._infix_func(binding_power, token, expr_fn, factory=factory))

    @classmethod
    def infix_r(cls, binding_power: int, token: str | TokenType, expr_fn: Callable[["Parser", int], Expression], factory=Binary):
        return cls(binding_power, token, led=cls._infix_func(binding_power - 1, token, expr_fn, factory=factory))

    @classmethod
    def prefix(cls, binding_power: int, token: str | TokenType, expr_fn: Callable[["Parser", int], Expression]):
        return cls(binding_power, token, nud=cls._prefix_func(binding_power, token, expr_fn))


class ContextualParser(StatefulProcessor, Generic[_T]):
    _name: str
    _parsers: dict[str | TokenType, SubParser]
    _fallback: "list[ContextualParser[_T]]"

    def __init__(self, state: State, name: str):
        super().__init__(state)
        self._name = name
        self._parsers = {}
        self._fallback = []

    @property
    def name(self):
        return self._name

    def add_fallback_parser(self, parser: "ContextualParser[_T]"):
        self._fallback.append(parser)

    def parse(self, parser: "Parser", binding_power: int) -> _T:
        stream = parser.stream

        if stream.token == TokenType.Breakpoint:
            breakpoint()
            stream.read()

        sub = self._get_parser_for(stream.token)
        if sub is None:
            self.state.error(f"Could not parse token[NUD]: {stream.token}", stream.file)
            return
        left = sub.nud(parser)

        if sub.binding_power == -1:
            return left

        while (sub := self._get_parser_for(stream.token)) is not None and binding_power < sub.binding_power:
            try:
                left = sub.led(parser, left)
            except AttributeError:
                self.state.error(f"Could not parse token[LED]: {stream.token}", stream.file)
                return

        # if sub is None:
        #     self.state.error(f"Could not parse token \"{stream.token}\"")

        return left

    def add_parser(self, parser: SubParser):
        self._parsers[parser.token] = parser

    def add_parsers(self, *parsers: SubParser):
        for parser in parsers:
            self.add_parser(parser)

    def get_parser(self, token: str | TokenType) -> SubParser:
        return self._parsers[token]

    def setup(self, parser: "Parser"):
        ...

    def symbol(self, symbol: str | TokenType) -> SubParser:
        self.add_parser(parser := SubParser(-1, symbol, nud=lambda _: None))
        return parser

    def _get_parser_for(self, token: Token):
        sub = (
                self._parsers.get(token.type, None) or self._parsers.get(token.value, None)
        ) if token != TokenType.Identifier else (
                self._parsers.get(token.value, None) or self._parsers.get(token.type, None)
        )
        if sub is None:
            sub = self._on_unknown_token(token)
        # if sub is None:
        #     self.state.error(f"Could not parse token: {token}", token)
        return sub

    def _on_unknown_token(self, token: Token):
        for fallback in self._fallback:
            sub = fallback._get_parser_for(token)
            if sub is not None:
                return sub
        return #self.state.error(f"Could not parse symbol '{token.value}'", token)


class Parser(StatefulProcessor):
    _context_parsers: dict[str | type, ContextualParser]
    _parser_stack: list[ContextualParser]
    _stream: TokenStream

    def __init__(self, state: State, toplevel_parser: ContextualParser = None):
        super().__init__(state)
        self._context_parsers = {}
        if toplevel_parser is not None:
            self._parser_stack = [toplevel_parser]

            self.add(toplevel_parser)
        else:
            self._parser_stack = []

    @property
    def parser(self):
        return self._parser_stack[-1]

    @property
    def stream(self):
        return self._stream

    @property
    def parsers(self):
        return self._context_parsers.values()

    @contextmanager
    def context(self, name: str):
        self._parser_stack.append(parser := self._context_parsers[name])
        try:
            yield parser
        finally:
            self._parser_stack.pop()

    @overload
    def add(self, type: Type[_T]):
        ...

    @overload
    def add(self, type: Type[_T], constructor: Type[ContextualParser[_T]]):
        ...

    @overload
    def add(self, type: Type[_T], parser: ContextualParser[_T]):
        ...

    @overload
    def add(self, name: str, parser: ContextualParser[_T]):
        ...

    @overload
    def add(self, parser: ContextualParser[_T]):
        ...

    def add(self, *args):
        try:
            type_or_name, parser = args
            if not isinstance(parser, ContextualParser):
                parser = parser(self.state)
            self._context_parsers[type_or_name] = parser
            if isinstance(type_or_name, type):
                self._context_parsers[type_or_name.__name__] = parser
        except ValueError:
            parser, = args
            if isinstance(parser, ContextualParser):
                self.add(parser.name, parser)
            else:
                self.add(parser(self.state))

    @overload
    def eat(self, type_: TokenType) -> Token | None:
        ...

    @overload
    def eat(self, value: str) -> Token | None:
        ...

    def eat(self, type_or_value: TokenType | str) -> Token | None:
        if not self.token(type_or_value):
            # self.state.error(f"Expected token: \"{type_or_value}\", got \"{self.stream.token}\" instead", self.stream.file)
            raise ParseError()
        return self.stream.read()

    @overload
    def get(self, name: str) -> ContextualParser:
        ...

    @overload
    def get(self, type_: type) -> ContextualParser:
        ...

    def get(self, name_or_type: str | type) -> ContextualParser:
        return self._context_parsers[name_or_type]

    @overload
    def next(self, binding_power: int = 0) -> Node:
        ...

    @overload
    def next(self, name: str, binding_power: int = 0) -> Node:
        ...

    @overload
    def next(self, type_: Type[_T], binding_power: int = 0) -> _T:
        ...

    def next(self, name: str | Type[_T] | int = None, binding_power=0) -> Node | _T:
        if isinstance(name, int):
            binding_power = name
            name = None
        if name is None:
            return self.parser.parse(self, binding_power)
        try:
            return self.get(name).parse(self, binding_power)
        except KeyError:
            self.state.error(f"Unknown parser \"{name}\" was invoked", name)

    @overload
    def token(self) -> Token:
        ...

    @overload
    def token(self, type_: TokenType, *, eat: bool = False) -> bool:
        ...

    @overload
    def token(self, value: str, *, eat: bool = False) -> bool:
        ...

    def token(self, type_or_value: TokenType | str = None, eat: bool = False) -> bool | Token:
        if type_or_value is None:
            return self.stream.token
        token = self._stream.peek()
        if not eat:
            return token == type_or_value
        if token == type_or_value:
            self.eat(type_or_value)
            return True
        return False

    def register(self, token: str | TokenType, binding_power: int = 0) -> SubParser:
        token = token if isinstance(token, TokenType) else token
        try:
            s = self.parser.get_parser(token)
            if binding_power >= s.binding_power:
                s.binding_power = binding_power
        except KeyError:
            self.parser.add_parser(s := SubParser(binding_power, token))
        return s

    @overload
    def parse(self, stream: TokenStream):
        ...

    @overload
    def parse(self, stream: TokenStream, binding_power: int):
        ...

    def parse(self, stream: TokenStream, binding_power: int = 0):
        self.run()
        self._stream = stream
        result = []
        while not stream.end:
            try:
                node = self.next(binding_power)
                result.append(node)
                if node is None:
                    raise ParseError
            except ParseError:
                self.state.error(f"Could not parse token {self.stream.token}", self.stream.token)
                self.stream.read()
        return result

    def setup(self):
        for parser in self.parsers:
            parser.setup(self)
