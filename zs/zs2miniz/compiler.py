"""
This module defines the class that's responsible for compiling a function body from resolved AST to a list of instructions.
"""

from contextlib import contextmanager
from functools import singledispatchmethod, wraps
from typing import TypeVar, Generic

from miniz.concrete.function import FunctionBody, Function
from miniz.concrete.module import Module
from miniz.concrete.oop import Class, Field, Method
from miniz.concrete.overloading import OverloadGroup
from miniz.concrete.signature import Parameter
from miniz.core import ImplementsType, ObjectProtocol
from miniz.generic.signature import GenericParameter
from miniz.interfaces.base import IMiniZObject, ScopeProtocol
from miniz.interfaces.function import IFunction, IFunctionSignature
from miniz.interfaces.module import IModule
from miniz.interfaces.oop import IClass, IField, Binding, IOOPMember, IMethod, IInterface, ITypeclass, IStructure
from miniz.interfaces.signature import IParameter
from miniz.type_system import Any, is_type, assignable_to, Void, String
from miniz.vm import instructions as vm
from miniz.vm.instruction import Instruction
from miniz.vm.runtime import Interpreter
from zs.ast import resolved
from zs.processing import StatefulProcessor, State
from zs.zs2miniz.errors import CompilerNotAvailableError
from zs.zs2miniz.lib import CompilationContext

_T = TypeVar("_T")
_SENTINEL = object()


def _cached(fn):
    @wraps(fn)
    def wrapper(self: "_SubCompiler", node: resolved.ResolvedNode, *args, **kwargs):
        try:
            return self.cache(node)
        except KeyError:
            return self.cache(node, fn(self, node, *args, **kwargs))

    return wrapper


class CompilerContext:
    ...


class _SubCompiler(StatefulProcessor):
    _compiler: "NodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler.state)
        self._compiler = compiler

    @property
    def compiler(self):
        return self._compiler

    @property
    def context(self):
        return self.compiler.context

    def cache(self, *args):
        return self.compiler.cache(*args)

    def compile(self, node: resolved.ResolvedNode):
        if isinstance(node, resolved.ResolvedObject):
            return node.object
        return self._compile(node)

    def _compile(self, node: resolved.ResolvedNode):
        raise NotImplementedError(f"[{type(self).__name__}] Can't compile node of type \'{type(node).__name__}\'")


class ContextualCompiler(_SubCompiler, Generic[_T]):
    _context_item: _T | None
    _node: resolved.ResolvedNode | None

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)
        self._context_item = None
        self._node = None

    @property
    def current_context_item(self):
        return self._context_item

    @property
    def compiler(self):
        return self._compiler

    @contextmanager
    def context_item(self, item: _T, node: resolved.ResolvedNode = None):
        node, self._node = self._node, node
        item, self._context_item = self._context_item, item
        try:
            yield self._context_item
        finally:
            self._context_item = item
            self._node = node

    def compile(self, node: resolved.ResolvedNode = _SENTINEL):
        if node is _SENTINEL:
            self.cache(node := self._node, self.current_context_item)
            return self.compile_current_context_item(node)
        return super().compile(node)

    def _compile(self, node: resolved.ResolvedNode):
        return super()._compile(node)

    def compile_current_context_item(self, node: resolved.ResolvedNode):
        raise NotImplementedError

    # def compile(self, node: ResolvedNode, **kwargs) -> _T:
    #     try:
    #         return self.cache(node)
    #     except KeyError:
    #         return self._compile(node, **kwargs)
    #
    # def _compile(self, node: ResolvedNode, **_):
    #     if isinstance(node, ResolvedObject):
    #         return node.object
    #     raise NotImplementedError(f"Can't compile node of type \'{type(node)}\' because it is not implemented yet")


