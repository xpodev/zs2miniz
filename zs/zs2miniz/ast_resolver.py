from contextlib import contextmanager
from functools import singledispatchmethod
from typing import TypeVar, overload

from miniz.interfaces.base import IMiniZObject
from miniz.type_system import ObjectProtocol, Null, Boolean, Unit, String
from zs.ast.node import Node
from zs.processing import StatefulProcessor, State
from zs.text.token import TokenType
from zs.zs2miniz.lib import Scope

import zs.ast.node_lib as nodes
import zs.ast.resolved as resolved

_SENTINEL = object()
_T = TypeVar("_T")


class ResolverContext:
    _scope: Scope[resolved.ResolvedNode]
    _mapping: dict[resolved.ResolvedNode, Scope]
    _injected_nodes: list[resolved.ResolvedNode]

    def __init__(self, global_scope: Scope | None):
        self._scope = Scope(global_scope)
        self._mapping = {}
        self._injected_nodes = []

    @property
    def current_scope(self):
        return self._scope

    @property
    def injected_nodes(self):
        return self._injected_nodes

    @contextmanager
    def scope(self, scope: Scope | None = _SENTINEL, **items):
        if scope is _SENTINEL:
            scope = Scope(self.current_scope, **items)
        else:
            assert not items
        scope, self._scope = self._scope, scope
        try:
            yield self._scope
        finally:
            self._scope = scope

    @contextmanager
    def create_scope(self, node: resolved.ResolvedNode):
        with self.scope() as scope:
            self._mapping[node] = scope
            yield scope

    @contextmanager
    def use_scope(self, node: resolved.ResolvedNode):
        with self.scope(self._mapping[node]) as scope:
            yield scope

    def inject(self, node: resolved.ResolvedNode):
        self._injected_nodes.append(node)


class _SubProcessor(StatefulProcessor):
    _processor: "NodeProcessor"

    def __init__(self, processor: "NodeProcessor"):
        super().__init__(processor.state)
        self._processor = processor

    @property
    def processor(self):
        return self._processor

    @property
    def context(self):
        return self.processor.context


class NodeRegistry(_SubProcessor):
    def register(self, node: Node):
        return self._register(node)

    @singledispatchmethod
    def _register(self, node: Node):
        raise NotImplementedError(type(node))

    _reg = _register.register

    @_reg
    def _(self, node: nodes.Class):
        result = resolved.ResolvedClass(node)

        if result.name:
            self.context.current_scope.create_name(result.name, result)

        for base in node.bases:
            result.bases.append(self.register(base))

        with self.context.create_scope(result):
            for item in node.items:
                result.items.append(self.register(item))

        return result

    @_reg
    def _(self, node: nodes.Expression):
        return resolved.ResolvedExpression(node)

    @_reg
    def _(self, node: nodes.ExpressionStatement):
        self.register(node.expression)

        return resolved.ResolvedExpressionStatement(node)

    @_reg
    def _(self, node: nodes.Function):
        result = resolved.ResolvedFunction(node)

        if result.name:
            group = self.context.current_scope.lookup_name(result.name, recursive_lookup=False, default=None)

            if group is None:
                group = resolved.ResolvedOverloadGroup(result.name, None)
                with self.context.create_scope(group):
                    self.processor.inject(group)
                self.context.current_scope.create_name(group.name, group)
            elif not isinstance(group, resolved.ResolvedOverloadGroup):
                return self.state.error(f"Name \'{result.name}\' is already bound to an object \'{group}\'")
            group.overloads.append(result)

        with self.context.create_scope(result):
            for parameter in node.positional_parameters:
                result.positional_parameters.append(self.register(parameter))

            for parameter in node.named_parameters:
                result.named_parameters.append(self.register(parameter))

            if node.variadic_positional_parameter is not None:
                result.variadic_positional_parameter = self.register(node.variadic_positional_parameter)

            if node.variadic_named_parameter is not None:
                result.variadic_named_parameter = self.register(node.variadic_named_parameter)

            if node.return_type is not None:
                result.return_type = self.register(node.return_type)

            if node.body is not None:
                with self.context.create_scope(result):
                    result.body.instructions = list(filter(bool, map(self.register, node.body)))

        return result

    @_reg
    def _(self, node: nodes.FunctionCall):
        result = resolved.ResolvedFunctionCall(node)

        result.callable = self.register(node.callable)

        result.arguments = list(filter(bool, map(self.register, node.arguments)))
        result.keyword_arguments = {
            name: self.register(arg) for name, arg in node.keyword_arguments.items()
        }

        return result

    @_reg
    def _(self, node: nodes.Identifier):
        return node

    @_reg
    def _(self, node: nodes.Import):
        result = resolved.ResolvedImport(node)

        result.source = self.register(node.source)

        match node.name:
            case None:
                ...
            case nodes.Alias():
                ...
            case nodes.Identifier():
                ...
            case list():
                for node in node.name:
                    match node:
                        case nodes.Identifier():
                            origin = name = node.name
                        case nodes.Alias():
                            assert isinstance(node.expression, nodes.Identifier)
                            origin = node.expression.name
                            name = node.name.name
                        case _:
                            raise TypeError
                    self.context.current_scope.refer_name(name, result.import_name(node, origin))
            case _:
                raise TypeError

        return result

    @_reg
    def _(self, node: nodes.Literal):
        match node.token_info.literal.type:
            case TokenType.Identifier:
                match node.token_info.literal.value:
                    case "null":
                        value = Null.NullInstance
                    case "true":
                        value = Boolean.TrueInstance
                    case "false":
                        value = Boolean.FalseInstance
                    case _:
                        raise NotImplementedError
            case TokenType.String:
                value = String.create_from(node.token_info.literal.value)
            case TokenType.Unit:
                value = Unit.UnitInstance
            case _:
                raise TypeError(f"Token type \'{node.token_info.literal.type}\' is not yet implemented")
        return resolved.ResolvedObject(value)

    @_reg
    def _(self, node: nodes.MemberAccess):
        result = resolved.ResolvedMemberAccess(node)

        result.object = self.register(node.object)

        return result

    @_reg
    def _(self, node: nodes.Module):
        result = resolved.ResolvedModule(node)

        if result.name:
            self.context.current_scope.create_name(result.name, result)

        with self.context.create_scope(result):
            result.items = list(filter(bool, map(self.register, node.items)))

        return result

    @_reg
    def _(self, node: nodes.Parameter):
        result = resolved.ResolvedParameter(node)

        self.context.current_scope.create_name(result.name, result)

        if node.type is not None:
            result.type = self.register(node.type)

        if node.initializer is not None:
            result.initializer = self.register(node.initializer)

        return result

    @_reg
    def _(self, node: nodes.Return):
        result = resolved.ResolvedReturn(node)

        result.expression = self.register(node.expression) if node.expression else None

        return result

    @_reg
    def _(self, node: nodes.Var):
        result = resolved.ResolvedVar(node)

        if node.name.type is not None:
            result.type = self.register(node.name.type)

        if node.initializer is not None:
            result.initializer = self.register(node.initializer)

        self.context.current_scope.create_name(result.name, result)

        return result


