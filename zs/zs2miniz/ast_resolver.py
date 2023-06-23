from contextlib import contextmanager
from functools import singledispatchmethod
from typing import TypeVar, Callable

from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.processing import StatefulProcessor, State
from zs.zs2miniz.errors import ZSharpError, NameAlreadyBoundError, NameNotFoundError
from zs.zs2miniz.lib import CompilationContext

import zs.ast.node_lib as nodes
import zs.ast.resolved as resolved


_SENTINEL = object()
_T = TypeVar("_T")


class Scope:
    _parent: "Scope | None"
    _items: dict[str, Node]

    def __init__(self, parent: "Scope | None" = None, **items):
        self._parent = parent
        self._items = items

    @property
    def parent(self):
        return self._parent

    def _assert_name_unused(self, name: str):
        if name in self._items:
            raise ValueError(f"Name {name} is already bound to an object {self._items[name]} in scope {self}")

    def create_name(self, name: str, value: Node):
        self._assert_name_unused(name)
        self._items[name] = value

    def delete_name(self, name: str, *, recursive_lookup: bool = False, must_exist: bool = True):
        if name in self._items:
            del self._items[name]
            return
        if recursive_lookup:
            if self.parent is not None:
                return self.parent.delete_name(name, recursive_lookup=recursive_lookup, must_exist=True)
            elif not must_exist:
                return
        if must_exist:
            raise NameNotFoundError(f"Could not delete name \'{name}\'.")

    def lookup_name(self, name: str, *, recursive_lookup: bool = True, default: _T = _SENTINEL) -> Node | _T:
        if name in self._items:
            return self._items[name]
        if recursive_lookup and self.parent is not None:
            return self.parent.lookup_name(name, recursive_lookup=recursive_lookup)
        if default is _SENTINEL:
            raise NameNotFoundError(f"Could not resolve name \'{name}\'.")
        return default


class IResolver:
    def resolve(self, node: Node) -> resolved.ResolvedNode:
        raise NotImplementedError


