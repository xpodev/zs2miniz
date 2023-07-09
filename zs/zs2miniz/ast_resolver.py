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

    def __init__(self, global_scope: Scope | None):
        self._scope = Scope(global_scope)
        self._mapping = {}

    @property
    def current_scope(self):
        return self._scope

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


# class NodeExecutor(StatefulProcessor):
#     _context: ResolverContext
#     _resolver: "ASTResolver"
#     _runtime: Interpreter
#
#     def __init__(self, resolver: "ASTResolver", context: ResolverContext):
#         super().__init__(resolver.state)
#         self._context = context
#         self._resolver = resolver
#         self._runtime = Interpreter()
#
#     @property
#     def context(self):
#         return self._context
#
#     @property
#     def resolver(self):
#         return self._resolver
#
#     @property
#     def runtime(self):
#         return self._runtime
#
#     def execute(self, node: nodes.Node, **kwargs):
#         return self._execute(node, **kwargs)
#
#     @singledispatchmethod
#     def _execute(self, node: nodes.Node, **kwargs):
#         raise NotImplementedError
#
#     _exe = _execute.register
#
#     @_exe
#     def _(self, node: resolved.ResolvedObject):
#         return node.object
#
#     @_exe
#     def _(self, node: nodes.Var):
#         if node.name.type:
#             var_type = self.execute(node.name.type)
#         else:
#             var_type = None
#         if node.initializer is None and var_type is Any:
#             value = Any.UndefinedInstance
#         elif node.initializer is not None:
#             value = self.execute(node.initializer)
#             var_type = var_type.runtime_type
#         else:
#             raise NotImplementedError(f"Type defaults are not yet implemented")
#         name = node.name.name.name
#         # self.context.current_scope.create_name(name, Value(name, var_type, value))
#         self.context.current_scope.create_name(name, resolved.ResolvedObject(value))
#
#     @_exe
#     def _(self, node: nodes.Literal):
#         match node.token_info.literal.type:
#             case TokenType.Identifier:
#                 match node.token_info.literal.value:
#                     case "null":
#                         return Null.NullInstance
#                     case "true":
#                         return Boolean.TrueInstance
#                     case "false":
#                         return Boolean.FalseInstance
#             case TokenType.String:
#                 return String.create_from(node.token_info.literal.value)
#             case TokenType.Unit:
#                 return Unit.UnitInstance
#             case _:
#                 raise TypeError(f"Token type \'{node.token_info.literal.type}\' is not yet implemented")
#
#     @_exe
#     def _(self, node: nodes.Identifier):
#         value = self.context.current_scope.lookup_name(node.name)
#         if isinstance(value, resolved.ResolvedObject):
#             value = value.object
#         if not isinstance(value, (ObjectProtocol, IMiniZObject)):
#             raise TypeError(f"Can only refer to built objects at CT execution")
#         return value
#
#     @_exe
#     def _(self, node: nodes.FunctionCall):
#         target = self.execute(node.callable)
#         args = list(map(self.execute, node.arguments))
#         kwargs = {
#             name: self.execute(arg) for name, arg in node.keyword_arguments.items()
#         }
#
#         if isinstance(target, OverloadGroup):
#             arg_types = [arg.runtime_type for arg in args]
#             kwarg_types = [(name, arg.runtime_type) for name, arg in kwargs.items()]
#
#             targets = target.get_match(arg_types, kwarg_types, strict=True)
#
#             if not len(targets):
#                 targets = target.get_match(arg_types, kwarg_types)
#
#             if len(targets) != 1:
#                 return self.state.error(f"Can't find a suitable overload for \'{target.name}\'", node)
#
#             target = targets[0]
#
#         return self.runtime.run([vm.Call(target)], args).pop() if target.signature.return_type is not Void else None


