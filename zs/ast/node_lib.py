from typing import TypeVar, Generic, Optional, Union

from utilz.debug.file_info import Span
from ..text import token_info_lib as token_info
from ..text.token import Token
from .node import Node

_T = TypeVar("_T")


class Expression(Node[_T], Generic[_T]):
    """
    Base AST node for expressions.
    """


class Alias(Node[token_info.Alias]):
    """
    AST node for the alias structure:

    EXPRESSION 'as' IDENTIFIER
    """

    name: "Identifier"

    expression: Expression

    def __init__(
            self,
            expression: Expression,
            _as: Token,
            name: "Identifier"
    ):
        super().__init__(token_info.Alias(_as))
        self.name = name
        self.expression = expression


class Assign(Node[token_info.Assign]):
    """
    AST node for assignment syntax

    EXPRESSION = EXPRESSION
    """

    left: Expression
    right: Expression

    def __init__(
            self,
            left: Expression,
            _assign: Token,
            right: Expression
    ):
        super().__init__(token_info.Assign(_assign))
        self.left = left
        self.right = right

    @property
    def span(self):
        return Span.combine(self.left.span, self.right.span)


class Binary(Expression[token_info.Binary]):
    left: Expression
    right: Expression

    def __init__(self, left: Expression, _operator: Token, right: Expression):
        super().__init__(token_info.Binary(_operator))
        self.left = left
        self.right = right

    @property
    def span(self):
        return Span.combine(self.left.span, self.right.span)


class Block(Node[token_info.Block]):
    statements: list[Node]

    def __init__(
            self,
            _left_bracket: Token,
            statements: list[Node],
            _right_bracket: Token
    ):
        super().__init__(token_info.Block(_left_bracket, _right_bracket))
        self.statements = statements


class Break(Node[token_info.Break]):
    loop: Expression | None

    def __init__(self, _break: Token, loop: Expression | None, _semicolon: Token):
        super().__init__(token_info.Break(_break, _semicolon))
        self.loop = loop


class Class(Node[token_info.Class]):  # todo
    """
    AST node for the 'class' construct

    'class' IDENTIFIER? ('<' PARAMETER*(,) '>')? ':' BASES '{' CLASS_ITEMS '}'
    """

    name: Optional["Identifier"]

    bases: list[Expression]

    items: list[Node]

    def __init__(
            self,
            _class: Token,
            name: Optional["Identifier"],
            _colon: Token | None,
            bases: list[Expression],
            _left_bracket: Token,
            items: list[Node],
            _right_bracket: Token
    ):
        super().__init__(token_info.Class(_class, _colon, _left_bracket, _right_bracket))
        self.name = name
        self.bases = bases
        self.items = items


class Continue(Node[token_info.Continue]):
    loop: Expression | None

    def __init__(self, _continue: Token, loop: Expression | None, _semicolon: Token):
        super().__init__(token_info.Continue(_continue, _semicolon))
        self.loop = loop


class Export(Node[token_info.Export]):
    exported_names: "list[Identifier | Alias] | Alias | Expression | Import"
    source: Expression | None

    def __init__(
            self,
            _export: Token,
            _l_curly: Token | None,
            exported_names: "list[Identifier | Alias] | Alias | Expression | Import",
            _r_curly: Token | None,
            _from: Token | None,
            source: Expression | None,
            _semicolon: Token
    ):
        super().__init__(token_info.Export(_export, _l_curly, _r_curly, _from, _semicolon))
        self.exported_names = exported_names
        self.source = source


class ExpressionStatement(Node[token_info.ExpressionStatement]):
    expression: Expression

    def __init__(self, expression: Expression, _semicolon: Token):
        super().__init__(token_info.ExpressionStatement(_semicolon))
        self.expression = expression

    @property
    def span(self):
        return Span.combine(self.expression.span, super().span)


class Parameter(Node[token_info.Parameter]):
    name: "Identifier"
    alias: "Identifier | None"
    type: Expression | None
    initializer: Expression | None

    def __init__(
            self,
            name: "Identifier",
            alias: "Identifier | None",
            colon: Token | None,
            type: Expression | None,
            equals: Token | None,
            initializer: Expression | None
    ):
        super().__init__(token_info.Parameter(colon, equals))
        self.name = name
        self.alias = alias
        self.type = type
        self.initializer = initializer