class ASTResolver(StatefulProcessor, IResolver):
    """
    Base class for all contextual processors
    """

    _context: CompilationContext
    _nodes: list[Node]
    _scope: Scope
    _built: set[Node]

    _scope_cache: dict[Node, Scope]
    _nodes_cache: dict[Node, resolved.ResolvedNode]

    def __init__(self, *, state: State | None = None, context: CompilationContext):
        super().__init__(state or State())
        self._context = context
        self._nodes = []
        self._scope = Scope(context.global_scope)
        self._built = set()

        self._scope_cache = {}
        self._nodes_cache = {}

    @property
    def context(self):
        return self._context

    @property
    def current_scope(self):
        return self._scope

    @contextmanager
    def scope(self, parent: Scope | Node | None = _SENTINEL, **items):
        if isinstance(parent, Node) and parent in self._scope_cache:
            scope = self._scope_cache[parent]
        else:
            scope = Scope(parent if parent is not _SENTINEL else self.current_scope, **items)
        scope, self._scope = self._scope, scope
        try:
            yield self._scope
        finally:
            self._scope = scope

    def add_node(self, node: Node):
        self._nodes.append(node)

    def resolve(self, node: Node | _T | None = _SENTINEL) -> \
            list[resolved.ResolvedNode] | \
            resolved.ResolvedNode[_T] | \
            resolved.ResolvedNode | \
            resolved.ResolvedExpression | \
            resolved.ResolvedParameter | \
            None:
        if node is not _SENTINEL:
            if node is None:
                return None
            if node in self._nodes_cache:
                if node not in self._built:
                    # if self._resolver not in (self, None):
                    #     self._resolver.resolve(node)
                    # else:
                    self._resolve(node)
                    self._built.add(node)
                return self._nodes_cache[node]
            # if self._resolver not in (self, None):
            #     return self._resolver.resolve(node)
            return self._resolve(node)

        for node in self._nodes:
            """
            Registering nodes.
            
            This associates nodes with the scope they create (e.g. a class node to the scope of the class)
            and registers named nodes in the scope they are defined in (e.g. a field is registered in the scope associated with its declaring class)
            """
            self._register(node)

        result = []
        for node in self._nodes:
            try:
                result.append(self._resolve(node))
            except ZSharpError as e:
                self.state.error(f"{type(e): {', '.join(e.args)}}", node)
                raise e from None
        self._nodes.clear()

        return result

    @singledispatchmethod
    def _register(self, node: Node):
        raise NotImplementedError(f"Can't register node of type \'{type(node)}\' because it is not implemented yet")

    _reg = _register.register

    @_reg
    def _(self, node: nodes.Class):
        if node.name:
            self.current_scope.create_name(node.name.name, node)

        self._nodes_cache[node] = resolved.ResolvedClass(node, [], [])

        with self.scope() as scope:
            self._scope_cache[node] = scope

            for item in node.items:
                self._register(item)

    @_reg
    def _(self, node: nodes.Var):
        self.current_scope.create_name(node.name.name.name, node)

    @_reg
    def _(self, node: nodes.Parameter):
        self.current_scope.create_name(node.name.name, node)

        self._nodes_cache[node] = resolved.ResolvedParameter(node, self.resolve(node.type), self.resolve(node.initializer))

    @_reg
    def _(self, node: nodes.Function):
        self._nodes_cache[node] = resolved.ResolvedFunction(node, None, [], [], None, None, None)

        with self.scope() as parameter_scope:
            for parameter in node.positional_parameters:
                self._register(parameter)
            for parameter in node.named_parameters:
                self._register(parameter)
            if node.variadic_positional_parameter:
                self._register(node.variadic_positional_parameter)
            if node.variadic_named_parameter:
                self._register(node.variadic_named_parameter)

            with self.scope(parameter_scope) as body_scope:
                self._scope_cache[node] = body_scope

                if node.name:
                    self.current_scope.create_name(node.name.name, node)

    @_reg
    def _(self, node: nodes.Module):
        if node.name:
            self.current_scope.create_name(node.name.name, node)

        self._nodes_cache[node] = resolved.ResolvedModule(node, [])

        with self.scope() as scope:
            self._scope_cache[node] = scope

            for item in node.items:
                self._register(item)

    @singledispatchmethod
    def _resolve(self, node: Node):
        raise NotImplementedError(f"Can't resolve node of type {type(node)} because it is not implemented yet")

    _res = _resolve.register

    @_res
    def _(self, node: nodes.Class):
        result = self._nodes_cache[node]
        assert isinstance(result, resolved.ResolvedClass)
        result.bases = list(map(self.resolve, node.bases))
        with self.scope(node):
            for item in node.items:
                result.items.append(self.resolve(item))
        return result

    @_res
    def _(self, node: nodes.Var):
        result = resolved.ResolvedVar(node, self.resolve(node.name.type), self.resolve(node.initializer))

        return result

    @_res
    def _(self, node: nodes.Function):
        result = self._nodes_cache[node]
        assert isinstance(result, resolved.ResolvedFunction)

        with self.scope(node) as body_scope:
            with self.scope(body_scope.parent):
                for parameter in node.positional_parameters:
                    result.positional_parameters.append(self.resolve(parameter))
                for parameter in node.named_parameters:
                    result.named_parameters.append(self.resolve(parameter))
                result.variadic_positional_parameter = self.resolve(node.variadic_positional_parameter)
                result.variadic_named_parameter = self.resolve(node.variadic_named_parameter)

                result.return_type = self.resolve(node.return_type)

            if node.body is not None:
                result.body = []
                for item in node.body:
                    result.body.append(self.resolve(item))

        return result

    @_res
    def _(self, node: nodes.Parameter):
        return self._nodes_cache[node]

    @_res
    def _(self, node: nodes.Module):
        result = self._nodes_cache[node]
        assert isinstance(result, resolved.ResolvedModule)
        with self.scope(node):
            for item in node.items:
                result.items.append(self.resolve(item))
        return result

    @_res
    def _(self, node: nodes.Expression):
        raise NotImplementedError(f"Could not resolve expression of type '{type(node)}' because it is not implemented yet")

    @_res
    def _(self, node: nodes.Identifier):
        node = self.current_scope.lookup_name(node.name)
        if not isinstance(node, Node):
            if not isinstance(node, ObjectProtocol):
                raise TypeError(f"Object which is not a node must be a valid Z# object, but was '{type(node)}'")
            return resolved.ResolvedObject(node)
        return self._nodes_cache[node]

    @_res
    def _(self, node: nodes.Binary):
        left = self._resolve(node.left)
        right = self._resolve(node.right)
        return resolved.ResolvedBinary(node, left, right)

    @_res
    def _(self, node: nodes.FunctionCall):
        fn = self.resolve(node.callable)
        fact: Callable[
            [nodes.FunctionCall, resolved.ResolvedFunction | resolved.ResolvedClass, list[resolved.ResolvedExpression], dict[str, resolved.ResolvedExpression]]
            , resolved.ResolvedFunctionCall | resolved.ResolvedClassCall]
        if isinstance(fn, resolved.ResolvedFunction):
            fact = resolved.ResolvedFunctionCall
        elif isinstance(fn, resolved.ResolvedClass):
            fact = resolved.ResolvedClassCall
        else:
            raise TypeError
        return fact(
            node,
            fn,
            [
                self.resolve(arg) for arg in node.arguments
            ],
            {
                name: self.resolve(arg) for name, arg in node.keyword_arguments.items()
            }
        )

    @_res
    def _(self, node: nodes.Return):
        expr = self.resolve(node.expression)
        return resolved.ResolvedReturn(expr)
