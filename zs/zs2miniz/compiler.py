"""
This module defines the class that's responsible for compiling a function body from resolved AST to a list of instructions.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import singledispatchmethod
from typing import TypeVar, Generic, Type

from utilz.analysis import CodeAnalyzer
from utilz.analysis.analyzers import ResultTypeAnalyzer
from miniz.concrete.function import FunctionBody, Function
from miniz.concrete.module import Module
from miniz.concrete.oop import Class, Field, Method, MethodBody
from miniz.concrete.overloading import OverloadGroup
from miniz.concrete.signature import Parameter
from miniz.core import TypeProtocol
from miniz.generic import GenericSignature, GenericParameter, GenericInstance
from miniz.generic.oop import GenericClassInstanceMemberReference
from miniz.interfaces.base import IMiniZObject, ScopeProtocol
from miniz.interfaces.function import IFunction
from miniz.interfaces.module import IModule
from miniz.interfaces.oop import IClass, IField, Binding, IOOPMemberDefinition, IMethod, IInterface, ITypeclass, IStructure, IOOPDefinition
from miniz.type_system import Any, assignable_to, String
from miniz.vm import instructions as vm
from miniz.vm.instruction import Instruction
from miniz.vm.runtime import Interpreter
from miniz.vm.type_stack import TypeStack
from utilz.callable import ICallable
from zs.ast import resolved
from zs.processing import StatefulProcessor, State
from zs.zs2miniz.import_system import ImportResult
from zs.zs2miniz.lib import CompilationContext

_T = TypeVar("_T")
_SENTINEL = object()


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


@dataclass(slots=True, frozen=True)
class Argument:
    code: list[Instruction]
    expression: resolved.ResolvedExpression
    type: TypeProtocol
    call: resolved.ResolvedFunctionCall


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
    _function_signature_compiler: "FunctionSignatureCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._function_body_compiler = FunctionBodyCompiler(compiler)
        self._function_signature_compiler = FunctionSignatureCompiler(compiler)

    @property
    def function_body_compiler(self):
        return self._function_body_compiler

    @property
    def function_signature_compiler(self):
        return self._function_signature_compiler

    def construct(self, node: resolved.ResolvedFunction) -> Function:
        fn = Function(node.name)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        return fn

    def construct_parameters(self, node: resolved.ResolvedFunction, fn: Function):
        sig = fn.signature

        if node.generic_parameters is not None:
            fn.generic_signature = GenericSignature()

            for parameter in node.generic_parameters:
                fn.generic_signature.positional_parameters.append(self.context.cache(parameter, GenericParameter(parameter.name)))

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
        with self.compiler.expression_compiler.code_context(self._function_signature_compiler):
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
    def _(self, node: resolved.ResolvedGenericParameter, item: GenericParameter):
        ...

    @_cpl
    def _(self, node: resolved.ResolvedParameter, item: Parameter):
        with self.compiler.expression_compiler.code_context(self._function_signature_compiler):
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
    _method_body_compiler: "MethodBodyCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._method_body_compiler = MethodBodyCompiler(compiler)

    @property
    def method_body_compiler(self):
        return self._method_body_compiler

    def construct(self, node: resolved.ResolvedFunction) -> Method:
        fn = Method(node.name)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        return fn

    @singledispatchmethod
    def compile(self, node: resolved.ResolvedFunction, item: IMiniZObject):
        super().compile(node, item)

    _cpl = compile.register

    @_cpl
    def _(self, node: resolved.ResolvedFunctionBody, item: FunctionBody):
        with self.compiler.expression_compiler.code_context(self._method_body_compiler):
            if node is not None:
                self.context.mark_defined(node)

                body = self.compiler.expression_compiler.compile_code(node.instructions)
                for instruction in body:
                    item.instructions.append(instruction)
            else:
                del item.instructions


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
    _stack: TypeStack

    _code_context_stack: list[CodeContext]

    _compiler: "NodeCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        self._compiler = compiler

        self._stack = TypeStack()

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
    def _(self, node: resolved.ResolvedExpressionStatement):
        return self.compile(node.expression)

    @_cpl
    def _(self, node: resolved.ResolvedFunctionCall):
        # todo: organize. this is hell. need to add callable protocol (only applies if no _{OP} method is found)

        if node.operator not in {"()", "{}", "[]"}:
            raise ValueError(f"{node.operator=}")

        fact = vm.Call

        code_analyzer = CodeAnalyzer()
        code_analyzer.add_analyzer(ResultTypeAnalyzer())

        args: list[Argument] = []
        kwargs: dict[str, Argument] = {}

        _context = {}

        for arg in node.arguments:
            arg_result = code_analyzer.analyze(self.compile_expression(arg), _context)
            args.append(Argument(
                arg_result.code,
                arg,
                arg_result.additional_information[ResultTypeAnalyzer].result_type,
                node
            ))

        for kw, arg in node.keyword_arguments.items():
            arg_result = code_analyzer.analyze(self.compile_expression(arg), _context)
            kwargs[kw] = Argument(
                arg_result.code,
                arg,
                arg_result.additional_information[ResultTypeAnalyzer].result_type,
                node
            )

        arg_types = [arg.type for arg in args]
        kwarg_types = [(kw, arg.type) for kw, arg in kwargs.items()]

        callable_result = code_analyzer.analyze(self.compile_expression(node.callable), _context)
        callable_type: TypeProtocol = callable_result.additional_information[ResultTypeAnalyzer].result_type

        del _context

        target = None

        if isinstance(callable_type, ScopeProtocol):
            implementations = callable_type.get_name('_' + node.operator)
            if implementations is None:
                ...
            elif isinstance(implementations, Function):
                target = implementations
            elif isinstance(implementations, OverloadGroup):
                overloads = implementations.get_match(arg_types, kwarg_types, strict=True)

                if not overloads:
                    overloads = implementations.get_match(arg_types, kwarg_types, recursive=True)

                if len(overloads) != 1:
                    raise TypeError(f"Can't find a suitable overload")

                target = overloads[0]

            else:
                raise TypeError(f"Member _._ must be a valid function")
        elif isinstance(callable_type, ICallable):
            item = callable_result.code[-1].object  # todo: use compile time value analyzer
            kwargs_pairs = [(key, value) for key, value in kwargs.items()]
            if node.operator == "()":
                result = callable_type.curvy_call(item, args, kwargs_pairs)
            elif node.operator == "[]":
                result = callable_type.square_call(item, args, kwargs_pairs)
            else:
                raise TypeError(f"Invalid call operator: '{node.operator}'")

            return result

        else:
            raise TypeError(f"Object of type '{callable_type}' is not callable")


        generic = None
        if target is None:
            target = self.compiler.evaluate(node.callable)

            if isinstance(target, GenericInstance):
                generic = target
                target = target.origin

            if isinstance(target, IClass):
                if node.operator == "[]":
                    generic = target.instantiate_generic(list(self.compiler.vm.run(arg.code).pop() for arg in args))
                    self.stack.push_type(generic)
                    return [vm.LoadObject(generic)]
                elif node.operator == "()":
                    self.stack.push_type(target)
                    arg_types.insert(0, target)
                    target = target.constructor
                    fact = vm.CreateInstance

            if generic is not None:
                target = generic

        if isinstance(target, (IFunction, GenericInstance)):
            ...
        elif isinstance(target, OverloadGroup):
            if node.operator == "[]":
                overloads = []
                total_args = len(arg_types) + len(kwarg_types)
                for overload in target.overloads:
                    if not overload.is_generic:
                        continue
                    if len(overload.generic_parameters) != total_args:
                        continue
                    overloads.append(overload)

                if len(overloads) != 1:
                    raise TypeError(f"Could not find a suitable overload")

                target = overloads[0]
                generic = target.instantiate_generic(list(self.compiler.vm.run(arg.code).pop() for arg in args))
                return [vm.LoadObject(generic)]

            overloads = target.get_match(arg_types, kwarg_types, strict=True)

            if not overloads:
                overloads = target.get_match(arg_types, kwarg_types, recursive=True)

            if len(overloads) != 1:
                raise ValueError("can't find suitable overload")

            target = overloads[0]
        else:
            raise TypeError(type(target))

        self.stack.apply_signature(target.signature)

        args_code = sum((arg.code for arg in args), [])
        if kwargs:
            kwargs_code = sum((kwargs[np.name].code for np in target.signature.named_parameters), [])
        else:
            kwargs_code = ()

        return [*args_code, *kwargs_code, fact(target)]

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

        tp = self.stack.top()

        assert isinstance(tp, ScopeProtocol)

        member = tp.get_name(node.member_name)

        if isinstance(member, IOOPMemberDefinition):
            assert isinstance(tp, TypeProtocol)
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

        return [vm.LoadObject(member)]

        # raise TypeError(type(member))

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

    @_cpl
    def _(self, node: resolved.ResolvedParameter):
        parameter = self.context.cache(node)
        assert isinstance(parameter, Parameter)
        self.stack.push_argument(parameter)
        return [vm.LoadArgument(parameter)]

    @_cpl
    def _(self, node: resolved.ResolvedGenericParameter):
        parameter = self.context.cache(node)
        assert isinstance(parameter, GenericParameter)
        self.stack.push_object(parameter)
        return [vm.LoadObject(parameter)]

    @_cpl
    def _(self, node: resolved.ResolvedReturn):
        return [*(self.code_compiler.compile(node.expression) if node.expression else ()), vm.Return()]


class MethodBodyCompiler(FunctionBodyCompiler):
    def compile(self, node: resolved.ResolvedNode):
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return super()._compile(node)

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedVar):
        var = self.context.cache(node)
        if isinstance(var, Field):
            self.stack.push_field(var)
            return [vm.LoadField(var)]
        return super()._compile(node)


class FunctionSignatureCompiler(CodeContext):
    def compile(self, node: resolved.ResolvedNode):
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return None

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedGenericParameter):
        parameter = self.context.cache(node)
        assert isinstance(parameter, GenericParameter)
        self.stack.push_type(parameter)
        return [vm.LoadObject(parameter)]

    @_cpl
    def _(self, node: resolved.ResolvedParameter):
        parameter = self.context.cache(node)
        assert isinstance(parameter, Parameter)
        self.stack.push_type(parameter.parameter_type)
        return [vm.LoadObject(parameter)]


class CallCompiler(CodeContext):
    def compile(self, node: resolved.ResolvedFunctionCall) -> list[Instruction]:
        ...

    @singledispatchmethod
    def _compiler(self, callee: IMiniZObject, *args: TypeProtocol, **kwargs: TypeProtocol):
        raise NotImplementedError(type(callee))


class CompilerDispatcher(StatefulProcessor):
    _compilers: dict[type, CompilerBase]

    def __init__(self, state: State):
        super().__init__(state)

        self._compilers = {}

    def register_compiler(self, cls: Type[_T], compiler: CompilerBase[_T]):
        if cls in self._compilers:
            raise TypeError(f"Type '{cls}' is already registered")
        self._compilers[cls] = compiler

    def compile(self, node: resolved.ResolvedNode, item: _T) -> _T:
        return self.dispatch(item).compile(node, item) or item

    def dispatch(self, item: _T) -> CompilerBase[_T]:
        return self._compilers[type(item)]

    @classmethod
    def standard(cls, compiler: "NodeCompiler"):
        dispatcher = cls(compiler.state)

        dispatcher.register_compiler(Function, compiler.function_compiler)
        dispatcher.register_compiler(Parameter, compiler.function_compiler)
        dispatcher.register_compiler(GenericParameter, compiler.function_compiler)
        dispatcher.register_compiler(FunctionBody, compiler.function_compiler)

        dispatcher.register_compiler(Method, compiler.class_compiler.method_compiler)
        dispatcher.register_compiler(MethodBody, compiler.class_compiler.method_compiler)
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
