from functools import wraps
from typing import Callable, TypeVar, Any

from zs.ast.node import Node
from zs.ast.node_lib import Function, Class, If, Expression, Binary, ExpressionStatement, Identifier, Literal, Module, Import, Alias, TypedName, FunctionCall, MemberAccess, Block, Return, While, \
    Continue, Break, When, Var, TypeClass, TypeClassImplementation, Assign, Export, Set, Parameter
from zs.processing import State
from zs.std.parsers.misc import subparser, copy_with
from zs.text.errors import ParseError
from zs.text.parser import ContextualParser, Parser, SubParser

# expression nodes
from zs.text.token import TokenType, Token

# utility parsers

_SENTINEL = object()
_T = TypeVar("_T")
_U = TypeVar("_U")


def _with_default(fn: Callable[[Parser, ...], _T]):
    @wraps(fn)
    def wrapper(parser: Parser, *args, default: _U = _SENTINEL, **kwargs) -> _T | _U:
        try:
            return fn(parser, *args, **kwargs)
        except ParseError:
            if default is _SENTINEL:
                raise
            return default

    return wrapper


@subparser(TokenType.Identifier)
@_with_default
def _identifier(parser: Parser):
    if parser.token(TokenType.Identifier):
        return Identifier(parser.eat(TokenType.Identifier))
    raise ParseError


@subparser(TokenType.String)
@_with_default
def _string(parser: Parser):
    if parser.token(TokenType.String):
        return Literal(parser.eat(TokenType.String))
    raise ParseError


@subparser(TokenType.Character)
@_with_default
def _char(parser: Parser):
    if parser.token(TokenType.Character):
        return Literal(parser.eat(TokenType.Character))
    raise ParseError


@subparser(TokenType.Decimal)
@_with_default
def _decimal(parser: Parser):
    if parser.token(TokenType.Decimal):
        return Literal(parser.eat(TokenType.Decimal))
    raise ParseError


@subparser(TokenType.Real)
@_with_default
def _real(parser: Parser):
    if parser.token(TokenType.Real):
        return Literal(parser.eat(TokenType.Real))
    raise ParseError


@_with_default
def separated(fn: Callable[[Parser], _T], sep: Callable[[Parser], Any]) -> Callable[[Parser], list[_T]]:
    @_with_default
    def wrapper(parser: Parser) -> list[_T]:
        result = []
        while True:
            result.append(fn(parser))
            try:
                sep(parser)
            except ParseError:
                break
        return result

    return wrapper


def _one_of(*fns: Callable[[Parser], Node]):
    @_with_default
    def wrapper(parser: Parser) -> Node:
        for fn in fns:
            try:
                return fn(parser)
            except ParseError:
                ...
        raise ParseError

    return wrapper


def _next(name: str) -> Callable[[Parser], _T]:
    @_with_default
    def wrapper(parser: Parser) -> _T:
        return parser.next(name)

    return wrapper


def _eat(token: str | TokenType) -> Callable[[Parser], _T]:
    @_with_default
    def wrapper(parser: Parser) -> _T:
        return parser.eat(token)

    return wrapper


def _many(fn: Callable[[Parser], _T]) -> Callable[[Parser], list[_T]]:
    @_with_default
    def wrapper(parser: Parser) -> list[_T]:
        result = []
        while True:
            try:
                result.append(fn(parser))
            except ParseError:
                break
        return result

    return wrapper


def _chain(*args: Callable[[Parser], _T]) -> Callable[[Parser], _T]:
    @_with_default
    def wrapper(parser: Parser):
        return [arg(parser) for arg in args]

    return wrapper


def _map(parser_fn: Callable[[Parser], _T], fn: Callable[[_T], _U]) -> Callable[[Parser], _U]:
    @_with_default
    def wrapper(parser: Parser):
        return fn(parser_fn(parser))

    return wrapper

# parsers