class Function(Expression[token_info.Function]):
    """
    AST node for the function structure:

    'fun' NAME? '(' PARAMETER* ')' (WHERE_CLAUSE | WHEN_CLAUSE)* EXPRESSION
    """

    name: Optional["Identifier | Literal"]

    generic_parameters: list["Identifier"] | None
    positional_parameters: list["Parameter"]
    named_parameters: list["Parameter"]
    variadic_positional_parameter: "Parameter | None"
    variadic_named_parameter: "Parameter | None"

    return_type: Expression

    body: list[Node] | None  # Expression | None

    def __init__(
            self,
            _fun: Token,
            name: Optional["Identifier"],
            _left_square_bracket: Token | None,
            generic_parameters: list["Identifier"],
            _right_square_bracket: Token | None,
            _left_parenthesis: Token,
            positional_parameters: list["Parameter"],
            # _left_np_bracket: Token | None,
            named_parameters: list["Parameter"],
            # _right_np_bracket: Token | None,
            variadic_positional_parameter: "Parameter | None",
            variadic_named_parameter: "Parameter | None",
            _right_parenthesis: Token,
            _colon: Token,
            return_type: Expression | None,
            _left_bracket: Token | None,
            body: list[Node] | None,
            _right_bracket: Token | None,
            _semicolon: Token | None
    ):
        super().__init__(token_info.Function(_fun, _left_square_bracket, _right_square_bracket, _left_parenthesis, _right_parenthesis, _colon, _left_bracket, _right_bracket, _semicolon))
        self.name = name
        self.generic_parameters = generic_parameters
        self.positional_parameters = positional_parameters
        self.named_parameters = named_parameters
        self.variadic_positional_parameter = variadic_positional_parameter
        self.variadic_named_parameter = variadic_named_parameter
        self.return_type = return_type
        self.body = body


class FunctionCall(Expression[token_info.FunctionCall]):
    """
    AST node for the function call expression

    EXPRESSION '(' ARGUMENTS ')'
    """

    callable: Expression
    arguments: list[Expression]
    keyword_arguments: dict[str, Expression]
    operator: str

    def __init__(
            self,
            callable_: Expression,
            _left_parenthesis: Token,
            arguments: list[Expression],
            keyword_arguments: dict[str, Expression],
            _right_parenthesis: Token
    ):
        super().__init__(token_info.FunctionCall(_left_parenthesis, _right_parenthesis))
        self.callable = callable_
        self.arguments = arguments
        self.keyword_arguments = keyword_arguments
        if _left_parenthesis == '(' and _right_parenthesis == ')':
            self.operator = "()"
        elif _left_parenthesis == '{' and _right_parenthesis == '}':
            self.operator = "{}"
        elif _left_parenthesis == '[' and _right_parenthesis == ']':
            self.operator = "[]"
        else:
            raise ValueError("Call operator must be either (), [] or {}")

    @property
    def span(self):
        return Span.combine(self.callable.span, super().span)


class Identifier(Expression[token_info.Identifier]):
    """
    AST node for identifiers.
    """

    name: str

    def __init__(self, name: Token):
        super().__init__(token_info.Identifier(name))
        self.name = name.value


class If(Expression[token_info.If]):
    """
    AST node for the 'if' expression construct:

    'if' NAME '(' CONDITION ')' IF_TRUE
    'else' IF_FALSE
    """

    name: Identifier | None

    condition: Expression

    if_true: Node
    if_false: Node | None

    def __init__(
            self,
            _if: Token,
            name: Identifier | None,
            _left_parenthesis: Token,
            condition: Expression,
            _right_parenthesis: Token,
            if_true: Node,
            _else: Token | None,
            if_false: Node | None
    ):
        super().__init__(token_info.If(_if, _left_parenthesis, _right_parenthesis, _else))
        self.name = name
        self.condition = condition
        self.if_true = if_true
        self.if_false = if_false


class Import(Node[token_info.Import]):
    """
    AST node for the 'import' statement construct:

    'import' (('*' | NAME | ALIAS) 'from')? SOURCE ';'
    """

    name: list[Identifier | Alias] | Alias | Identifier | None
    source: Expression

    def __init__(
            self,
            _import: Token,
            _left_parenthesis: Token | None,
            name: list[Identifier | Alias] | Alias | Identifier | None,
            _right_parenthesis: Token | None,
            _from: Token | None,
            source: Expression,
            _semicolon: Token
    ):
        super().__init__(token_info.Import(_import, name if isinstance(name, Token) else None, _left_parenthesis, _right_parenthesis, _from, _semicolon))
        self.name = name
        self.source = source


class Inlined(Node[token_info.Inlined]):
    """
    AST node for the 'inline' modifier

    'import' (('*' | NAME | ALIAS) 'from')? SOURCE ';'
    """

    item: Node

    def __init__(
            self,
            _inline: Token,
            item: Node
    ):
        super().__init__(token_info.Inlined(_inline))
        self.item = item


class Literal(Expression[token_info.Literal]):
    """
    AST node for literals
    """

    def __init__(self, _literal: Token):
        super().__init__(token_info.Literal(_literal))


class MemberAccess(Expression[token_info.MemberAccess]):
    """
    AST node for the member access syntax

    EXPRESSION '.' IDENTIFIER
    """

    object: Expression
    member: Identifier

    def __init__(self, expr: Expression, _dot: Token, member: Identifier):
        super().__init__(token_info.MemberAccess(_dot))
        self.object = expr
        self.member = member

    @property
    def span(self):
        return Span.combine(self.object.span, self.member.span)


class Module(Node[token_info.Module]):
    """
    AST node for the 'module' statement construct:

    'module' IDENTIFIER ('.' IDENTIFIER)* ('{' ITEMS '}') | ';'
    """

    name: Identifier | None
    items: list[Node] | None

    def __init__(
            self,
            _module: Token,
            name: Identifier | None,
            _left_bracket: Token = None,
            items: list[Node] = None,
            _right_bracket: Token = None,
            _semicolon: Token = None
    ):
        super().__init__(token_info.Module(_module, _left_bracket, _right_bracket, _semicolon))
        self.name = name
        self.items = items if items is not None else items