class ModuleCompiler(ContextualCompiler[IModule]):
    def compile_current_context_item(self, node: resolved.ResolvedModule):
        for item in node.items:
            self.compile(item)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        super()._compile(node)

    _cpl = _compile.register

    @_cpl
    # @_cached
    def _(self, node: resolved.ResolvedClass):
        cls = self.compiler.top_level_compiler.compile(node)
        self.current_context_item.types.append(cls)
        return cls

    @_cpl
    # @_cached
    def _(self, node: resolved.ResolvedFunction):
        fn = self.compiler.top_level_compiler.compile(node)
        self.current_context_item.functions.append(fn)
        return fn

    @_cpl
    # @_cached
    def _(self, node: resolved.ResolvedOverloadGroup):
        group = OverloadGroup(node.name, self.compiler.compile(node.parent) if node.parent else None)
        for overload in node.overloads:
            self._compile(overload)
        return group


class FunctionCompiler(ContextualCompiler[Function]):
    _function_body_compiler: "FunctionBodyCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._function_body_compiler = FunctionBodyCompiler(compiler)

    @property
    def function_body_compiler(self):
        return self._function_body_compiler

    def compile_current_context_item(self, node: resolved.ResolvedFunction):
        for parameter in node.positional_parameters:
            self.current_context_item.positional_parameters.append(self._compile_parameter(parameter))

        for parameter in node.named_parameters:
            self.current_context_item.named_parameters.append(self._compile_parameter(parameter))

        if node.variadic_positional_parameter:
            self.current_context_item.variadic_positional_parameter = self._compile_parameter(node.variadic_positional_parameter)

        if node.variadic_named_parameter:
            self.current_context_item.variadic_named_parameter = self._compile_parameter(node.variadic_named_parameter)

        self.current_context_item.return_type = self.compiler.compile(resolved.Evaluate(node.return_type)) if node.return_type is not None else None

        if node.body is not None:
            with self.compiler.code_compiler.code_context(self._function_body_compiler):
                body = self.compiler.code_compiler.compile_code(node.body)
                for item in body:
                    self.current_context_item.body.instructions.append(item)

        if self.current_context_item.return_type is None:
            self.current_context_item.return_type = Any  # todo: infer

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedFunction):
        return super()._compile(node)

    _cpl = _compile.register

    def _compile_parameter(self, node: resolved.ResolvedParameter):
        parameter_type = self.compiler.compile(node.type) if node.type else Any
        if is_type(parameter_type):
            factory = Parameter
        else:
            factory = GenericParameter
        result = factory(node.name, parameter_type)
        self.compiler.cache(node, result)
        return result


class FunctionBodyCompiler(ContextualCompiler[FunctionBody]):
    @property
    def stack(self):
        return self.compiler.code_compiler.stack

    @contextmanager
    def context_item(self, item: FunctionBody, node: resolved.ResolvedFunction = None):
        state = self.stack.reset()
        try:
            with super().context_item(item, node) as ctx_item:
                yield ctx_item
                if item.owner.signature.return_type is not Void:
                    result = self.stack.top()[0]
                    returns = item.owner.signature.return_type
                    assert assignable_to(result, returns)
        finally:
            self.stack.reset(state)

    def compile(self, node: resolved.ResolvedNode = _SENTINEL):
        if node is _SENTINEL:
            return super().compile()
        return self._compile(node)

    def compile_current_context_item(self, node: resolved.ResolvedFunction):
        if node.body is not None:
            for item in node.body:
                for inst in self.compile(item):
                    self.current_context_item.instructions.append(inst)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        raise CompilerNotAvailableError

    _cpl = _compile.register

    # @_cpl
    # def _(self, node: res.ResolvedClassCall):
    #     result = []
    #
    #     for arg in node.arguments:
    #         result.extend(self.compile(arg))
    #     # todo: named args
    #     # todo: find suitable constructor
    #     cls = self.compiler.compile(node.callable)
    #     assert isinstance(cls, Class)
    #     args = self._stack.top(len(node.arguments))
    #     constructors = cls.constructor.get_match(args, [], strict=True)
    #     if not constructors:
    #         constructors = cls.constructor.get_match(args, [])
    #     if len(constructors) != 1:
    #         raise ValueError
    #     return [*result, vm.CreateInstance(constructors[0])]

    # @_cpl
    # def _(self, node: res.ResolvedFunctionCall):
    #     return self.compiler.code_compiler.compile(node)

    @_cpl
    def _(self, node: resolved.ResolvedParameter):
        parameter = self.cache(node)
        assert isinstance(parameter, Parameter)
        self.stack.push_argument(parameter)
        return [vm.LoadArgument(parameter)]

    @_cpl
    def _(self, node: resolved.ResolvedObject):
        obj = node.object
        self.stack.push_object(obj)
        return [vm.LoadObject(obj)]

    @_cpl
    def _(self, node: resolved.ResolvedReturn):
        return [*(self.compiler.code_compiler.compile(node.expression) if node.expression else ()), vm.Return()]