# @subparser("var")
# def parse_variable(parser: Parser) -> Variable:
#     ...
#
#
# @subparser("let")
# def parse_immutable(parser: Parser) -> Immutable:
#     ...
#
#
# @subparser("const")
# def parse_constant(parser: Parser) -> Constant:
#     """
#     Not to be confused with literal
#     """
#     ...


def parse_typed_name(parser: Parser) -> TypedName:
    name = _identifier(parser)

    if parser.token(':'):
        _colon = parser.eat(':')
        type_ = parser.next("Expression", 70)
    else:
        _colon = type_ = None

    return TypedName(
        name,
        _colon,
        type_
    )


def parse_parameter(parser: Parser) -> Parameter:
    name = _identifier(parser)

    if parser.token("as", eat=True):
        alias = _identifier(parser)
    else:
        alias = None

    colon = type = None
    if parser.token(':'):
        colon = parser.eat(':')
        type = parser.next("Expression", binding_power=7)  # '=' symbol is 5

    equals = initializer = None
    if parser.token('='):
        equals = parser.eat('=')
        initializer = parser.next("Expression")

    return Parameter(name, alias, colon, type, equals, initializer)


@subparser('{')
def parse_block(parser: Parser) -> Block:
    _left_bracket = parser.eat('{')

    statements = []

    while not parser.token('}'):
        statements.append(parser.next())

    _right_bracket = parser.eat('}')

    return Block(_left_bracket, statements, _right_bracket)


@subparser('(')
def parse_parenthesised_expression_or_tuple(parser: Parser) -> Expression:
    _left_parenthesis = parser.eat('(')

    expressions = []

    is_tuple = False
    while not parser.token(')'):
        expressions.append(parser.next("Expression"))

        if parser.token(',', eat=True):
            is_tuple = True

    _right_parenthesis = parser.eat(')')

    if is_tuple:
        raise ValueError("Tuples are not yet supported")
    else:
        if len(expressions) != 1:
            raise ValueError("???")

        return expressions[0]


# statements


@subparser("export")
def parse_export(parser: Parser) -> Export:
    keyword = parser.eat("export")

    _l_curly = _r_curly = None

    source = True
    _from = _semicolon = None
    if parser.token('*'):
        exported_items = Identifier(parser.eat('*'))
        if parser.token("as"):
            exported_items = Alias(exported_items, parser.eat("as"), _identifier(parser))
    elif parser.token('{'):
        exported_items: list[Identifier | Alias] | Identifier | Alias = []
        _l_curly = parser.eat('{')
        while not parser.token('}'):
            name = _identifier(parser)

            if parser.token("as"):
                name = Alias(name, parser.eat("as"), _identifier(parser))

            exported_items.append(name)

            if not parser.token('}'):
                parser.eat(',')
            else:
                break
        _r_curly = parser.eat('}')
    else:
        exported_items = _one_of(
            parse_var,
            parse_function,
            parse_class,
            parse_module,
            parse_type_class,
            parse_import,
            _map(_chain(_identifier, _eat(';')), lambda items: items[0])
        )(parser)

        if parser.token("as"):
            exported_items = Alias(exported_items, parser.eat("as"), _identifier(parser))
            _semicolon = parser.eat(';')

        source = None

    if source:
        _from = parser.eat("from")

        source = _one_of(
            parse_import,
            _next("ExpressionStatement")
        )(parser)

        # _semicolon = parser.eat(';')
        _semicolon = None

    return Export(keyword, _l_curly, exported_items, _r_curly, _from, source, _semicolon)


