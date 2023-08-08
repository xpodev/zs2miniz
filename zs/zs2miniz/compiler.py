"""
This module defines the class that's responsible for compiling a function body from resolved AST to a list of instructions.
"""

from contextlib import contextmanager
from functools import singledispatchmethod, wraps
from typing import TypeVar, Generic, Callable, TypeAlias, Type

from miniz.concrete.function import FunctionBody, Function
from miniz.concrete.module import Module
from miniz.concrete.oop import Class, Field, Method
from miniz.concrete.overloading import OverloadGroup
from miniz.concrete.signature import Parameter
from miniz.core import ImplementsType, ObjectProtocol
from miniz.generic.function import GenericFunction
from miniz.generic.generic_construction import IConstructor
from miniz.generic.signature import GenericParameter
from miniz.interfaces.base import IMiniZObject, ScopeProtocol
from miniz.interfaces.function import IFunction, IFunctionSignature
from miniz.interfaces.module import IModule
from miniz.interfaces.oop import IClass, IField, Binding, IOOPMember, IMethod, IInterface, ITypeclass, IStructure, IOOPDefinition
from miniz.interfaces.signature import IParameter
from miniz.type_system import Any, is_type, assignable_to, Void, String
from miniz.vm import instructions as vm
from miniz.vm.instruction import Instruction
from miniz.vm.runtime import Interpreter
from zs.ast import resolved
from zs.processing import StatefulProcessor, State
from zs.zs2miniz.errors import CompilerNotAvailableError
from zs.zs2miniz.import_system import ImportResult
from zs.zs2miniz.lib import CompilationContext

_T = TypeVar("_T")
_SENTINEL = object()


DefinitionFunction: TypeAlias = Callable[[resolved.ResolvedNode, IMiniZObject | None], IMiniZObject | None]


class Cache:
    _cache: dict[resolved.ResolvedNode, IMiniZObject]

    def __init__(self):
        self._cache = {}

    def cache(self, node: resolved.ResolvedNode, item: IMiniZObject | None = _SENTINEL, *, default=_SENTINEL):
        if item is _SENTINEL:
            try:
                return self._cache[node]
            except KeyError:
                if default is not _SENTINEL:
                    return default
                raise
        if item is not None:
            self._cache[node] = item
        return item


# def _cached(fn):
#     @wraps(fn)
#     def wrapper(self: "_SubCompiler", node: resolved.ResolvedNode, *args, **kwargs):
#         try:
#             return self.cache(node)
#         except KeyError:
#             return self.cache(node, fn(self, node, *args, **kwargs))
#
#     return wrapper
#
#
# DECLARATION = Cache()
# DEFINITION = Cache()


class CompilerContext:
    _cache: Cache
    _built: set[resolved.ResolvedNode]
    _compiler: "NodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        self._cache = Cache()
        self._built = set()
        self._compiler = compiler

    @property
    def compiler(self):
        return self._compiler

    def cache(self, node: resolved.ResolvedNode, item: IMiniZObject | None = _SENTINEL, *, default=_SENTINEL):
        return self._cache.cache(node, item, default=default)

    def mark_defined(self, node: resolved.ResolvedNode):
        self._built.add(node)
        return node

    def require_definition(self, node: resolved.ResolvedNode):
        if node is None:
            return None
        if node in self._built:
            return self.cache(node)
        item = self.cache(node, default=None)
        result = self.compiler.dispatcher.compile(node, item)
        self.mark_defined(node)
        if item is None and result is not None:
            self.cache(node, result)
        return result or item


# class _SubCompiler(StatefulProcessor):
#     _compiler: "NodeCompiler"
#
#     def __init__(self, compiler: "NodeCompiler"):
#         super().__init__(compiler.state)
#         self._compiler = compiler
#
#     @property
#     def compiler(self):
#         return self._compiler
#
#     @property
#     def context(self):
#         return self.compiler.context
#
#     def cache(self, *args):
#         return self.compiler.cache(*args)
#
#     def declare(self, node: resolved.ResolvedNode) -> IMiniZObject | None:
#         return self.create_object(node)
#
#     def create_object(self, node: resolved.ResolvedNode) -> IMiniZObject | None:
#         raise NotImplementedError(f"[{type(self).__name__}] Can't declare node of type \'{type(node).__name__}\'")
#
#     def compile(self, node: resolved.ResolvedNode):
#         # return self.define(node, result := self.declare(node)) or result
#         # if isinstance(node, resolved.ResolvedObject):
#         #     return node.object
#         return self._compile(node)
#
#     def _compile(self, node: resolved.ResolvedNode):
#         raise NotImplementedError(f"[{type(self).__name__}] Can't compile node of type \'{type(node).__name__}\'")