class ClassCompiler(ContextualCompiler[Class]):
    def compile_current_context_item(self, node: resolved.ResolvedClass):
        bases = list(map(self.compiler.compile, node.bases))

        if bases:
            if isinstance(bases[0], IClass):
                self.current_context_item.base = bases.pop(0)

            for base in bases:
                if not isinstance(base, (IInterface, ITypeclass, IStructure)):
                    raise TypeError
                self.current_context_item.specifications.append(base)

        for item in node.items:
            self.compile(item)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        super()._compile(node)

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedClass):
        current = self.current_context_item
        with self.compiler.class_compiler.context_item(Class(node.name), node) as result:
            self.compiler.class_compiler.compile()
        current.nested_definitions.append(result)
        return result

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedFunction):
        with self.compiler.function_compiler.context_item(Method(node.name), node) as result:
            # self.compiler.function_compiler.compile()
            if result.name == "new":
                self.current_context_item.constructors.append(result)
            else:
                self.current_context_item.methods.append(result)

        return result

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedOverloadGroup):
        group = OverloadGroup(node.name, self.compiler.compile(node.parent) if node.parent else None)
        for overload in node.overloads:
            self._compile(overload)
        return group

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedVar):
        field = Field(node.name)  # todo: execute expression? or maybe by build order
        if node.type:
            field.field_type = self.compiler.compile(resolved.Evaluate(node.type))
        self.current_context_item.fields.append(field)

        return field