@subparser("import")
def parse_import(parser: Parser) -> Import:
    keyword = parser.eat("import")

    if parser.token('*'):
        imported_names = Identifier(parser.eat('*'))
        if parser.token("as"):
            imported_names = Alias(imported_names, parser.eat("as"), _identifier(parser))
    elif parser.token(TokenType.String):
        return Import(keyword, None, None, None, None, _string(parser), parser.eat(';'))
    else:
        imported_names: list[Identifier | Alias] | Identifier | Alias = []

    _l_curly = _r_curly = None
    if parser.token('{'):
        _l_curly = parser.eat('{')
        while not parser.token('}'):
            name = _identifier(parser)

            if parser.token("as"):
                name = Alias(name, parser.eat("as"), _identifier(parser))

            imported_names.append(name)

            if not parser.token('}'):
                parser.eat(',')
            else:
                break
        _r_curly = parser.eat('}')

    _from = parser.eat("from")

    source = parser.next("Expression")

    return Import(
        keyword, _l_curly, imported_names, _r_curly, _from, source, parser.eat(';')
    )


@subparser("fun")
def parse_function(parser: Parser) -> Function:
    keyword = parser.eat("fun")

    name = _one_of(_identifier, _string)(parser, default=None)

    generic_parameters = None
    _left_square_bracket = _right_square_bracket = None

    if parser.token('['):
        generic_parameters = []
        _left_square_bracket = parser.eat('[')

        while not parser.token(']'):
            generic_parameters.append(_identifier(parser))

            if not parser.token(',', eat=True):
                break

        _right_square_bracket = parser.eat(']')

    positional_parameters = []
    named_parameters = []

    _left_parenthesis = parser.eat('(')

    while not parser.token(')'):
        if parser.token('*') or parser.token('**'):
            break

        if parser.token('{', eat=True):
            while not parser.token('}'):
                named_parameters.append(parse_parameter(parser))

                if not parser.token(TokenType.Comma, eat=True):
                    break
            parser.eat('}')
        else:
            positional_parameters.append(parse_parameter(parser))

        if not parser.token(TokenType.Comma, eat=True):
            break

    variadic_positional_parameter = variadic_named_parameter = None
    if parser.token('*', eat=True):
        variadic_positional_parameter = parse_parameter(parser)

        parser.token(TokenType.Comma, eat=True)

    if parser.token("**", eat=True):
        variadic_named_parameter = parse_parameter(parser)

        parser.token(TokenType.Comma, eat=True)

    _right_parenthesis = parser.eat(')')

    _colon = return_type = None
    if parser.token(":"):
        _colon = parser.eat(":")

        return_type = parser.next("Expression")

    if parser.token(';'):
        _left_bracket = _right_bracket = body = None
        _semicolon = parser.eat(';')
    else:
        _semicolon = None
        _left_bracket = parser.eat('{')

        body = []
        with parser.context("Function.Body"):
            while not parser.token('}'):
                body.append(parser.next())

        _right_bracket = parser.eat('}')

    return Function(
        keyword,
        name,
        _left_square_bracket,
        generic_parameters,
        _right_square_bracket,
        _left_parenthesis,
        positional_parameters,
        named_parameters,
        variadic_positional_parameter,
        variadic_named_parameter,
        _right_parenthesis,
        _colon,
        return_type,
        _left_bracket,
        body,
        _right_bracket,
        _semicolon
    )


@subparser("class")
def parse_class(parser: Parser) -> Class:
    keyword = parser.eat("class")

    name = _one_of(_identifier, _string)(parser, default=None)

    generic = None
    if parser.token('[', eat=True):
        generic = []
        while True:
            generic.append(_identifier(parser))
            if not parser.token(',', eat=True):
                break
        parser.eat(']')

    if parser.token('('):
        _left_parenthesis = parser.eat('(')
        metaclass = parser.next("Expression")
        _right_parenthesis = parser.eat(')')
    else:
        _left_parenthesis = _right_parenthesis = metaclass = None

    bases = []
    if parser.token('<'):
        _colon = parser.eat('<')
        # bases = separated(parser, _next("Expression"), _eat(','))
        while True:
            expr = parser.next("Expression")
            assert isinstance(expr, Expression)
            bases.append(expr)
            if not parser.token(',', eat=True):
                break
    else:
        _colon = None

    _left_bracket = parser.eat('{')

    items = []

    while not parser.token('}'):
        items.append(_one_of(
            parse_var,
            parse_function,
            parse_class,
        )(parser))

    _right_bracket = parser.eat('}')

    return Class(
        keyword,
        name,
        generic,
        # _left_parenthesis,
        # metaclass,
        # _right_parenthesis,
        _colon,
        bases,
        _left_bracket,
        items,
        _right_bracket,
    )


