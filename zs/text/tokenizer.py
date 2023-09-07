from typing import Iterable

from utilz.debug.file_info import Span, Position
from .source_file import SourceFile
from .text_stream import TextStream
from .token import Token, TokenType


__all__ = [
    "Tokenizer",
]

from ..processing import StatefulProcessor, State

_OP_CHARS = {'.', '/', '|', '+', '-', '=', '<', '>', '!', '@', '#', '$', '%', '^', '&', '*', '~', '?'}
_HEX_CHARS = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f', '_'}
_KEYWORDS = {
    "as": TokenType.As,
    "base": TokenType.Base,
    "break": TokenType.Break,
    "case": TokenType.Case,
    "catch": TokenType.Catch,
    "class": TokenType.Class,
    "continue": TokenType.Continue,
    "else": TokenType.Else,
    "false": TokenType.FalseValue,
    "finally": TokenType.Finally,
    "for": TokenType.For,
    "from": TokenType.From,
    "fun": TokenType.Fun,
    "if": TokenType.If,
    "import": TokenType.Import,
    "in": TokenType.In,
    "let": TokenType.Let,
    "module": TokenType.Module,
    "null": TokenType.Null,
    "this": TokenType.This,
    "true": TokenType.TrueValue,
    "try": TokenType.Try,
    "unit": TokenType.Unit,
    "using": TokenType.Using,
    "value": TokenType.Value,
    "var": TokenType.Var,
    "when": TokenType.When,
    "where": TokenType.Where,
    "while": TokenType.While,
}


def _is_operator_char(c: str):
    return c in _OP_CHARS


class Tokenizer(StatefulProcessor):
    _document: SourceFile | None
    _stream: TextStream | None
    _start: Position

    def __init__(self, state: State):
        super().__init__(state)
        self._document = None
        self._start = Position(1, 1)
        self._stream = None

    @property
    def text_stream(self):
        return self._stream

    def tokenize(self, document: SourceFile) -> Iterable[Token]:
        self.run()

        self._document = document
        self._stream = TextStream(document.content_stream)

        while not self._stream.eof():
            yield self._next()
        else:
            yield self._token(TokenType.EOF, self._stream.peek())

    def _token(self, typ: TokenType, value: str):
        token = Token(typ, value, Span(self._start, self._stream.position, self._stream.text))
        self._stream.clear()
        self._start = self._stream.position
        return token

    def _next(self) -> Token:
        self._start = self._stream.position

        char = self._stream.read(1)

        match char:
            case '$':
                return self._token(TokenType.Breakpoint, char)
            case '\n':
                return self._token(TokenType.NewLine, char)
            case ' ':
                return self._token(TokenType.Space, char)
            case '\t':
                return self._token(TokenType.Tab, char)
            case '{':
                return self._token(TokenType.L_Curly, char)
            case '}':
                return self._token(TokenType.R_Curly, char)
            case '(':
                return self._token(TokenType.L_Curvy, char)
            case ')':
                return self._token(TokenType.R_Curvy, char)
            case '[':
                return self._token(TokenType.L_Square, char)
            case ']':
                return self._token(TokenType.R_Square, char)
            case ';':
                return self._token(TokenType.Semicolon, char)
            case ':':
                return self._token(TokenType.Colon, char)
            case ',':
                return self._token(TokenType.Comma, char)
            case '\"':
                return self._next_string()
            case '\'':
                return self._next_char()
            case '0':
                return self._next_number(char)
            case '.' | '/' | '|' | '+' | '-' | '=' | '<' | '>' | '!' | '@' | '#' | '$' | '%' | '^' | '&' | '*' | '~' | '?':
                if char == '/' and self._stream.peek() == '/':
                    comment = ""
                    while (c := self._stream.read(1)) != '\n' and not self._stream.eof():
                        comment += c
                    return self._token(TokenType.LineComment, comment)
                if char == '/' and self._stream.peek() == '*':
                    level = 1
                    comment = ""
                    while level and not self._stream.eof():
                        c = self._stream.read(1)
                        if c == '*' and self._stream.peek() == '/':
                            level -= 1
                        elif c == '/' and self._stream.peek() == '*':
                            level += 1
                        comment += c
                    if not self._stream.eof():
                        self._stream.read(1)
                    return self._token(TokenType.BlockComment, comment)
                else:
                    return self._next_operator(char)
            case _:
                if char == '_' or char.isalpha():
                    name = self._next_identifier(char)
                    # try:
                    #     return self._token(_KEYWORDS[name], name)
                    # except KeyError:
                    return self._token(TokenType.Identifier, name)
                elif char.isdigit():
                    return self._next_number(char)
        return self._token(TokenType.Unknown, char)

    def _next_char(self):
        char = self._stream.read(1)
        if char == '\\':
            char += self._stream.read(1)
        if self._stream.peek() != '\'':
            self.state.error(f"Expected end of character literal ({self._stream.position})", self._stream.position)
        self._stream.read(1)
        return self._token(TokenType.Character, char)

    def _next_string(self):
        s = []
        while self._stream.peek() != '\"':
            c = self._stream.read(1)
            if c == '\\':
                c += self._stream.read(1)
            s.append(c)
        self._stream.read(1)
        return self._token(TokenType.String, ''.join(s))

    def _next_identifier(self, res: str):
        while True:
            c = self._stream.peek()
            if not c.isalnum() and c != '_':
                break
            res += self._stream.read(1)
        return res

    def _next_operator(self, res: str):
        while _is_operator_char(self._stream.peek()):
            res += self._stream.read(1)
        return self._token(TokenType.Operator, res)

    def _next_number(self, res: str):
        if res == '0' and self._stream.peek() == 'x':
            self._stream.read(1)
            res = ''
            while self._stream.peek().lower() in _HEX_CHARS:
                res += self._stream.read(1)
            type_, value = TokenType.Hex, res
        else:
            num = res + self._get_int()
            if self._stream.peek() == '.':
                num += self._stream.read(1)
                num += self._get_int()
                type_, value = TokenType.Real, num
            else:
                type_, value = TokenType.Decimal, num
        if self._stream.peek() in {'i', 'u', 'f', 'I', 'U'}:
            value += self._get_num_type(self._stream.read(1))
        if self._stream.peek() == '_':
            value += self._next_identifier(self._stream.read(1))
        return self._token(type_, value)

    def _get_int(self):
        res = ""
        while self._stream.peek().isdigit():
            res += self._stream.read(1)
        return res

    def _get_num_type(self, t):
        if t in {'i', 'u'}:
            match self._stream.peek():
                case '8':
                    return t + self._stream.read(1)
                case '1':
                    res = t + self._stream.read(1)
                    if self._stream.peek() == '6':
                        return res + self._stream.read(1)
                case '3':
                    res = t + self._stream.read(1)
                    if self._stream.peek() == '2':
                        return res + self._stream.read(1)
                case '6':
                    res = t + self._stream.read(1)
                    if self._stream.peek() == '4':
                        return res + self._stream.read(1)
        elif t == 'f':
            match self._stream.peek():
                case '3':
                    res = t + self._stream.read(1)
                    if self._stream.peek() == '2':
                        return res + self._stream.read(1)
                case '6':
                    res = t + self._stream.read(1)
                    if self._stream.peek() == '4':
                        return res + self._stream.read(1)
        else:
            return t