class CompilerBase(StatefulProcessor, Generic[_T]):
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

    def construct(self, node: resolved.ResolvedNode) -> _T | None:
        raise NotImplementedError

    def compile(self, node: resolved.ResolvedNode, item: _T | None) -> _T | None:
        raise NotImplementedError


class ModuleCompiler(CompilerBase[IModule]):
    def construct(self, node: resolved.ResolvedModule) -> Module | None:
        module = Module(node.name)

        for item in node.items:
            self.context.cache(item, self._construct(item, module))

        return module

    @singledispatchmethod
    def _construct(self, node: resolved.ResolvedNode, module: Module):
        raise TypeError(f"Can't construct object from node of type '{type(node)}' inside module '{module}'")

    _con = _construct.register

    @_con
    def _(self, node: resolved.ResolvedClass, module: Module):
        result = self.compiler.class_compiler.construct(node)
        module.types.append(result)
        return result

    @_con
    def _(self, node: resolved.ResolvedFunction, module: Module):
        result = self.compiler.function_compiler.construct(node)
        module.functions.append(result)
        return result

    @_con
    def _(self, node: resolved.ResolvedImport, module: None):
        # add information that module imported from node
        return ImportResult(node)

    def compile(self, node: resolved.ResolvedNode, item: _T | None):
        return None

    # @_rec
    # def _(self, node: resolved.ResolvedOverloadGroup):
    #     group = OverloadGroup(node.name, self.compiler.compile(node.parent) if node.parent else None)
    #     for overload in node.overloads:
    #         self._compile(overload)
    #     return group


class FunctionCompiler(CompilerBase[IFunction]):
    _function_body_compiler: "FunctionBodyCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._function_body_compiler = FunctionBodyCompiler(compiler)

    @property
    def function_body_compiler(self):
        return self._function_body_compiler

    def construct(self, node: resolved.ResolvedFunction) -> Function:
        fn = Function(node.name)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        return fn

    def construct_parameters(self, node: resolved.ResolvedFunction, fn: Function):
        sig = fn.signature

        for parameter in node.positional_parameters:
            sig.positional_parameters.append(self.context.cache(parameter, self.create_parameter(parameter)))

        for parameter in node.named_parameters:
            sig.named_parameters.append(self.context.cache(parameter, self.create_parameter(parameter)))

        if node.variadic_positional_parameter:
            sig.variadic_positional_parameter = self.context.cache(node.variadic_positional_parameter, self.create_parameter(node.variadic_positional_parameter))

        if node.variadic_named_parameter:
            sig.variadic_named_parameter = self.context.cache(node.variadic_positional_parameter, self.create_parameter(node.variadic_named_parameter))

    @singledispatchmethod
    def compile(self, node: resolved.ResolvedFunction, item: IMiniZObject):
        super().compile(node, item)

    _cpl = compile.register

    @_cpl
    def _(self, node: resolved.ResolvedFunction, item: Function) -> None:
        if node.return_type is None:
            item.signature.return_type = Any  # todo: infer
        else:
            item.signature.return_type = self.compiler.evaluate(node.return_type)

    @_cpl
    def _(self, node: resolved.ResolvedFunctionBody, item: FunctionBody):
        with self.compiler.expression_compiler.code_context(self._function_body_compiler):
            if node is not None:
                self.context.mark_defined(node)

                body = self.compiler.expression_compiler.compile_code(node.instructions)
                for instruction in body:
                    item.instructions.append(instruction)
            else:
                del item.instructions

    @_cpl
    def _(self, node: resolved.ResolvedParameter, item: Parameter):
        if node.type:
            item.parameter_type = self.compiler.evaluate(node.type)
        else:
            item.parameter_type = Any

    def create_parameter(self, node: resolved.ResolvedParameter):
        # parameter_type = self.compiler.evaluate(node.type) if node.type else Any
        # if is_type(parameter_type) and not isinstance(parameter_type, IConstructor):
        #     factory = Parameter
        # else:
        #     factory = GenericParameter
        # return factory(node.name, parameter_type)
        # todo: get dependencies to check if we need to create a generic parameter instead
        return Parameter(node.name)