@subparser("module")
def parse_module(parser: Parser) -> Module:
    keyword = parser.eat("module")

    name = _identifier(parser, default=None)

    items = []
    if parser.token(';'):
        _semicolon = parser.eat(';')
        _left_bracket = _right_bracket = None
    else:
        _semicolon = None
        _left_bracket = parser.eat('{')

        # items = _many(_next("Document"))(parser)
        with parser.context("Document"):
            while not parser.token('}'):
                items.append(parser.next())

        _right_bracket = parser.eat('}')

    return Module(
        keyword,
        name,
        _left_bracket,
        items,
        _right_bracket,
        _semicolon
    )


@subparser("set")
def parse_set(parser: Parser) -> Set:
    keyword = parser.eat("set")

    name = _identifier(parser)

    _equals = parser.eat('=')

    expression = parser.next("Expression")

    _semicolon = parser.eat(';')

    return Set(keyword, name, _equals, expression, _semicolon)


@subparser("typeclass")
def parse_type_class(parser: Parser) -> TypeClass | TypeClassImplementation:
    keyword = parser.eat("typeclass")

    name = _identifier(parser)

    if parser.token('('):
        _left_parenthesis = parser.eat('(')
        implemented_type = parser.next("Expression")
        _right_parenthesis = parser.eat(')')
    else:
        _left_parenthesis = implemented_type = _right_parenthesis = None

    _left_bracket = parser.eat('{')

    items = []
    while not parser.token('}'):
        items.append(_one_of(
            parse_class,
            parse_function,
            parse_var,
            parse_type_class
        )(parser))

    _right_bracket = parser.eat('}')

    if implemented_type is not None:
        return TypeClassImplementation(
            keyword,
            name,
            _left_parenthesis,
            implemented_type,
            _right_parenthesis,
            _left_bracket,
            items,
            _right_bracket
        )
    else:
        return TypeClass(keyword, name, _left_bracket, items, _right_bracket)


@subparser("var")
def parse_var(parser: Parser) -> Var:
    keyword = parser.eat("var")

    typed_name = parse_typed_name(parser)

    if parser.token('='):
        _assign = parser.eat('=')
        initializer = parser.next("Expression")
    else:
        _assign = initializer = None

    _semicolon = parser.eat(';')

    return Var(keyword, typed_name, _assign, initializer, _semicolon)


# operators


# @subparser(TokenType.Operator)
# def parse_prefix(parser: Parser) -> Prefix:
#     ...


def parse_infix(parser: Parser, left: Expression) -> Binary:
    ...


def parse_argument_list(parser: Parser, terminator: str | TokenType):
    arguments = []
    keyword_arguments = {}

    while not parser.token(terminator):
        if parser.token(TokenType.Identifier):
            with parser.stream.save_position() as pos:
                expr = parser.eat(TokenType.Identifier)
                if parser.token(':', eat=True):
                    name: str = expr.value
                    expr = parser.next("Expression")
                    assert isinstance(expr, Expression)
                    keyword_arguments[name] = expr
                    pos.commit()
                    continue
        expr = parser.next("Expression")
        arguments.append(expr)

        if not parser.token(',', eat=True):
            break

    return arguments, keyword_arguments


def parse_call(left_bracket: str | TokenType, right_bracket: str | TokenType):
    def wrapper(parser: Parser, left: Expression) -> FunctionCall:
        _left_bracket = parser.eat(left_bracket)

        arguments, keyword_arguments = parse_argument_list(parser, right_bracket)

        _right_bracket = parser.eat(right_bracket)

        return FunctionCall(left, _left_bracket, arguments, keyword_arguments, _right_bracket)

    return wrapper


