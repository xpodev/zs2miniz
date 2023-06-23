from dataclasses import dataclass
from typing import Generic, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.ast.node_lib import Expression, Binary, ExpressionStatement, Unary, FunctionCall, Class, Module, Var, Function, Parameter

_T = TypeVar("_T", bound=Node)


_cfg = {
    "slots": True,
    "eq": False
}


@dataclass(**_cfg)
class ResolvedNode(Generic[_T]):
    node: _T

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return id(self) == id(other)


class ResolvedObject(ResolvedNode[None], Generic[_T]):
    object: "ObjectProtocol"

    def __init__(self, obj: "ObjectProtocol"):
        super().__init__(None)
        self.object = obj


class ResolvedExpression(ResolvedNode[Expression[_T]], Generic[_T]):
    ...


@dataclass(**_cfg)
class ResolvedBinary(ResolvedExpression[Binary]):
    left: ResolvedExpression
    right: ResolvedExpression

    @property
    def operator(self):
        return self.node.token_info.operator.value


class ResolvedExpressionStatement(ResolvedNode[ExpressionStatement]):
    expression: ResolvedExpression


class ResolvedUnary(ResolvedExpression[Unary]):
    ...


@dataclass(**_cfg)
class ResolvedClassCall(ResolvedExpression[FunctionCall]):
    callable: "ResolvedClass"
    arguments: list[ResolvedExpression]
    keyword_arguments: dict[str, ResolvedExpression]


@dataclass(**_cfg)
class ResolvedFunctionCall(ResolvedExpression[FunctionCall]):
    callable: "ResolvedFunction"
    arguments: list[ResolvedExpression]
    keyword_arguments: dict[str, ResolvedExpression]

    @property
    def operator(self):
        return self.node.operator


@dataclass(**_cfg)
class ResolvedClass(ResolvedNode[Class]):
    bases: list[ResolvedExpression]

    items: list[ResolvedNode]

    @property
    def name(self):
        return self.node.name.name if self.node.name is not None else None

    def __str__(self):
        return f"ResolvedClass {self.name or '{Anonymous}'}"


@dataclass(**_cfg)
class ResolvedParameter(ResolvedNode[Parameter]):
    type: ResolvedExpression | None
    initializer: ResolvedExpression | None

    @property
    def name(self):
        return self.node.name.name


@dataclass(**_cfg)
class ResolvedFunction(ResolvedNode[Function]):
    return_type: ResolvedExpression | None
    positional_parameters: list[ResolvedParameter]
    named_parameters: list[ResolvedParameter]
    variadic_positional_parameter: ResolvedParameter | None
    variadic_named_parameter: ResolvedParameter | None
    body: list[ResolvedNode] | None

    @property
    def name(self):
        return self.node.name.name if self.node.name is not None else None


@dataclass(**_cfg)
class ResolvedFunctionGroup(ResolvedNode):
    overloads: list[ResolvedFunction]


@dataclass(**_cfg)
class ResolvedVar(ResolvedNode[Var]):
    type: ResolvedExpression
    initializer: ResolvedExpression | None

    @property
    def name(self):
        return self.node.name.name.name


@dataclass(**_cfg)
class ResolvedModule(ResolvedNode[Module]):
    items: list[ResolvedNode]

    @property
    def name(self):
        return self.node.name.name if self.node.name else None


@dataclass(**_cfg)
class ResolvedReturn:
    expression: ResolvedExpression
