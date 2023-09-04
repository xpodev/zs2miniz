from typing import Generic, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.ast.node_lib import (
    Alias,
    Assign,
    Binary,
    Block,
    Break,
    Class,
    Expression,
    ExpressionStatement,
    Function,
    FunctionCall,
    Identifier,
    If,
    Import,
    Literal,
    MemberAccess,
    Module,
    Parameter,
    Return,
    Unary,
    Var,
    While,
)

_T = TypeVar("_T", bound=Node)


class ResolvedNode(Generic[_T]):
    node: _T

    def __init__(self, node: _T | None):
        self.node = node
        self._init()

    def _init(self):
        ...

    def __str__(self):
        name = getattr(self, "name", f"at {id(self)}")

        return f"<{type(self).__name__} object '{name}'>"


class ResolvedExpression(ResolvedNode[Expression[_T]], Generic[_T]):
    ...


class ResolvedStatement(ResolvedNode[_T], Generic[_T]):
    ...


# region Concrete


class ResolvedAssign(ResolvedExpression[Assign]):
    left: ResolvedExpression
    right: ResolvedExpression


class ResolvedBinary(ResolvedExpression[Binary]):
    left: ResolvedExpression
    right: ResolvedExpression

    @property
    def operator(self):
        return self.node.token_info.operator.value


class ResolvedBlock(ResolvedStatement[Block]):
    body: list[ResolvedNode]


class ResolvedBreak(ResolvedStatement[Break]):
    loop: "ResolvedWhile"


class ResolvedClass(ResolvedExpression[Class]):
    bases: list[ResolvedExpression]

    items: list[ResolvedNode]

    def _init(self):
        self.bases = []
        self.items = []

    @property
    def name(self):
        return self.node.name.name if self.node.name is not None else None

    def __str__(self):
        return f"ResolvedClass {self.name or '{Anonymous}'}"


class ResolvedExpressionStatement(ResolvedStatement[ExpressionStatement]):
    expression: ResolvedExpression


class ResolvedFunctionBody(ResolvedNode[None]):
    owner: "ResolvedFunction"
    instructions: list[ResolvedNode] | None

    def __init__(self, owner: "ResolvedFunction"):
        super().__init__(None)
        self.owner = owner
        self.instructions = None


class ResolvedFunction(ResolvedNode[Function]):
    return_type: ResolvedExpression | None
    generic_parameters: list["ResolvedGenericParameter"] | None
    positional_parameters: list["ResolvedParameter"]
    named_parameters: list["ResolvedParameter"]
    variadic_positional_parameter: "ResolvedParameter | None"
    variadic_named_parameter: "ResolvedParameter | None"
    body: ResolvedFunctionBody

    def _init(self):
        self.return_type = None
        self.generic_parameters = None
        self.positional_parameters = []
        self.named_parameters = []
        self.variadic_positional_parameter = None
        self.variadic_named_parameter = None
        self.body = ResolvedFunctionBody(self)

    @property
    def name(self):
        if self.node.name is None:
            return None
        if isinstance(self.node.name, Identifier):
            return self.node.name.name
        if isinstance(self.node.name, Literal):
            return self.node.name.token_info.literal.value
        raise RuntimeError


class ResolvedFunctionCall(ResolvedExpression[FunctionCall]):
    callable: "ResolvedExpression | None"
    arguments: list[ResolvedExpression] | None
    keyword_arguments: dict[str, ResolvedExpression] | None

    @property
    def operator(self):
        return self.node.operator


class ResolvedGenericParameter(ResolvedExpression, ResolvedNode[Identifier]):
    @property
    def name(self):
        return self.node.name


class ResolvedIf(ResolvedExpression[If]):
    condition: ResolvedExpression
    if_body: ResolvedNode
    else_body: ResolvedNode


class ResolvedImport(ResolvedStatement[Import]):
    class ImportedName(ResolvedExpression[Identifier | Alias]):
        name: str
        origin: "ResolvedImport"

        def __init__(self, node: Identifier | Alias, name: str, origin: "ResolvedImport"):
            super().__init__(node)
            self.name = name
            self.origin = origin

    source: ResolvedExpression | None
    imported_names: list[ImportedName]

    def _init(self):
        self.source = None
        self.imported_names = []

    def import_name(self, node: Identifier | Alias, name: str):
        return (self.imported_names.append(imported := self.ImportedName(node, name, self)), imported)[1]


class ResolvedMemberAccess(ResolvedExpression[MemberAccess]):
    object: ResolvedExpression

    @property
    def member_name(self):
        return self.node.member.name


class ResolvedModule(ResolvedNode[Module]):
    items: list[ResolvedNode]

    def _init(self):
        self.items = []

    @property
    def name(self):
        return self.node.name.name if self.node.name else None


class ResolvedObject(ResolvedExpression[None], Generic[_T]):
    object: "ObjectProtocol"

    def __init__(self, obj: "ObjectProtocol"):
        super().__init__(None)
        self.object = obj


class ResolvedOverloadGroup(ResolvedExpression[None]):
    def __init__(self, name: str, parent: "ResolvedFunctionGroup | None"):
        super().__init__(None)
        self.name = name
        self.parent = parent
        self.overloads = []

    name: str
    parent: "ResolvedOverloadGroup | None"
    overloads: list[ResolvedFunction]


class ResolvedParameter(ResolvedNode[Parameter]):
    type: ResolvedExpression | None
    initializer: ResolvedExpression | None

    def _init(self):
        self.type = None
        self.initializer = None

    @property
    def name(self):
        return self.node.name.name


class ResolvedReturn(ResolvedStatement[Return]):
    expression: ResolvedExpression


class ResolvedUnary(ResolvedExpression[Unary]):
    ...


class ResolvedVar(ResolvedStatement[Var]):
    type: ResolvedExpression | None
    initializer: ResolvedExpression | None

    def _init(self):
        self.type = None
        self.initializer = None

    @property
    def name(self):
        return self.node.name.name.name


class ResolvedWhile(ResolvedStatement[While]):
    condition: ResolvedExpression
    while_body: ResolvedNode
    else_body: ResolvedNode | None

    @property
    def name(self):
        return self.node.name.name if self.node.name else None

# endregion