class MethodCompiler(FunctionCompiler):
    def construct(self, node: resolved.ResolvedFunction) -> Method:
        fn = Method(node.name)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        return fn


class ClassCompiler(CompilerBase[Class]):
    method_compiler: MethodCompiler

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self.method_compiler = MethodCompiler(compiler)

    def construct(self, node: resolved.ResolvedClass) -> Class:
        cls = Class(node.name)

        for item in node.items:
            self.context.cache(item, self._construct(item, cls))

        return cls

    @singledispatchmethod
    def _construct(self, node: resolved.ResolvedNode, cls: Class):
        raise TypeError(f"Can't compile object from node of type '{type(node)}' inside class '{cls}'")

    _con = _construct.register

    @_con
    def _(self, node: resolved.ResolvedClass, cls: Class):
        result = self.construct(node)
        cls.nested_definitions.append(result)
        return result

    @_con
    def _(self, node: resolved.ResolvedFunction, cls: Class):
        result = self.method_compiler.construct(node)
        if result.name == "new":
            cls.constructors.append(result)
        else:
            cls.methods.append(result)

        return result

    # @_rec
    # @_cached
    # def _(self, node: resolved.ResolvedOverloadGroup):
    #     group = OverloadGroup(node.name, self.compiler.compile(node.parent) if node.parent else None)
    #     for overload in node.overloads:
    #         self._compile(overload)
    #     return group

    @_con
    def _(self, node: resolved.ResolvedVar, cls: Class):
        result = Field(node.name)
        cls.fields.append(result)
        return result

    @singledispatchmethod
    def compile(self, node: resolved.ResolvedNode, item: _T) -> None:
        raise TypeError(type(node), type(item))

    _cpl = compile.register

    @_cpl
    def _(self, node: resolved.ResolvedClass, item: Class):
        bases = list(map(self.compiler.evaluate, node.bases))

        if bases:
            if isinstance(bases[0], IClass):
                item.base = bases.pop(0)

            for base in bases:
                if not isinstance(base, (IInterface, ITypeclass, IStructure)):
                    raise TypeError
                item.specifications.append(base)

    @_cpl
    def _(self, node: resolved.ResolvedVar, item: Field):
        item.field_type = self.compiler.evaluate(node.type)


class CodeContext:
    _code_compiler: "CodeCompiler | None"
    _compiler: "NodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        self._code_compiler = None
        self._compiler = compiler

    @property
    def compiler(self):
        return self._compiler

    @property
    def context(self):
        return self.compiler.context

    @property
    def stack(self):
        return self.code_compiler.stack

    @property
    def code_compiler(self):
        return self._code_compiler

    @code_compiler.setter
    def code_compiler(self, value: "CodeCompiler | None"):
        self._code_compiler = value

    def compile(self, node: resolved.ResolvedNode) -> list[Instruction]:
        raise NotImplementedError


