from contextlib import contextmanager
from functools import singledispatchmethod
from pathlib import Path

from zs.ast.node import Node
from zs.ast import node_lib as nodes
from zs.ctrt.core import Null, Unit, Any, Function, OverloadGroup, Object, Variable, Class, TypeClass, TypeClassImplementation, Module, Scope
from zs.ctrt.errors import ReturnInstructionInvoked, NameNotFoundError, BreakInstructionInvoked, ContinueInstructionInvoked, UnknownMemberError
# from zs.ctrt.objects import Frame, Function, Scope, Class, FunctionGroup, Variable, TypeClass, TypeClassImplementation
from zs.ctrt.native import Boolean, Int64, Float64, String, Character
from zs.ctrt.protocols import ObjectProtocol, CallableProtocol, GetterProtocol, TypeProtocol, BindProtocol, SetterProtocol
from miniz.interfaces.base import ScopeProtocol
from zs.processing import StatefulProcessor, State
from zs.std.processing.import_system import ImportSystem
from zs.text.token import TokenType

# from zs.ctrt.native import *
from zs.utils import SingletonMeta

_GLOBAL_SCOPE = object()


def _get_dict_from_import_result(node: nodes.Import, result: ScopeProtocol):
    res = {}
    errors = []

    match node.name:
        case nodes.Identifier() as star:
            if star.name != '*':
                errors.append(f"Can't perform a default import since that is not a feature yet")
            for name, item in result.all():
                res[name] = item
        case nodes.Alias() as alias:
            errors.append(f"Can't perform a default import since that is not a feature yet")
        case list() as names:
            for item in names:
                name = item.name
                try:
                    if isinstance(item, nodes.Alias):
                        if not isinstance(item.expression, nodes.Identifier):
                            errors.append(f"Imported name must be an identifier")
                        item_name = item.expression.name
                        res[name.name] = result.get_name(item_name)
                    else:
                        res[name] = result.get_name(name)
                except KeyError:
                    errors.append(f"Could not import name \"{name}\" from \"{node.source}\"")
        case _:
            errors.append(f"Unknown error while importing \"{node.source}\"")

    return res, errors


class Frame(Scope):
    _function: Function

    def __init__(self, function: Function | None, parent: ScopeProtocol | None = None):
        super().__init__(parent)
        self._function = function

    @property
    def function(self):
        return self._function


class InterpreterState:
    _frame_stack: list[Frame]
    _scope: Scope
    _global_scope: Scope
    _scope_protocol: ScopeProtocol | None

    def __init__(self, global_scope: Scope):
        self._frame_stack = [Frame(None, global_scope)]
        self._scope = self._global_scope = global_scope
        self._scope_protocol = None

    @property
    def current_frame(self):
        return self._frame_stack[-1]

    @property
    def current_scope(self):
        return self._scope

    @property
    def global_scope(self):
        return self._global_scope

    @contextmanager
    def scope(self, scope: ScopeProtocol = None, /, parent: Scope = None, **items: ObjectProtocol):
        self._scope, old = scope or Scope(parent or self._scope, **items), self._scope
        try:
            yield self._scope
        finally:
            self._scope.on_exit()
            self._scope = old

    @contextmanager
    def frame(self, function: "Function"):
        self._frame_stack.append(Frame(function, function.lexical_scope))
        self._scope, scope = self.current_frame, self._scope
        try:
            yield
        finally:
            self._frame_stack.pop().on_exit()
            self._scope = scope


