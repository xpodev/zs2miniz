from enum import Enum

from .file_info import Span


__all__ = [
    "Token",
    "TokenCategory",
    "TokenType",
]


class TokenCategory(str, Enum):
    WS = "WS"
    Misc = "Misc"
    Term = "Term"
    Symbol = "Symbol"
    Literal = "Literal"
    KW = "KW"

    def __str__(self):
        return self.value


class TokenType(str, Enum):
    Space = f"{TokenCategory.WS}.Space"
    NewLine = f"{TokenCategory.WS}.EOL"
    Tab = f"{TokenCategory.WS}.Tab"
    LineComment = f"{TokenCategory.WS}.LineComment"
    BlockComment = f"{TokenCategory.WS}.BlockComment"

    EOF = f"{TokenCategory.Misc}.EOF"
    Unknown = f"{TokenCategory.Misc}.Unknown"
    Breakpoint = f"{TokenCategory.Misc}.Breakpoint"

    Identifier = f"{TokenCategory.Term}.Identifier"

    # symbols

    L_Curly = f"{TokenCategory.Symbol}.Bracket.Curly.L"
    R_Curly = f"{TokenCategory.Symbol}.Bracket.Curly.R"
    L_Curvy = f"{TokenCategory.Symbol}.Bracket.Curvy.L"
    R_Curvy = f"{TokenCategory.Symbol}.Bracket.Curvy.R"
    L_Square = f"{TokenCategory.Symbol}.Bracket.Square.L"
    R_Square = f"{TokenCategory.Symbol}.Bracket.Square.R"

    Semicolon = f"{TokenCategory.Symbol}.Semicolon"
    Colon = f"{TokenCategory.Symbol}.Colon"
    Comma = f"{TokenCategory.Symbol}.Comma"

    Operator = f"{TokenCategory.Symbol}.Operator"

    # literals

    String = f"{TokenCategory.Literal}.String"
    Character = f"{TokenCategory.Literal}.Character"

    Hex = f"{TokenCategory.Literal}.Number.Hex"
    Decimal = f"{TokenCategory.Literal}.Number.Integral"
    Real = f"{TokenCategory.Literal}.Number.Real"

    TrueValue = f"{TokenCategory.Literal}.Boolean.True"
    FalseValue = f"{TokenCategory.Literal}.Boolean.False"

    Null = f"{TokenCategory.Literal}.Object.Null"
    This = f"{TokenCategory.Literal}.Object.This"
    Base = f"{TokenCategory.Literal}.Object.Base"
    Unit = f"{TokenCategory.Literal}.Object.Unit"

    # keywords

    As = f"{TokenCategory.KW}.As"
    Break = f"{TokenCategory.KW}.Break"
    Case = f"{TokenCategory.KW}.Case"
    Catch = f"{TokenCategory.KW}.Catch"
    Class = f"{TokenCategory.KW}.Class"
    Continue = f"{TokenCategory.KW}.Continue"
    Else = f"{TokenCategory.KW}.Else"
    Finally = f"{TokenCategory.KW}.Finally"
    For = f"{TokenCategory.KW}.For"
    From = f"{TokenCategory.KW}.From"
    Fun = f"{TokenCategory.KW}.Fun"
    If = f"{TokenCategory.KW}.If"
    Import = f"{TokenCategory.KW}.Import"
    In = f"{TokenCategory.KW}.In"
    Let = f"{TokenCategory.KW}.Let"
    Module = f"{TokenCategory.KW}.Module"
    Try = f"{TokenCategory.KW}.Try"
    Using = f"{TokenCategory.KW}.Using"
    Value = f"{TokenCategory.KW}.Value"
    Var = f"{TokenCategory.KW}.Var"
    When = f"{TokenCategory.KW}.When"
    Where = f"{TokenCategory.KW}.Where"
    While = f"{TokenCategory.KW}.While"


class Token:
    _type: TokenType
    _span: Span
    _value: str

    def __init__(self, type_: TokenType, value: str, span: Span):
        super().__init__()
        self._span = span
        self._value = value
        self._type = type_

    @property
    def span(self):
        return self._span

    @property
    def value(self):
        return self._value

    @property
    def type(self):
        return self._type

    @property
    def category(self):
        return self.type.value.split('.')[0]

    # categories
    @property
    def is_whitespace(self):
        return self.category == TokenCategory.WS

    @property
    def is_symbol(self):
        return self.category == TokenCategory.Symbol

    @property
    def is_term(self):
        return self.category == TokenCategory.Term

    def __str__(self):
        return f"Token {self.type} @ {self.span}"

    def __repr__(self):
        return f"Token({self._type.value}, {repr(self._value)}, {repr(self._span)})"

    def __eq__(self, other):
        if isinstance(other, TokenType):
            return self._type == other
        if isinstance(other, str):
            return self._value == other
        else:
            raise TypeError(f"Can't compare between types: {Token} and {type(other)}")