class CodeCompiler:
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

    _code_context_stack: list[CodeContext]

    _compiler: "NodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        self._compiler = compiler

        self._stack = self.StackTypeChecker()

        self._code_context_stack = [TopLevelCodeCompiler(self)]

    @property
    def compiler(self):
        return self._compiler

    @property
    def context(self):
        return self.compiler.context

    @property
    def stack(self):
        return self._stack

    @property
    def current_code_context(self):
        try:
            return self._code_context_stack[-1]
        except IndexError:
            return None

    @contextmanager
    def code_context(self, ctx: CodeContext):
        self._code_context_stack.append(ctx)
        compiler, ctx.code_compiler = ctx.code_compiler, self
        try:
            yield
        finally:
            self._code_context_stack.pop()
            ctx.code_compiler = compiler

    def compile_code(self, code: list[resolved.ResolvedNode]) -> list[Instruction]:
        result = []

        for item in code:
            result.extend(self.compile(item) or ())

        return result

    def compile_expression(self, expression: resolved.ResolvedExpression) -> list[Instruction]:
        return self.compile_code([expression])

    def compile(self, node: resolved.ResolvedNode):
        for compiler in reversed(self._code_context_stack):
            result = compiler.compile(node)
            if result is not None:
                break
        else:
            return self._compile(node)
        return result

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        raise TypeError(f"Default code compiler can't compile node of type '{type(node)}'")

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedClass):
        cls = self.context.cache(node)
        self._stack.push_object(cls)
        return [vm.LoadObject(cls)]

    @_cpl
    def _(self, node: resolved.ResolvedFunctionCall):
        result = []

        fact = vm.Call

        group = self.compiler.evaluate(node.callable)
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
        imported = self.context.cache(node)
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
            case IOOPDefinition():
                return [vm.LoadObject(member)]

        raise TypeError(type(member))

    @_cpl
    def _(self, node: resolved.ResolvedObject):
        self.stack.push_object(node.object)
        return [vm.LoadObject(node.object)]

    @_cpl
    def _(self, node: resolved.ResolvedOverloadGroup):
        return [vm.LoadObject(self.compiler.define((node, self.compiler.declare(node))))]

    @_cpl
    def _(self, node: resolved.ResolvedVar):
        return self.current_code_context.compile(node)


class TopLevelCompiler(CompilerBase):
    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

    # region Declare

    def construct(self, node: resolved.ResolvedNode) -> IMiniZObject | None:
        return self.context.cache(node, self._construct(node))

    @singledispatchmethod
    def _construct(self, node: resolved.ResolvedNode):
        raise TypeError(f"Node of type '{type(node)}' may not appear on the top level scope")

    _con = _construct.register

    @_con
    def _(self, node: resolved.ResolvedClass):
        return self.compiler.class_compiler.construct(node)

    @_con
    def _(self, node: resolved.ResolvedFunction):
        return self.compiler.function_compiler.construct(node)

    @_con
    def _(self, node: resolved.ResolvedModule):
        return self.compiler.module_compiler.construct(node)

    @_con
    def _(self, node: resolved.ResolvedImport):
        return ImportResult(node)

    @_con
    def _(self, node: resolved.ResolvedOverloadGroup):
        return OverloadGroup(node.name, None)

    del _con

    # endregion

    def compile(self, node: resolved.ResolvedNode, item: _T) -> _T | None:
        return self._compile(node, item)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode, item: _T):
        raise TypeError(f"{type(self).__name__} can't compile node of type '{node}' with object '{item}'")

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedImport, item: ImportResult):
        item.source = self.compiler.evaluate(node.source)
        if not String.is_instance(item.source):
            raise TypeError

        result = self.compiler.compilation_context.import_system.import_from(item.source.native)

        for imported_name in node.imported_names:
            self.context.cache(imported_name, result.get_name(imported_name.name))
            self.context.mark_defined(imported_name)

    @_cpl
    def _(self, node: resolved.ResolvedOverloadGroup, item: OverloadGroup):
        item.parent = self.context.require_definition(node.parent)

        for overload in node.overloads:
            item.overloads.append(self.context.require_definition(overload))

    del _cpl


class TopLevelCodeCompiler(CodeContext):
    def __init__(self, code_compiler: "CodeCompiler"):
        super().__init__(code_compiler.compiler)
        self.code_compiler = code_compiler

    def compile(self, node: resolved.ResolvedNode) -> list[Instruction]:
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return None
        # raise TypeError(f"{type(self)} can't compile node of type '{type(node)}'")

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedImport):
        source = self.compiler.evaluate(node.source)
        if not String.is_instance(source):
            raise TypeError

        result = self.compiler.compilation_context.import_system.import_from(source.native)

        for imported_name in node.imported_names:
            self.context.cache(imported_name, result.get_name(imported_name.name))
            self.context.mark_defined(imported_name)

    @_cpl
    def _(self, node: resolved.ResolvedImport.ImportedName):
        result = self.context.cache(node)
        self.code_compiler.stack.push_object(result)
        return [vm.LoadObject(result)]

    @_cpl
    def _(self, node: resolved.ResolvedObject):
        self.code_compiler.stack.push_object(node.object)
        return [vm.LoadObject(node.object)]