class Interpreter(StatefulProcessor, metaclass=SingletonMeta):
    """
    This class is responsible for executing nodes.
    """

    _x: InterpreterState
    _import_system: ImportSystem

    def __init__(self, state: State, global_scope: Scope = None, import_system: ImportSystem = None):
        super().__init__(state)
        self._x = InterpreterState(global_scope or Scope())
        self._import_system = import_system or ImportSystem()

        self._srf_access = False

    @property
    def x(self):
        return self._x

    @property
    def import_system(self):
        return self._import_system

    @contextmanager
    def new_context(self):
        context = self.x
        try:
            self._x = InterpreterState(self.x.global_scope)
            yield
        finally:
            self._x = context

    @contextmanager
    def srf_access(self, srf=True):
        self._srf_access, old = srf, self._srf_access
        try:
            yield
        finally:
            self._srf_access = old

    def process(self, node: Node):
        return self._process(node)

    @singledispatchmethod
    def _process(self, node: Node):
        return node

    _exec = _process.register

    @_exec
    def _(self, assign: nodes.Assign):
        # target = assign.left
        # if isinstance(target, nodes.Identifier):
        #     self.x.frame.set_name(target.name, self.execute(assign.right))
        # else:
        #     self.state.warning(f"Assignment for anything other than a variable is not yet supported.")
        with self.srf_access():
            target = self.process(assign.left)

        if not isinstance(target, SetterProtocol):
            self.state.error(f"Could not assign to '{assign.left}' because it does not implement the setter protocol", assign)

        target.set(self.process(assign.right))

    @_exec
    def _(self, binary: nodes.Binary):
        left = self.process(binary.left)
        right = self.process(binary.right)

        with self.srf_access():
            left_srf = self.process(left)
            right_srf = self.process(right)

        try:
            op_fn = self.do_get_member(left_srf, left, f"_{binary.token_info.operator.value}_")
            return self.do_function_call(op_fn, [right], {})
        except TypeError:
            op_fn = self.do_get_member(right_srf, right, f"_{binary.token_info.operator.value}_")
            return self.do_function_call(op_fn, [left], {})

    @_exec
    def _(self, block: nodes.Block):
        with self.x.scope():
            for statement in block.statements:
                self.process(statement)

    @_exec
    def _(self, break_: nodes.Break):
        loop = self.process(break_.loop) if break_.loop else None

        raise BreakInstructionInvoked(loop)

    @_exec
    def _(self, continue_: nodes.Continue):
        loop = self.process(continue_.loop) if continue_.loop else None

        raise ContinueInstructionInvoked(loop)

    @_exec
    def _(self, export: nodes.Export):
        target_scope = self.x.current_scope.parent
        if export.source is not None:
            source = self.process(export.source)

            if not isinstance(source, ScopeProtocol):
                raise TypeError

            if isinstance(export.exported_names, nodes.Identifier):
                if export.exported_names.name == "*":
                    for name, item in source.all():
                        target_scope.refer(name, item)
                else:
                    raise ValueError
            elif isinstance(export.exported_names, list):
                for item in export.exported_names:
                    if isinstance(item, nodes.Identifier):
                        target_scope.refer(item.name, source.get_name(item.name))
                    elif isinstance(item, nodes.Alias):
                        if not isinstance(item.expression, nodes.Identifier):
                            raise TypeError
                        target_scope.refer(item.name.name, item.expression.name)
                    else:
                        raise TypeError
            else:
                raise TypeError
        else:
            if isinstance(export.exported_names, nodes.Alias):
                name = export.exported_names.name.name
                exported_item = self.process(export.exported_names.expression)
            elif isinstance(export.exported_names, nodes.Identifier):
                name = export.exported_names.name
                exported_item = self.process(export.exported_names)
            else:
                exported_item = self.process(export.exported_names)
                name = getattr(exported_item, "name", None)
                if not name:
                    raise ValueError
            target_scope.define(name, exported_item, exported_item)

    @_exec
    def _(self, expression_statement: nodes.ExpressionStatement):
        self.process(expression_statement.expression)

    @_exec
    def _(self, call: nodes.FunctionCall):
        function = self.process(call.callable)

        # is function really a function?

        arguments = list(map(self.process, call.arguments))
        keyword_arguments = {
            name: self.process(value)
            for name, value in call.keyword_arguments.items()
        }

        # did we successfully evaluate the arguments?

        # can we unpack the arguments into the function parameters without any errors? I guess we should try...

        return self.do_function_call(function, arguments, keyword_arguments)

    @_exec
    def _(self, function: nodes.Function):
        return_type = self.process(function.return_type) if function.return_type is not None else Unit

        if function.name is not None:
            if isinstance(function.name, nodes.Identifier):
                name = function.name.name
            elif isinstance(function.name, nodes.Literal):
                name = function.name.token_info.literal.value
            else:
                raise TypeError
        else:
            name = None

        func = Function(name, return_type, self.x.current_scope, [])
        sig = func.signature

        if name:
            self.x.current_scope.define(name, func)

        for parameter in function.parameters:
            parameter_type = self.process(parameter.type) if parameter.type else Any
            sig.define_parameter(parameter.name.name, parameter_type)

        sig.build()

        if function.body:
            func.body.extend(function.body)

        return func

    @_exec
    def _(self, identifier: nodes.Identifier):
        try:
            return self.do_resolve_name(identifier.name)
        except NameNotFoundError:
            return self.state.error(f"Could not resolve name '{identifier.name}'", identifier)

    @_exec
    def _(self, if_: nodes.If):
        with self.x.scope():
            condition = self.process(if_.condition)

            if if_.name:
                if_.owner = if_.type = None
                self.x.current_scope.define(if_.name.name, if_)

            if condition:
                self.process(if_.if_true)
            elif if_.if_false:
                self.process(if_.if_false)

    @_exec
    def _(self, import_: nodes.Import):
        result = self.__get_import_result(import_)

        if isinstance(result, str):
            return self.state.error(result)

        items, errors = _get_dict_from_import_result(import_, result)
        for name, item in items.items():
            self.x.current_scope.refer(name, item)

        for error in errors:
            self.state.error(error, import_)

        return Scope(None, **items)

    @_exec
    def _(self, literal: nodes.Literal):
        value = literal.token_info.literal.value
        if value == "true":
            return Boolean.TRUE
        if value == "false":
            return Boolean.FALSE
        if value == "null":
            return Null.Instance
        match literal.token_info.literal.type:
            case TokenType.String:
                return String(value)
            case TokenType.Decimal:
                return Int64(int(value))
            case TokenType.Real:
                return Float64(float(value))
            case TokenType.Character:
                return Character(value)
            case _:
                raise TypeError(literal.token_info.literal.type)

    @_exec
    def _(self, member_access: nodes.MemberAccess):
        with self.srf_access():
            obj_srf = self.process(member_access.object)
        with self.srf_access(False):
            obj = self.process(member_access.object)
        return self.do_get_member(obj_srf, obj, member_access.member.name)

    @_exec
    def _(self, module: nodes.Module):
        mod = Module(module.name, self.x.current_scope)

        if mod.name:
            self.x.current_scope.refer(mod.name, mod)

        with self.x.scope(mod):
            for item in module.items:
                self.process(item)

        return mod

    @_exec
    def _(self, cls: nodes.Class):
        name = cls.name.name if cls.name else None
        class_ = Class(name, self.process(cls.base), self.x.current_scope)

        if class_.name is not None:
            self.x.current_scope.define(class_.name, class_)

        with self.x.scope(class_):
            for item in cls.items:
                self.process(item)

        return class_

    @_exec
    def _(self, tc: nodes.TypeClass):
        type_class = TypeClass(tc.name.name, None, self.x.current_scope)

        self.x.current_scope.define(type_class.name, type_class)

        with self.x.scope(type_class):
            for item in tc.items:
                self.process(item)

        return type_class

    @_exec
    def _(self, impl: nodes.TypeClassImplementation):
        type_class = self.process(impl.name)
        impl_type = self.process(impl.implemented_type)

        if not isinstance(type_class, TypeClass):
            raise TypeError(f"'{impl.name}' is not a valid type class")

        if not isinstance(impl_type, TypeProtocol):
            raise TypeError(f"implementation for typeclass '{type_class.name}' must be a type")

        implementation = TypeClassImplementation(f"{type_class.name}.{impl_type}", self.x.current_scope, impl_type)
        with self.x.scope(implementation, value=implementation):
            for item in impl.items:
                self.process(item)

        for method in type_class._methods:
            try:
                impl = implementation.get_name(method.name, implementation)
                #
                # if isinstance(impl, FunctionGroup._BoundFunctionGroup):
                #     impl = impl.group
                # if isinstance(impl, FunctionGroup):
                #     for overload in impl.overloads:
                #         if overload.get_type().compare_type_signature(method.get_type()):
                #             overload.parameters[0].type = impl_type
                # if isinstance(impl, Function):
                #     if impl.get_type().compare_type_signature(method.get_type()):
                #         impl.parameters[0].type = impl_type
            except UnknownMemberError:
                # error: not implemented
                ...

        # validate that all items are implemented

        type_class.add_implementation(impl_type, implementation)

        return implementation

    @_exec
    def _(self, return_: nodes.Return):
        expression = self.process(return_.expression) if return_.expression else None
        raise ReturnInstructionInvoked(expression)

    @_exec
    def _(self, set_: nodes.Set):
        value = self.process(set_.expression)
        self.x.global_scope.refer(set_.name.name, value)

    @_exec
    def _(self, var: nodes.Var):
        var_type = self.process(var.name.type) if var.name.type is not None else None
        initializer = self.process(var.initializer) if var.initializer is not None else None

        if var_type is None and initializer is None:
            return self.state.error(f"You must either specify a type or a value in a `var` statement", var)

        if var_type is None:
            var_type = initializer.runtime_type
        if not isinstance(var_type, TypeProtocol):
            return self.state.error(f"'var' statement type must be a valid Z# type")
        if initializer is None:
            initializer = var_type.default()

        if not initializer.runtime_type.assignable_to(var_type):
            return self.state.error(f"Initializer expression does not match the variable type", var)

        name = var.name.name.name
        variable = Variable(name, var_type, initializer)
        self.x.current_scope.define(name, variable, variable)

        return variable

    @_exec
    def _(self, when: nodes.When):
        when.owner = when.type = None

        with self.x.scope():
            if when.name:
                self.x.current_scope.define(when.name.name, when)

            value = self.process(when.expression)

            self.x.current_scope.refer("value", value)

            skip_validation = False
            for case in when.cases:
                case_value = self.process(case.expression)

                if skip_validation or case_value == value:
                    try:
                        self.process(case.body)
                    except BreakInstructionInvoked:
                        ...
                    except ContinueInstructionInvoked:
                        skip_validation = True
                        continue
                    break
            else:
                if when.else_body:
                    self.process(when.else_body)

    @_exec
    def _(self, while_: nodes.While):
        with self.x.scope():
            if while_.name:
                while_wrapper = while_
                self.x.current_scope.define(while_.name.name, while_wrapper)

            while self.process(while_.condition):
                try:
                    self.process(while_.body)
                except BreakInstructionInvoked as e:
                    if e.loop is None or e.loop is while_:
                        break
                    raise
                except ContinueInstructionInvoked as e:
                    if e.loop is None or e.loop is while_:
                        continue
                    raise
            else:
                if while_.else_body:
                    self.process(while_.else_body)

    def __get_import_result(self, import_: nodes.Import):
        source = self.process(import_.source)

        if isinstance(source, String):
            source = source.native
            # path = Path(str(source))
            # if not path.suffixes:
            #     path /= f"{path.stem}.module.zs"

            result = self._import_system.import_from(source)

            if result is None:
                return f"Could not import \"{source}\""

            result._node = import_

            return result

        return source  # todo: make sure is ImportResult

    # runtime implementation functions

    @staticmethod
    def do_function_call(function: CallableProtocol, arguments: list[ObjectProtocol], keyword_arguments: dict[str, ObjectProtocol]) -> ObjectProtocol:
        if not isinstance(function, CallableProtocol):
            raise TypeError(f"'function' must implement the callable protocol")

        return function.call(arguments, keyword_arguments)

    def do_get_member(self, obj_srf, obj: ObjectProtocol, name: str):
        try:
            member = obj_srf.type.get_name(name, instance=obj)
        except AttributeError:
            member = obj_srf.runtime_type.get_name(name, instance=obj)
        if isinstance(member, BindProtocol):
            member = member.bind([obj], {})
        if self._srf_access:
            return member
        if isinstance(member, GetterProtocol):
            return member.get()
        return member

    def do_resolve_name(self, name: str):
        item = self.x.current_scope.get_name(name)
        if self._srf_access:
            return item
        if isinstance(item, GetterProtocol):
            return item.get()
        return item