parse_curvy_call = parse_call('(', ')')
parse_square_call = parse_call('[', ']')
parse_curly_call = parse_call('{', '}')


def parse_member_access(parser: Parser, left: Expression) -> MemberAccess:
    _dot = parser.eat('.')

    member = _identifier(parser)

    return MemberAccess(left, _dot, member)


# todo: parse postfix


# imperative statements


@subparser("if")
def parse_if(parser: Parser) -> If:
    keyword = parser.eat("if")

    name = _identifier(parser, default=None)

    _left_parenthesis = parser.eat('(')

    condition = parser.next("Expression")

    _right_parenthesis = parser.eat(')')

    if_true = parser.next()

    if parser.token("else"):
        _else = parser.eat("else")
        if_false = parser.next()
    else:
        _else = if_false = None

    return If(keyword, name, _left_parenthesis, condition, _right_parenthesis, if_true, _else, if_false)


@subparser("while")
def parse_while(parser: Parser) -> While:
    keyword = parser.eat("while")

    name = _identifier(parser, default=None)

    _left_parenthesis = parser.eat('(')

    condition = parser.next("Expression")

    _right_parenthesis = parser.eat(')')

    body = parser.next()

    if parser.token("else"):
        else_ = parser.eat("else")
        else_body = parser.next()
    else:
        else_ = else_body = None

    return While(keyword, name, _left_parenthesis, condition, _right_parenthesis, body, else_, else_body)


# @subparser("for")
# def parse_for(parser: Parser) -> For:
#     ...


@subparser("when")
def parse_when(parser: Parser) -> When:
    keyword = parser.eat("when")

    name = _identifier(parser, default=None)

    _left_parenthesis = parser.eat('(')

    expression = parser.next("Expression")

    _right_parenthesis = parser.eat(')')

    _left_bracket = parser.eat('{')

    cases = []

    while not parser.token('}'):
        case_keyword = parser.eat("case")
        case_left_parenthesis = parser.eat('(')
        case_expression = parser.next("Expression")
        case_right_parenthesis = parser.eat(')')
        case_body = parser.next()

        cases.append(
            When.Case(
                case_keyword,
                case_left_parenthesis,
                case_expression,
                case_right_parenthesis,
                case_body
            )
        )

    _right_bracket = parser.eat('}')

    if parser.token("else"):
        else_ = parser.eat("else")
        else_body = parser.next()
    else:
        else_ = else_body = None

    return When(
        keyword,
        name,
        _left_parenthesis,
        expression,
        _right_parenthesis,
        _left_bracket,
        cases,
        _right_bracket,
        else_,
        else_body
    )


@subparser("return")
def parse_return(parser: Parser) -> Return:
    keyword = parser.eat("return")

    expression = None
    if not parser.token(';'):
        expression = parser.next("Expression")

    _semicolon = parser.eat(';')

    return Return(keyword, expression, _semicolon)


@subparser("continue")
def parse_continue(parser: Parser) -> Continue:
    keyword = parser.eat("continue")

    loop = None
    if not parser.token(';'):
        loop = parser.next("Expression")

    _semicolon = parser.eat(';')

    return Continue(keyword, loop, _semicolon)


@subparser("break")
def parse_break(parser: Parser) -> Break:
    keyword = parser.eat("break")

    loop = None
    if not parser.token(';'):
        loop = parser.next("Expression")

    _semicolon = parser.eat(';')

    return Break(keyword, loop, _semicolon)