class FunctionBodyCompiler(CodeContext):
    def compile(self, node: resolved.ResolvedNode):
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return None

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
        parameter = self.context.cache(node)
        assert isinstance(parameter, Parameter)
        self.stack.push_argument(parameter)
        return [vm.LoadArgument(parameter)]

    @_cpl
    def _(self, node: resolved.ResolvedReturn):
        return [*(self.code_compiler.compile(node.expression) if node.expression else ()), vm.Return()]


class CompilerDispatcher(StatefulProcessor):
    _compilers: dict[type, CompilerBase]

    def __init__(self, state: State):
        super().__init__(state)

        self._compilers = {}

    def register_compiler(self, typ: Type[_T], compiler: CompilerBase[_T]):
        if typ in self._compilers:
            raise TypeError(f"Type '{typ}' is already registered")
        self._compilers[typ] = compiler

    def compile(self, node: resolved.ResolvedNode, item: _T) -> _T:
        return self.dispatch(item).compile(node, item) or item

    def dispatch(self, item: _T) -> CompilerBase[_T]:
        return self._compilers[type(item)]

    @classmethod
    def standard(cls, compiler: "NodeCompiler"):
        dispatcher = cls(compiler.state)

        dispatcher.register_compiler(Function, compiler.function_compiler)
        dispatcher.register_compiler(Parameter, compiler.function_compiler)
        dispatcher.register_compiler(FunctionBody, compiler.function_compiler)

        dispatcher.register_compiler(Method, compiler.class_compiler.method_compiler)
        dispatcher.register_compiler(Class, compiler.class_compiler)
        dispatcher.register_compiler(Field, compiler.class_compiler)

        dispatcher.register_compiler(Module, compiler.module_compiler)

        dispatcher.register_compiler(ImportResult, compiler.top_level_compiler)
        dispatcher.register_compiler(OverloadGroup, compiler.top_level_compiler)

        return dispatcher


class NodeCompiler(StatefulProcessor):
    _dispatcher: CompilerDispatcher

    _vm: Interpreter
    _context: CompilerContext

    _top_level_compiler: TopLevelCompiler
    _expression_compiler: CodeCompiler

    _class_compiler: ClassCompiler
    _function_compiler: FunctionCompiler
    _module_compiler: ModuleCompiler

    def __init__(self, state: State, context: CompilationContext):
        super().__init__(state)

        self._vm = Interpreter()
        self._context = CompilerContext(self)

        self._expression_compiler = CodeCompiler(self)
        self._top_level_compiler = TopLevelCompiler(self)

        self._class_compiler = ClassCompiler(self)
        self._function_compiler = FunctionCompiler(self)
        self._module_compiler = ModuleCompiler(self)

        self._dispatcher = CompilerDispatcher.standard(self)

        self._compilation_context = context

    @property
    def vm(self):
        return self._vm

    @property
    def context(self):
        return self._context

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def compilation_context(self):
        return self._compilation_context

    # region Sub-Compilers

    @property
    def top_level_compiler(self):
        return self._top_level_compiler

    @property
    def expression_compiler(self):
        return self._expression_compiler

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

    def declare(self, nodes: list[resolved.ResolvedNode] | resolved.ResolvedNode) -> list[tuple[resolved.ResolvedNode, IMiniZObject]] | IMiniZObject:
        if not isinstance(nodes, list):
            return self.context.cache(nodes, self.top_level_compiler.construct(nodes))

        return list(map(lambda n: (n, self.declare(n)), nodes))

    def define(self, pairs: list[tuple[resolved.ResolvedNode, IMiniZObject]] | tuple[resolved.ResolvedNode, IMiniZObject]) -> list[IMiniZObject] | IMiniZObject | None:
        if not isinstance(pairs, list):
            return self.dispatcher.compile(*pairs)

        return list(map(lambda p: self.dispatcher.compile(*p), pairs))

    def evaluate(self, expression: resolved.ResolvedExpression):
        if expression is None:
            return None
        return self.vm.run(self.expression_compiler.compile_expression(expression)).pop(default=None)
