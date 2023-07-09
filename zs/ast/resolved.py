from typing import Generic, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.ast.node_lib import Expression, Binary, ExpressionStatement, Unary, FunctionCall, Class, Module, Var, Function, Parameter, Import, Alias, Identifier, MemberAccess

_T = TypeVar("_T", bound=Node)


class ResolvedNode(Generic[_T]):
    node: _T

    def __init__(self, node: _T | None):
        self.node = node
        self._init()

    def _init(self):
        ...


class ResolvedExpression(ResolvedNode[Expression[_T]], Generic[_T]):
    ...


# region Concrete


class Evaluate(ResolvedNode[_T], Generic[_T]):
    value: ResolvedExpression[_T] | ResolvedNode[_T]

    def __init__(self, node: ResolvedExpression[_T] | ResolvedNode[_T]):
        super().__init__(node.node)
        self.value = node


class ResolvedBinary(ResolvedExpression[Binary]):
    left: ResolvedExpression
    right: ResolvedExpression

    @property
    def operator(self):
        return self.node.token_info.operator.value


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


class ResolvedClassCall(ResolvedExpression[FunctionCall]):
    callable: "ResolvedClass"
    arguments: list[ResolvedExpression]
    keyword_arguments: dict[str, ResolvedExpression]


class ResolvedExpressionStatement(ResolvedNode[ExpressionStatement]):
    expression: ResolvedExpression


class ResolvedFunction(ResolvedNode[Function]):
    return_type: ResolvedExpression | None
    positional_parameters: list["ResolvedParameter"]
    named_parameters: list["ResolvedParameter"]
    variadic_positional_parameter: "ResolvedParameter | None"
    variadic_named_parameter: "ResolvedParameter | None"
    body: list[ResolvedNode] | None

    def _init(self):
        self.return_type = None
        self.positional_parameters = []
        self.named_parameters = []
        self.variadic_positional_parameter = None
        self.variadic_named_parameter = None
        self.body = None

    @property
    def name(self):
        return self.node.name.name if self.node.name is not None else None


class ResolvedFunctionCall(ResolvedExpression[FunctionCall]):
    callable: "ResolvedFunction | None"
    arguments: list[ResolvedExpression] | None
    keyword_arguments: dict[str, ResolvedExpression] | None

    @property
    def operator(self):
        return self.node.operator


class ResolvedImport(ResolvedNode[Import]):
    class ImportedName(ResolvedExpression[Identifier | Alias]):
        name: str
        origin: "ResolvedImport"

        def __init__(self, node: Identifier | Alias, name: str, origin: "ResolvedImport"):
            super().__init__(node)
            self.name = name
            self.origin = origin

    source: Evaluate[ResolvedExpression] | ResolvedExpression | None
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


class ResolvedOverloadGroup(ResolvedNode[None]):
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


class ResolvedReturn(ResolvedNode):
    expression: ResolvedExpression


class ResolvedUnary(ResolvedExpression[Unary]):
    ...


class ResolvedVar(ResolvedNode[Var]):
    type: ResolvedExpression | None
    initializer: ResolvedExpression | None

    def _init(self):
        self.type = None
        self.initializer = None

    @property
    def name(self):
        return self.node.name.name.name