class NodeResolver(_SubProcessor):
    _resolved: set[resolved.ResolvedNode]

    def __init__(self, processor: "NodeProcessor"):
        super().__init__(processor)
        self._resolved = set()

    @overload
    def resolve(self, node: Node) -> resolved.ResolvedNode:
        ...

    @overload
    def resolve(self, node: resolved.ResolvedNode):
        ...

    def resolve(self, node: Node | resolved.ResolvedNode):
        if node is None:
            return None
        if node in self._resolved:
            return node
        self._resolved.add(node)
        return self._resolve(node) or node

    @singledispatchmethod
    def _resolve(self, node: resolved.ResolvedNode):
        raise NotImplementedError(type(node))

    _res = _resolve.register

    # region Resolved Nodes

    @_res
    def _(self, node: resolved.ResolvedClass):
        with self.context.use_scope(node):
            node.bases = list(map(self.resolve, node.bases))
            node.items = list(map(self.resolve, node.items))

    @_res
    def _(self, node: resolved.ResolvedFunction):
        with self.context.use_scope(node):
            node.positional_parameters = list(map(self.resolve, node.positional_parameters))
            node.named_parameters = list(map(self.resolve, node.named_parameters))
            node.variadic_positional_parameter = self.resolve(node.variadic_positional_parameter)
            node.variadic_named_parameter = self.resolve(node.variadic_named_parameter)
            node.return_type = self.resolve(node.return_type)
            node.body.instructions = list(map(self.resolve, node.body.instructions)) if node.body.instructions is not None else None

    @_res
    def _(self, node: resolved.ResolvedFunctionCall):
        node.callable = self.resolve(node.callable)
        node.arguments = list(map(self.resolve, node.arguments))
        node.keyword_arguments = dict(zip(node.keyword_arguments.keys(), list(map(self.resolve, node.keyword_arguments.values()))))

    @_res
    def _(self, node: resolved.ResolvedImport):
        node.source = self.resolve(node.source)

    @_res
    def _(self, node: resolved.ResolvedMemberAccess):
        node.object = self.resolve(node.object)

    @_res
    def _(self, node: resolved.ResolvedModule):
        with self.context.use_scope(node):
            node.items = list(map(self.resolve, node.items))

    @_res
    def _(self, node: resolved.ResolvedObject):
        ...

    @_res
    def _(self, node: resolved.ResolvedOverloadGroup):
        with self.context.use_scope(node):
            with self.context.scope(self.context.current_scope.parent.parent):
                node.parent = self.context.current_scope.lookup_name(node.name, default=None)
                node.overloads = list(map(self.resolve, node.overloads))

    @_res
    def _(self, node: resolved.ResolvedParameter):
        node.type = self.resolve(node.type)
        node.initializer = self.resolve(node.initializer)

    @_res
    def _(self, node: resolved.ResolvedReturn):
        node.expression = self.resolve(node.expression)

    @_res
    def _(self, node: resolved.ResolvedVar):
        node.type = self.resolve(node.type)
        node.initializer = self.resolve(node.initializer)

    # endregion Resolved Nodes

    @_res
    def _(self, node: nodes.Identifier):
        value = self.context.current_scope.lookup_name(node.name)
        if isinstance(value, (ObjectProtocol, IMiniZObject)):
            value = resolved.ResolvedObject(value)
        return value


class NodeProcessor(StatefulProcessor):
    _nodes: list[Node]

    _context: ResolverContext

    _registry: NodeRegistry
    _resolver: NodeResolver

    def __init__(self, state: State, global_scope: Scope[ObjectProtocol]):
        super().__init__(state)
        self._nodes = []
        self._injected = []

        self._context = ResolverContext(global_scope)

        self._registry = NodeRegistry(self)
        self._resolver = NodeResolver(self)

    @property
    def context(self):
        return self._context

    def add_node(self, node: Node):
        self._nodes.append(node)

    def inject(self, node: resolved.ResolvedNode):
        self.context.inject(node)

    def resolve(self) -> list[resolved.ResolvedNode]:
        result = []

        for node in self._nodes:
            result.append(self._registry.register(node))

        # for node in self.context.current_scope.items:
        #     self._resolver.resolve(node)

        for node in result:
            self._resolver.resolve(node)

        for node in self.context.injected_nodes:
            self._resolver.resolve(node)

        self._nodes.clear()

        return result