class CodeCompiler(_SubCompiler):
    class StackTypeChecker:
        _stack: list[ImplementsType]

        def __init__(self):
            self._stack = []

        @property
        def size(self):
            return len(self._stack)

        def _push(self, tp: ImplementsType):
            self._stack.append(tp)

        def _pop(self):
            return self._stack.pop()

        def push_type(self, tp: ImplementsType):
            self._push(tp)

        def push_object(self, obj: ObjectProtocol):
            self._push(obj.runtime_type)

        def push_argument(self, p: IParameter):
            self._push(p.parameter_type)

        def push_field(self, f: IField):
            self._push(f.field_type)

        def apply_function(self, fn: IFunctionSignature):
            if len(self._stack) < len(fn.parameters):
                raise TypeError

            _cache = []

            for parameter in reversed(fn.parameters):
                tp = self._pop()
                _cache.append(tp)

                if not assignable_to(tp, parameter.parameter_type):
                    break
            else:
                if fn.return_type is not Void:
                    self._push(fn.return_type)

                return

            for tp in reversed(_cache):
                self._push(tp)

        def pop(self):
            return self._pop()

        def reset(self, state: list[ImplementsType] = None):
            state, self._stack = self._stack, state if state is not None else []
            return state

        def top(self, n: int = 1):
            if not n:
                return []
            if len(self._stack) < n:
                raise IndexError
            return self._stack[-n:]

        def __repr__(self):
            return repr(self._stack)

    _stack: StackTypeChecker

    _code_context: _SubCompiler | None

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._stack = self.StackTypeChecker()

        self._code_context = None

    @property
    def stack(self):
        return self._stack

    @property
    def current_code_context(self):
        return self._code_context

    @contextmanager
    def code_context(self, ctx: _SubCompiler):
        ctx, self._code_context = self._code_context, ctx
        try:
            yield
        finally:
            self._code_context = ctx

    def compile_code(self, code: list[resolved.ResolvedNode]) -> list[Instruction]:
        result = []

        for item in code:
            result.extend(self.compile(item) or ())

        return result

    def compile(self, node: resolved.ResolvedNode):
        try:
            return self._code_context.compile(node)
        except CompilerNotAvailableError:
            return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return super()._compile(node)

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedClass):
        cls = self.compiler.compile(node)
        self._stack.push_object(cls)
        return [vm.LoadObject(cls)]

    @_cpl
    def _(self, node: resolved.ResolvedFunctionCall):
        result = []

        fact = vm.Call

        group = self.compiler.compile(resolved.Evaluate(node.callable) if isinstance(node.callable, resolved.ResolvedExpression) else node.callable)
        if isinstance(group, IClass):
            self.stack.push_type(group)

        for arg in node.arguments:
            result.extend(self.compile(arg))

        args = self.stack.top(len(node.arguments))

        kwargs = {}
        kwarg_types = []

        for name, arg in node.keyword_arguments.items():
            code = self.compile(arg)
            kwargs[name] = code
            kwarg_types.append((name, self.stack.top()[0]))

        if isinstance(group, IClass):
            args.insert(0, group)
            group = group.constructor
            fact = vm.CreateInstance

        # if not isinstance(group, (IFunction, OverloadGroup)):
        #     group = self.compiler.vm.run(group)
        if isinstance(group, IFunction):
            fn = group
        elif isinstance(group, OverloadGroup):
            overloads = group.get_match(args, kwarg_types, strict=True)

            if not overloads:
                overloads = group.get_match(args, kwarg_types, recursive=True)

            if len(overloads) != 1:
                raise ValueError("can't find suitable overload")

            fn = overloads[0]
        else:
            raise TypeError(type(group))

        for parameter in fn.signature.named_parameters:
            result.extend(kwargs[parameter.name])

        self.stack.apply_function(fn.signature)

        return [*result, fact(fn)]

    @_cpl
    def _(self, node: resolved.ResolvedImport):
        return self.current_code_context.compile(node)

    @_cpl
    def _(self, node: resolved.ResolvedImport.ImportedName):
        imported = self.cache(node)
        self.stack.push_object(imported)
        return [vm.LoadObject(imported)]

    @_cpl
    def _(self, node: resolved.ResolvedMemberAccess):
        result = self.compile(node.object)

        tp = self.stack.top()[0]

        assert isinstance(tp, ScopeProtocol)

        member = tp.get_name(node.member_name)

        if isinstance(member, IOOPMember):
            assert isinstance(tp, ImplementsType)
            match member.binding:
                case Binding.Instance:
                    if not assignable_to(tp, member.owner):
                        raise TypeError
                    self.stack.pop()
                case Binding.Static:
                    result = []
                    self.stack.pop()
                case Binding.Class:
                    if assignable_to(tp, member.owner):
                        result = [vm.LoadObject(tp.runtime_type)]
                    self.stack.pop()
            match member:
                case IField() as field:
                    self.stack.push_field(field)
                    return [*result, vm.LoadField(field)]
                case IMethod() as method:
                    """
                    Push 'this' if available, call a bound method constructor. otherwise, return the overloads normally
                    """
                    raise NotImplementedError

        match member:
            case IFunction():
                return [vm.LoadObject(member)]
            case OverloadGroup():
                return [vm.LoadObject(member)]

        raise TypeError(type(member))

    @_cpl
    def _(self, node: resolved.ResolvedObject):
        self.stack.push_object(node.object)
        return [vm.LoadObject(node.object)]

    @_cpl
    def _(self, node: resolved.ResolvedOverloadGroup):
        return [vm.LoadObject(self.compiler.compile(node))]

    @_cpl
    def _(self, node: resolved.ResolvedVar):
        return self.current_code_context.compile(node)