class Property(Node[None]):  # todo
    """
    AST node for class property
    """

    def __init__(
            self,
    ):
        super().__init__(None)  # todo


class Return(Node[token_info.Return]):
    expression: Expression | None

    def __init__(
            self,
            _return: Token,
            expression: Expression | None,
            _semicolon: Token
    ):
        super().__init__(token_info.Return(_return, _semicolon))
        self.expression = expression


class Set(Node[token_info.Set]):
    name: Identifier
    expression: Expression

    def __init__(
            self,
            _set: Token,
            name: Identifier,
            _equals: Token,
            expression: Expression,
            _semicolon: Token
    ):
        super().__init__(token_info.Set(_set, _equals, _semicolon))
        self.name = name
        self.expression = expression


class Tuple(Expression[token_info.Tuple]):
    """
    AST node for a tuple

    '(' EXPRESSIONS, ... ')'
    """

    items: list[Expression]

    def __init__(self, _left_parenthesis: Token, items: list[Expression], _right_parenthesis: Token):
        super().__init__(token_info.Tuple(_left_parenthesis, _right_parenthesis))
        self.items = items


class TypeClass(Node[token_info.TypeClass]):
    """
    AST node for a type class definition
    """

    name: Identifier

    items: list[Node]

    def __init__(
            self,
            _type_class: Token,
            name: Identifier,
            _left_bracket: Token,
            items: list[Node],
            _right_bracket: Token
    ):
        super().__init__(token_info.TypeClass(_type_class, _left_bracket, _right_bracket))
        self.name = name
        self.items = items


class TypeClassImplementation(Node[token_info.TypeClassImplementation]):
    """
    AST node for a type class implementation
    """

    name: Identifier

    implemented_type: Expression

    items: list[Node]

    def __init__(
            self,
            _type_class: Token,
            name: Identifier,
            _left_parenthesis: Token,
            implemented_type: Expression,
            _right_parenthesis: Token,
            _left_bracket: Token,
            items: list[Node],
            _right_bracket: Token
    ):
        super().__init__(token_info.TypeClassImplementation(
            _type_class, _left_parenthesis, _right_parenthesis, _left_bracket, _right_bracket
        ))
        self.name = name
        self.implemented_type = implemented_type
        self.items = items


class TypedName(Node[token_info.TypedName]):
    """
    AST node for a typed name

    IDENTIFIER ':' EXPRESSION
    """

    name: Identifier
    type: Expression | None

    def __init__(self, name: Identifier, _colon: Token | None, type: Expression | None):
        super().__init__(token_info.TypedName(_colon))
        self.name = name
        self.type = type


class Unary(Expression[token_info.Unary]):
    operand: Expression

    def __init__(self, operator: Token, operand: Expression):
        super().__init__(token_info.Unary(operator))
        self.operand = operand


class Var(Node[token_info.Var]):
    name: TypedName
    initializer: Expression | None

    def __init__(self, _var: Token, name: TypedName, _assign: Token | None, initializer: Expression | None, _semicolon: Token):
        super().__init__(token_info.Var(_var, _assign, _semicolon))
        self.name = name
        self.initializer = initializer


class When(Node[token_info.When]):
    class Case(Node[token_info.When.Case]):
        expression: Expression
        body: Node

        def __init__(
                self,
                _case: Token,
                _left_parenthesis: Token,
                expression: Expression,
                _right_parenthesis: Token,
                body: Node,
        ):
            super().__init__(token_info.When.Case(
                _case,
                _left_parenthesis,
                _right_parenthesis
            ))
            self.expression = expression
            self.body = body

    name: Identifier | None
    expression: Expression
    cases: list[Case]
    else_body: Node

    def __init__(
            self,
            _when: Token,
            name: Identifier | None,
            _left_parenthesis: Token,
            expression: Expression,
            _right_parenthesis: Token,
            _left_bracket: Token,
            cases: list[Case],
            _right_bracket: Token,
            _else: Token | None,
            else_body: Node | None
    ):
        super().__init__(token_info.When(
            _when,
            _left_parenthesis,
            _right_parenthesis,
            _left_bracket,
            _right_bracket,
            _else
        ))
        self.name = name
        self.expression = expression
        self.cases = cases
        self.else_body = else_body


class While(Node[token_info.While]):
    name: Identifier | None
    condition: Expression
    body: Node
    else_body: Node | None

    def __init__(
            self,
            _keyword_while: Token,
            name: Identifier | None,
            _left_parenthesis: Token,
            condition: Expression,
            _right_parenthesis: Token,
            body: Node,
            _else: Token,
            else_body: Node | None
    ):
        super().__init__(token_info.While(_keyword_while, _left_parenthesis, _right_parenthesis, _else))
        self.name = name
        self.condition = condition
        self.body = body
        self.else_body = else_body