class ExpressionParser(ContextualParser[Expression]):
    """
    Parses a single Z# expression
    """

    def __init__(self, state: State):
        super().__init__(state, "Expression")

        self.add_parser(copy_with(_char, binding_power=0))
        self.add_parser(copy_with(_string, binding_power=0))
        self.add_parser(copy_with(_identifier, binding_power=0))
        self.add_parser(copy_with(_decimal, binding_power=0))
        self.add_parser(copy_with(_real, binding_power=0))

        self.add_parser(SubParser(
            100, '(', led=parse_curvy_call, nud=parse_parenthesised_expression_or_tuple
        ))
        self.add_parser(SubParser(
            100, '[', led=parse_square_call
        ))
        self.add_parser(SubParser(
            100, '{', led=parse_curly_call
        ))
        self.add_parser(SubParser(
            120, '.', led=parse_member_access
        ))

        self.add_parser(copy_with(parse_function, binding_power=0))
        self.add_parser(copy_with(parse_module, binding_power=0))
        self.add_parser(copy_with(parse_class, binding_power=0))
        self.add_parser(copy_with(parse_type_class, binding_power=0))

        self.add_parser(SubParser.infix_r(5, '=', self.parse, Assign))

        self.add_parser(SubParser.infix_l(50, '+', self.parse))
        self.add_parser(SubParser.infix_l(50, '-', self.parse))

        self.add_parser(SubParser.infix_l(50, '*', self.parse))
        self.add_parser(SubParser.infix_l(50, '/', self.parse))
        self.add_parser(SubParser.infix_l(50, '%', self.parse))

        # terminal symbols

        self.symbol(',')
        self.symbol(')')
        self.symbol(';')
        self.symbol('{')

    def parse(self, parser: "Parser", binding_power: int) -> _T:
        expression = super().parse(parser, binding_power)

        if isinstance(expression, Identifier) and expression.name in {
            "true",
            "false",
            "null",
        }:
            return Literal(expression.token_info.name)

        return expression


class ExpressionStatementParser(ContextualParser[ExpressionStatement]):
    """
    Parses a single Z# expression statement
    """

    _parser: Parser
    _expr: ContextualParser

    def __init__(self, state: State):
        super().__init__(state, "ExpressionStatement")

    def parse(self, parser: Parser, binding_power: int) -> ExpressionStatement:
        expression = parser.next("Expression", binding_power)

        _semicolon = parser.eat(';')

        return ExpressionStatement(expression, _semicolon)

    def setup(self, parser: "Parser"):
        self._parser = parser
        self._expr = parser.get("Expression")
        self.add_fallback_parser(parser.get("Expression"))

    def _get_parser_for(self, token: Token):
        sub = self._expr._get_parser_for(token)
        if sub is None:
            return sub

        def nud(parser: Parser) -> ExpressionStatement:
            expression = parser.next("Expression")
            _semicolon = parser.eat(';')
            return ExpressionStatement(expression, _semicolon)

        return SubParser(
            -1, token.value, nud=nud
        )


class DocumentParser(ContextualParser[list[Node]]):
    """
    Parses a Z# document
    """

    def __init__(self, state: State):
        super().__init__(state, "Document")


class FunctionBodyParser(ContextualParser[list[Node]]):
    """
    Parses the body of a function. This parser outputs a list of statements.
    """

    def __init__(self, state: State):
        super().__init__(state, "Function.Body")

    def setup(self, parser: "Parser"):
        self.add_fallback_parser(parser.get("Document"))


# utility


def _get_function_body_parser(state: State):
    parser = FunctionBodyParser(state)

    parser.add_parsers(
        parse_return
    )

    return parser


def get_parser(state: State):
    document = DocumentParser(state)
    parser = Parser(state, document)

    document.add_parsers(
        parse_if,
        parse_while,
        # parse_for,
        parse_when,

        parse_block,

        parse_export,
        parse_import,
        parse_function,
        parse_class,
        parse_module,
        parse_set,
        parse_type_class,
        parse_var,

        parse_continue,
        parse_break,
    )

    expression_parser = ExpressionParser(state)
    expression_statement_parser = ExpressionStatementParser(state)
    function_body_parser = _get_function_body_parser(state)

    document.add_fallback_parser(expression_statement_parser)

    parser.add(expression_parser)
    parser.add(expression_statement_parser)
    parser.add(function_body_parser)

    return parser