# class ASTResolver(StatefulProcessor):
#     """
#     Base class for all contextual processors
#     """
#
#     _context: CompilationContext
#     _nodes: list[Node]
#     _inject: list[tuple[resolved.ResolvedNode, Scope]]
#     _scope: Scope
#     _built: set[Node]
#
#     _scope_cache: dict[Node, Scope]
#     _nodes_cache: dict[Node, resolved.ResolvedNode]
#
#     _resolver_context: ResolverContext
#     _executor: NodeExecutor
#
#     def __init__(self, *, state: State | None = None, context: CompilationContext):
#         super().__init__(state or State())
#         self._context = context
#         self._nodes = []
#         self._inject = []
#         self._built = set()
#
#         self._scope_cache = {}
#         self._nodes_cache = {}
#
#         self._resolver_context = ResolverContext(context.scope)
#         self._executor = NodeExecutor(self, self._resolver_context)
#
#     @property
#     def context(self):
#         return self._context
#
#     @property
#     def executor(self):
#         return self._executor
#
#     @property
#     def current_scope(self):
#         return self._resolver_context.current_scope
#
#     @contextmanager
#     def scope(self, parent: Scope | Node | None = _SENTINEL, **items):
#         if isinstance(parent, Node) and parent in self._scope_cache:
#             scope = self._scope_cache[parent]
#         else:
#             scope = parent
#         with self._resolver_context.scope(scope, **items) as scope:
#             yield scope
#
#     def add_node(self, node: Node):
#         self._nodes.append(node)
#
#     def resolve(self, node: Node | _T | None = _SENTINEL) -> \
#             list[resolved.ResolvedNode] | \
#             resolved.ResolvedNode[_T] | \
#             resolved.ResolvedNode | \
#             resolved.ResolvedExpression | \
#             resolved.ResolvedParameter | \
#             None:
#         if node is not _SENTINEL:
#             if node is None:
#                 return None
#             if node in self._nodes_cache:
#                 if node not in self._built:
#                     # if self._resolver not in (self, None):
#                     #     self._resolver.resolve(node)
#                     # else:
#                     self._resolve(node)
#                     self._built.add(node)
#                 return self._nodes_cache[node]
#             # if self._resolver not in (self, None):
#             #     return self._resolver.resolve(node)
#             return self._resolve(node)
#
#         self.run()
#
#         for node in self._nodes:
#             """
#             Registering nodes.
#
#             This associates nodes with the scope they create (e.g. a class node to the scope of the class)
#             and registers named nodes in the scope they are defined in (e.g. a field is registered in the scope associated with its declaring class)
#             """
#             self._register(node)
#
#         result = set()
#         for node in self._nodes:
#             try:
#                 self._resolve(node)
#             except ZSharpError as e:
#                 self.state.error(f"{type(e)}: {', '.join(e.args)}", node)
#                 raise e from None
#         self._nodes.clear()
#
#         for node, scope in self._inject:
#             try:
#                 self._resolve(node, scope)
#             except ZSharpError as e:
#                 self.state.error(f"{type(e)}: {', '.join(e.args)}", node)
#                 raise e from None
#         self._inject.clear()
#
#         # return list(filter(bool, result))
#         return [self._nodes_cache[node] if isinstance(node, Node) else node for node in self.current_scope.items]
#
#     @singledispatchmethod
#     def _register(self, node: Node):
#         raise NotImplementedError(f"Can't register node of type \'{type(node)}\' because it is not implemented yet")
#
#     _reg = _register.register
#
#     @_reg
#     def _(self, node: nodes.Class):
#         if node.name:
#             self.current_scope.create_name(node.name.name, node)
#
#         self._nodes_cache[node] = resolved.ResolvedClass(node, [], [])
#
#         with self.scope() as scope:
#             self._scope_cache[node] = scope
#
#             for item in node.items:
#                 self._register(item)
#
#     @_reg
#     def _(self, node: nodes.Var):
#         self.current_scope.create_name(node.name.name.name, node)
#
#     @_reg
#     def _(self, node: nodes.Parameter):
#         self.current_scope.create_name(node.name.name, node)
#
#         self._nodes_cache[node] = resolved.ResolvedParameter(node, self.resolve(node.type), self.resolve(node.initializer))
#
#     @_reg
#     def _(self, node: nodes.Function):
#         fn = self._nodes_cache[node] = resolved.ResolvedFunction(node, None, [], [], None, None, None)
#
#         if node.name:
#             group = self.current_scope.lookup_name(node.name.name, recursive_lookup=False, default=None)
#             if group is None:
#                 group = resolved.ResolvedOverloadGroup(None, node.name.name, None, [])
#                 self.current_scope.create_name(node.name.name, group)
#                 self._inject.append((group, self.current_scope))
#             if not isinstance(group, resolved.ResolvedOverloadGroup):
#                 raise NameAlreadyBoundError(node.name.name)
#             group.overloads.append(fn)
#
#         with self.scope() as parameter_scope:
#             for parameter in node.positional_parameters:
#                 self._register(parameter)
#             for parameter in node.named_parameters:
#                 self._register(parameter)
#             if node.variadic_positional_parameter:
#                 self._register(node.variadic_positional_parameter)
#             if node.variadic_named_parameter:
#                 self._register(node.variadic_named_parameter)
#
#             with self.scope(parameter_scope) as body_scope:
#                 self._scope_cache[node] = body_scope
#
#                 # if node.name:
#                 #     self.current_scope.create_name(node.name.name, node)
#
#     @_reg
#     def _(self, node: nodes.Module):
#         if node.name:
#             self.current_scope.create_name(node.name.name, node)
#
#         self._nodes_cache[node] = resolved.ResolvedModule(node, [])
#
#         with self.scope() as scope:
#             self._scope_cache[node] = scope
#
#             for item in node.items:
#                 self._register(item)
#
#     @_reg
#     def _(self, node: nodes.Import):
#         if node.name is None:
#             return
#
#         if isinstance(node.name, nodes.Identifier):
#             if node.name.name == "*":
#                 self.state.error("Z# does not yet support star (*) imports", node)
#             else:
#                 self.state.error("Z# does not yet support default import", node)
#
#         if isinstance(node.name, nodes.Alias):
#             self.state.error("Z# does not yet support default import", node)
#
#         if not isinstance(node.name, list):
#             raise TypeError(f"Expected either an identifier, alias, star or a list of names, but got a \'{type(node.name)}\' instead")
#
#         source = self.executor.execute(node.source)
#
#         if not String.is_instance(source):
#             raise TypeError(f"Currently, only string are allowed as import sources")
#
#         result = self.context.import_system.import_from(source.native)
#
#         # should resolve the source here and add the relevant names to the scope
#
#         for name in node.name:
#             if isinstance(name, nodes.Alias):
#                 if not isinstance(name.expression, nodes.Identifier):
#                     raise TypeError(f"Expected an identifier, got \'{type(name.expression)}\' instead.")
#                 origin = name.expression.name
#                 name = name.name.name
#             elif isinstance(name, nodes.Identifier):
#                 origin = name = name.name
#             else:
#                 raise TypeError
#             value = result.get_name(origin)
#
#             # self.current_scope.create_name(name, Value(origin, getattr(value, "runtime_type", None), value))
#             try:
#                 self.current_scope.create_name(name, resolved.ResolvedObject(value))
#             except NameAlreadyBoundError:
#                 if isinstance(value, OverloadGroup) and isinstance(target := self.current_scope.lookup_name(name, recursive_lookup=False).object, OverloadGroup):
#                     target.overloads.extend(value.overloads)
#                 else:
#                     raise
#
#     @singledispatchmethod
#     def _resolve(self, node: Node):
#         raise NotImplementedError(f"Can't resolve node of type {type(node)} because it is not implemented yet")
#
#     _res = _resolve.register
#
#     @_res
#     def _(self, node: nodes.Import):
#         ...  # filler
#
#     @_res
#     def _(self, node: nodes.Class):
#         result = self._nodes_cache[node]
#         assert isinstance(result, resolved.ResolvedClass)
#         result.bases = list(map(self.resolve, node.bases))
#         with self.scope(node):
#             for item in node.items:
#                 result.items.append(self.resolve(item))
#         return result
#
#     @_res
#     def _(self, node: nodes.Var):
#         result = resolved.ResolvedVar(node, self.resolve(node.name.type), self.resolve(node.initializer))
#
#         return result
#
#     @_res
#     def _(self, node: nodes.Function):
#         result = self._nodes_cache[node]
#         assert isinstance(result, resolved.ResolvedFunction)
#
#         with self.scope(node) as body_scope:
#             with self.scope(body_scope.parent):
#                 for parameter in node.positional_parameters:
#                     result.positional_parameters.append(self.resolve(parameter))
#                 for parameter in node.named_parameters:
#                     result.named_parameters.append(self.resolve(parameter))
#                 result.variadic_positional_parameter = self.resolve(node.variadic_positional_parameter)
#                 result.variadic_named_parameter = self.resolve(node.variadic_named_parameter)
#
#                 result.return_type = self.resolve(node.return_type)
#
#             if node.body is not None:
#                 result.body = []
#                 for item in node.body:
#                     result.body.append(self.resolve(item))
#
#         return result
#
#     @_res
#     def _(self, node: nodes.Parameter):
#         return self._nodes_cache[node]
#
#     @_res
#     def _(self, node: nodes.Module):
#         result = self._nodes_cache[node]
#         assert isinstance(result, resolved.ResolvedModule)
#         with self.scope(node):
#             for item in node.items:
#                 result.items.append(self.resolve(item))
#         return result
#
#     @_res
#     def _(self, node: nodes.Expression):
#         raise NotImplementedError(f"Could not resolve expression of type '{type(node)}' because it is not implemented yet")
#
#     @_res
#     def _(self, node: nodes.Identifier):
#         node = self.current_scope.lookup_name(node.name)
#         if not isinstance(node, Node):
#             if isinstance(node, resolved.ResolvedNode):
#                 return node
#             if isinstance(node, Value):
#                 node = node.value
#             if not isinstance(node, (ObjectProtocol, IMiniZObject)):
#                 raise TypeError(f"Object which is not a node must be a valid Z# object, but was '{type(node)}'")
#             return resolved.ResolvedObject(node)
#         return self._nodes_cache[node]
#
#     @_res
#     def _(self, node: nodes.Binary):
#         left = self._resolve(node.left)
#         right = self._resolve(node.right)
#         return resolved.ResolvedBinary(node, left, right)
#
#     @_res
#     def _(self, node: nodes.FunctionCall):
#         fn = self.resolve(node.callable)
#
#         if isinstance(fn, resolved.ResolvedObject):
#             fn = fn.object
#
#         fact: Callable[
#             [nodes.FunctionCall, resolved.ResolvedFunction | resolved.ResolvedClass, list[resolved.ResolvedExpression], dict[str, resolved.ResolvedExpression]]
#             , resolved.ResolvedFunctionCall | resolved.ResolvedClassCall]
#         if isinstance(fn, (resolved.ResolvedFunction, IFunction, resolved.ResolvedOverloadGroup, OverloadGroup)):
#             fact = resolved.ResolvedFunctionCall
#         elif isinstance(fn, (resolved.ResolvedClass, IClass)):
#             fact = resolved.ResolvedClassCall
#         else:
#             raise TypeError(type(fn))
#         if isinstance(fn, (IFunction, IClass, OverloadGroup)):
#             fn = resolved.ResolvedObject(fn)
#         return fact(
#             node,
#             fn,
#             [
#                 self.resolve(arg) for arg in node.arguments
#             ],
#             {
#                 name: self.resolve(arg) for name, arg in node.keyword_arguments.items()
#             }
#         )
#
#     @_res
#     def _(self, node: nodes.Literal):
#         return resolved.ResolvedObject(self.executor.execute(node))
#
#     @_res
#     def _(self, node: nodes.Return):
#         expr = self.resolve(node.expression)
#         return resolved.ResolvedReturn(node, expr)
#
#     @_res
#     def _(self, node: resolved.ResolvedOverloadGroup, scope: Scope):
#         node.parent = scope.parent.lookup_name(node.name, default=None)
#         return node


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
                    result.body = list(filter(bool, map(self.register, node.body)))

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

        return resolved.Evaluate(result)

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

    @_res
    def _(self, node: resolved.Evaluate):
        node.value = self.resolve(node.value)

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
            node.body = list(map(self.resolve, node.body)) if node.body is not None else None

    @_res
    def _(self, node: resolved.ResolvedFunctionCall):
        node.callable = self.resolve(node.callable)
        node.arguments = list(map(self.resolve, node.arguments))
        node.keyword_arguments = dict(zip(node.keyword_arguments.keys(), list(map(self.resolve, node.keyword_arguments.values()))))

    @_res
    def _(self, node: resolved.ResolvedImport):
        node.source = self.resolve(node.source)

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
    _injected: list[resolved.ResolvedNode]

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
        self._injected.append(node)

    def resolve(self) -> list[resolved.ResolvedNode]:
        result = []

        for node in self._nodes:
            result.append(self._registry.register(node))

        # for node in self.context.current_scope.items:
        #     self._resolver.resolve(node)

        for node in result:
            self._resolver.resolve(node)

        for node in self._injected:
            self._resolver.resolve(node)

        self._nodes.clear()

        return result