class TopLevelCompiler(_SubCompiler):
    _code_compiler: "TopLevelCodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)
        self._code_compiler = TopLevelCodeCompiler(compiler)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return super()._compile(node)

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.Evaluate) -> IMiniZObject | ObjectProtocol | _T:
        with self.compiler.code_compiler.code_context(self._code_compiler):
            ctx = self.compiler.vm.run(self.compiler.code_compiler.compile_code([node.value]))
            if isinstance(node.value, resolved.ResolvedExpression):
                value = ctx.pop()
                self.compiler.code_compiler.stack.pop()
                # if not assignable_to(value.runtime_type, self.compiler.code_compiler.stack.pop()):
                #     raise TypeError
                return value

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedClass):
        with self.compiler.class_compiler.context_item(Class(node.name), node) as result:
            self.compiler.class_compiler.compile()

            nodes = []

            def _recurse(_node: resolved.ResolvedClass):
                for _item in _node.items:
                    if isinstance(_item, resolved.ResolvedClass):
                        _recurse(_item)
                    elif isinstance(_item, resolved.ResolvedFunction):
                        nodes.append((_item, self.cache(_item)))

            _recurse(node)

            for node, item in nodes:
                with self.compiler.function_compiler.context_item(item, node):
                    self.compiler.function_compiler.compile()

        return result

    @_cpl
    def _(self, node: resolved.ResolvedExpression):
        with self.compiler.code_compiler.code_context(self._code_compiler):
            return self.compiler.code_compiler.compile(node)

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedFunction):
        with self.compiler.function_compiler.context_item(Function(node.name), node) as result:
            self.compiler.function_compiler.compile()

        return result

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedImport.ImportedName):
        raise RuntimeError(f"This method should not be invoked.")

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedModule):
        with self.compiler.module_compiler.context_item(Module(node.name), node) as result:
            self.compiler.module_compiler.compile()

        return result

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedOverloadGroup):
        result = OverloadGroup(node.name, self.compile(node.parent) if node.parent else None)

        for overload in node.overloads:
            result.overloads.append(self.compile(overload))

        return result


class TopLevelCodeCompiler(_SubCompiler):
    def compile(self, node: resolved.ResolvedNode):
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        raise CompilerNotAvailableError

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.Evaluate) -> IMiniZObject | ObjectProtocol | _T:
        return self.compiler.top_level_compiler.compile(node)

    @_cpl
    @_cached
    def _(self, node: resolved.ResolvedImport):
        source = self.compile(resolved.Evaluate(node.source))
        if not String.is_instance(source):
            raise TypeError

        result = self.compiler.context.import_system.import_from(source.native)

        for imported_name in node.imported_names:
            self.cache(imported_name, result.get_name(imported_name.name))


class NodeCompiler(StatefulProcessor):
    _cache: dict[resolved.ResolvedNode, ObjectProtocol]

    _vm: Interpreter
    _context: CompilerContext

    _top_level_compiler: TopLevelCompiler
    _code_compiler: CodeCompiler

    _class_compiler: ClassCompiler
    _function_compiler: FunctionCompiler
    _module_compiler: ModuleCompiler

    _compilation_context: CompilationContext

    def __init__(self, state: State, context: CompilationContext):
        super().__init__(state)

        self._cache = {}

        self._vm = Interpreter()
        self._context = CompilerContext()

        self._top_level_compiler = TopLevelCompiler(self)
        self._code_compiler = CodeCompiler(self)

        self._class_compiler = ClassCompiler(self)
        self._function_compiler = FunctionCompiler(self)
        self._module_compiler = ModuleCompiler(self)

        self._compilation_context = context

    @property
    def vm(self):
        return self._vm

    @property
    def context(self):
        # return self._context
        return self._compilation_context

    # region Sub-Compilers

    @property
    def top_level_compiler(self):
        return self._top_level_compiler

    @property
    def code_compiler(self):
        return self._code_compiler

    @property
    def class_compiler(self):
        return self._class_compiler

    @property
    def function_compiler(self):
        return self._function_compiler

    @property
    def module_compiler(self):
        return self._module_compiler

    # endregion Sub-Compilers

    def cache(self, node: resolved.ResolvedNode, value: ObjectProtocol | IMiniZObject = _SENTINEL):
        if value is _SENTINEL:
            return self._cache[node]
        if value is not None:
            self._cache[node] = value
        return value

    def compile(self, nodes: list[resolved.ResolvedNode] | resolved.ResolvedNode) -> list[IMiniZObject] | IMiniZObject:
        if isinstance(nodes, list):
            return list(filter(bool, map(self.top_level_compiler.compile, nodes)))
        return self.top_level_compiler.compile(nodes)
