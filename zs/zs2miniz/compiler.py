"""
This module defines the class that's responsible for compiling a function body from resolved AST to a list of instructions.
"""

from contextlib import contextmanager
from functools import singledispatchmethod
from typing import TypeVar, Generic, Type

from miniz.generic.oop import GenericClassInstance
from miniz.interfaces.overloading import Argument
from utilz.analysis import CodeAnalyzer
from utilz.analysis.analyzers import ResultTypeAnalyzer
from miniz.concrete.function import FunctionBody, Function, Local
from miniz.concrete.module import Module
from miniz.concrete.oop import Class, Field, Method, MethodBody
from miniz.concrete.overloading import OverloadGroup
from miniz.concrete.signature import Parameter
from miniz.core import TypeProtocol, ScopeProtocol, ObjectProtocol
from miniz.generic import GenericSignature, GenericParameter
from miniz.interfaces.base import IMiniZObject
from miniz.interfaces.function import IFunction
from miniz.interfaces.module import IModule
from miniz.interfaces.oop import IClass, IField, IInterface, ITypeclass, IStructure, IProperty, IOOPDefinition
from miniz.type_system import Any, String, Boolean, Void
from miniz.vm import instructions as vm
from miniz.vm.instruction import Instruction
from miniz.vm.runtime import Interpreter
from miniz.vm.type_stack import TypeStack
from utilz.analysis.analyzers.return_type_analyzer import ReturnTypeAnalyzer
from utilz.callable import ICallable
from utilz.code_generation.core import CodeGenerationResult
from utilz.code_generation.code_objects import BoundMemberCode, LoopingCode
from utilz.debug.file_info import Span
from utilz.pattern_matching import patterns, IPattern
from utilz.scope import IScope
from zs.ast import resolved
from zs.processing import StatefulProcessor, State
from zs.utils import SingletonMeta
from zs.zs2miniz.debug import DebugDatabase, DebugContext
from zs.zs2miniz.errors import CodeCompilationError, OverloadMatchError
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

    def cache(self, node: resolved.ResolvedNode, item: _T | None = _SENTINEL, *, default=_SENTINEL) -> _T:
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


class VarDeclaration(resolved.ResolvedNode[resolved.Var]):
    def __init__(self, var: Local, node: resolved.ResolvedVar):
        super().__init__(node.node)
        self.resolved = node
        self.var = var


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

    @property
    def body_compiler(self):
        return self.function_body_compiler

    def construct(self, node: resolved.ResolvedFunction) -> Function:
        fn = Function(node.name)

        if isinstance(node.node.name, resolved.Literal):
            self.compiler.add_operator_function(fn.name, fn)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        new_body = []

        for item in node.body.instructions:
            if isinstance(item, resolved.ResolvedVar):
                new_body.append(VarDeclaration(self.construct_local(item, fn), item))
            else:
                new_body.append(item)

        node.body.instructions = new_body

        self.compiler.debug_context.debug_database.create_debug_information(fn.body, self.compiler.compilation_context.current_document.info)

        return fn

    def construct_local(self, node: resolved.ResolvedVar, fn: Function) -> Local:
        local = self.context.cache(node, Local(node.name, Any))

        fn.locals.append(local)

        return local

    def construct_parameters(self, node: resolved.ResolvedFunction, fn: Function):
        sig = fn.signature

        if node.generic_parameters is not None:
            fn.generic_signature = GenericSignature()

            for parameter in node.generic_parameters:
                fn.generic_signature.positional_parameters.append(self.context.cache(parameter, GenericParameter(parameter.name)))

        for parameter in node.positional_parameters:
            sig.positional_parameters.append(self.context.cache(parameter, Parameter(parameter.name)))

        for parameter in node.named_parameters:
            sig.named_parameters.append(self.context.cache(parameter, Parameter(parameter.name)))

        if node.variadic_positional_parameter:
            sig.variadic_positional_parameter = self.context.cache(node.variadic_positional_parameter, Parameter(node.variadic_positional_parameter.name))

        if node.variadic_named_parameter:
            sig.variadic_named_parameter = self.context.cache(node.variadic_positional_parameter, Parameter(node.variadic_named_parameter.name))

    @singledispatchmethod
    def compile(self, node: resolved.ResolvedFunction, item: IMiniZObject):
        super().compile(node, item)

    _cpl = compile.register

    @_cpl
    def _(self, node: resolved.ResolvedFunction, item: Function) -> None:
        with self.compiler.expression_compiler.code_context(self._function_signature_compiler):
            if node.return_type is not None:
                item.signature.return_type = self.compiler.evaluate(node.return_type)
            if item.return_type is None:
                item.signature.return_type = Any

    @_cpl
    def _(self, node: resolved.ResolvedFunctionBody, item: FunctionBody):
        with self.compiler.expression_compiler.code_context(self.body_compiler):
            if node is not None:
                self.context.mark_defined(node)

                with self.compiler.debug_context.function_body(item):
                    for instruction in node.instructions:
                        instructions = self.compiler.expression_compiler.compile(instruction)
                        if instructions:
                            item.instructions.extend(instructions.code)

                if node.owner.return_type is None:
                    possible_types = ReturnTypeAnalyzer.quick_analysis(item.instructions, {}).possible_return_types
                    if len(possible_types) != 1:
                        raise CodeCompilationError(f"Can't currently handle more than 1 path in a function", node.owner.node.return_type)
                    item.owner.signature.return_type = possible_types[0]
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

    @_cpl
    def _(self, node: resolved.ResolvedVar, item: Local):
        if node.type:
            with self.compiler.expression_compiler.code_context(self._function_signature_compiler):
                item.target_type = self.compiler.evaluate(node.type)
        else:
            with self.compiler.expression_compiler.code_context(self._function_body_compiler):
                if node.initializer:
                    with self.compiler.debug_context.function(item.owner):
                        init = self.compiler.expression_compiler.compile_expression(node.initializer)
                    item.target_type = ResultTypeAnalyzer.quick_analysis(init, {}).result_type
                else:
                    raise CodeCompilationError(f"Variable '{node.name}' must either have a type or an initializer", node.node)


class MethodCompiler(FunctionCompiler):
    _method_body_compiler: "MethodBodyCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self._method_body_compiler = MethodBodyCompiler(compiler)

    @property
    def method_body_compiler(self):
        return self._method_body_compiler

    @property
    def body_compiler(self):
        return self.method_body_compiler

    def construct(self, node: resolved.ResolvedFunction) -> Method:
        fn = Method(node.name)

        if isinstance(node.node.name, resolved.Literal):
            self.compiler.add_operator_function(fn.name, fn)

        self.construct_parameters(node, fn)

        self.context.cache(node.body, fn.body)

        new_body = []

        for item in node.body.instructions:
            if isinstance(item, resolved.ResolvedVar):
                new_body.append(VarDeclaration(self.construct_local(item, fn), item))
            else:
                new_body.append(item)

        node.body.instructions = new_body

        self.compiler.debug_context.debug_database.create_debug_information(fn.body, self.compiler.compilation_context.current_document.info)

        return fn

    @singledispatchmethod
    def compile(self, node: resolved.ResolvedFunction, item: IMiniZObject):
        super().compile(node, item)

    _cpl = compile.register


class ClassCompiler(CompilerBase[Class]):
    method_compiler: MethodCompiler

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)

        self.method_compiler = MethodCompiler(compiler)

    def construct(self, node: resolved.ResolvedClass) -> Class:
        cls = Class(node.name)

        if node.generic:
            cls.make_generic()
            for generic in node.generic:
                cls.generic_parameters.append(self.context.cache(generic, GenericParameter(generic.name)))

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
        if item.has_generic_parameters:
            with self.compiler.expression_compiler.code_context(self.compiler.generic_context_compiler):
                bases = list(map(self.compiler.evaluate, node.bases))
        else:
            bases = list(map(self.compiler.evaluate, node.bases))

        if bases:
            if isinstance(bases[0], (IClass, GenericClassInstance)):
                item.base = bases.pop(0)

            for base in bases:
                if not isinstance(base, (IInterface, ITypeclass, IStructure)):
                    raise TypeError
                item.specifications.append(base)

    @_cpl
    def _(self, node: resolved.ResolvedVar, item: Field):
        owner = item.owner
        while True:
            if owner.has_generic_parameters:
                break
            if not isinstance(owner.owner, IOOPDefinition):
                break
            owner = owner.owner
        if owner.has_generic_parameters:
            with self.compiler.expression_compiler.code_context(self.compiler.generic_context_compiler):
                item.field_type = self.compiler.evaluate(node.type)
        else:
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

    @property
    def debug(self):
        return self.compiler.debug_context

    def compile(self, node: resolved.ResolvedNode) -> list[Instruction]:
        raise NotImplementedError


class CodeCompiler:
    _stack: TypeStack

    _code_context_stack: list[CodeContext]

    _compiler: "NodeCompiler"

    _loop: "LoopBodyCompiler"

    def __init__(self, compiler: "NodeCompiler"):
        self._compiler = compiler

        self._stack = TypeStack()

        self._code_context_stack = [TopLevelCodeCompiler(self)]

        self._loop = LoopBodyCompiler(compiler)

    @property
    def compiler(self):
        return self._compiler

    @property
    def context(self):
        return self.compiler.context

    @property
    def debug(self):
        return self.compiler.debug_context

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
            code_result = self.compile(item)
            if isinstance(code_result, CodeGenerationResult):
                code_result = code_result.code
            result.extend(code_result)

        return result

    def compile_expression(self, expression: resolved.ResolvedExpression) -> list[Instruction]:
        return self.compile_code([expression])

    def compile(self, node: resolved.ResolvedNode):
        for compiler in reversed(self._code_context_stack):
            result = compiler.compile(node)
            if result is not None:
                break
        else:
            result = self._compile(node)
        if not isinstance(result, CodeGenerationResult):
            result = CodeGenerationResult(list(result))
        return result

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        raise TypeError(f"Default code compiler can't compile node of type '{type(node)}'")

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedAssign):
        pattern = self.compiler.pattern_constructor.get_pattern_for(node.left)

        code = self.compile_expression(node.right)

        result = pattern.match(CodeGenerationResult(code), target=self.compile(node.left))

        return result.code

    @_cpl
    def _(self, node: resolved.ResolvedBinary):
        group = self.compiler.get_operator_function(f"_{node.operator}_")

        left = self.compile_expression(node.left)
        right = self.compile_expression(node.right)

        _context = {}

        args = [
            Argument(left, ResultTypeAnalyzer.quick_analysis(left, _context).result_type),
            Argument(right, ResultTypeAnalyzer.quick_analysis(right, _context).result_type),
        ]

        del _context

        assert isinstance(group.runtime_type, ICallable)

        try:
            return group.runtime_type.curvy_call(self.compiler, CodeGenerationResult([vm.LoadObject(group)]), args, [])
        except OverloadMatchError as e:
            raise CodeCompilationError(f"Could not find a suitable overload for operator '{node.operator}' with types ({e.types})", node.node)

    @_cpl
    def _(self, node: resolved.ResolvedBlock):
        result = []

        # nop = vm.NoOperation()
        # self.debug.emit(nop, node.node.token_info.left_bracket)
        # result.append(nop)

        for item in node.body:
            code = self.compile(item).code
            result.extend(code)

            # self.debug.emit(code[0], node.node)

        # nop = vm.NoOperation()
        # self.debug.emit(nop, node.node.token_info.left_bracket)
        # result.append(nop)

        return result

    @_cpl
    def _(self, node: resolved.ResolvedClass):
        cls = self.context.cache(node)
        self._stack.push_object(cls)
        return [vm.LoadObject(cls)]

    @_cpl
    def _(self, node: resolved.ResolvedExpressionStatement):
        try:
            code = self.compile(node.expression).code
            result_type = ResultTypeAnalyzer.quick_analysis(code, {}).result_type
            if result_type is not Void:
                code.append(vm.Pop())
            self.debug.emit(code[0], node.node.span)
            return code
        except CodeCompilationError as e:
            self.compiler.state.error(e.message, e.node)
            raise e
            # return ()

    @_cpl
    def _(self, node: resolved.ResolvedFunctionCall):
        if node.operator not in {"()", "{}", "[]"}:
            raise CodeCompilationError(f"Call operator '{node.operator}' is invalid.", node.node)

        code_analyzer = CodeAnalyzer()
        code_analyzer.add_analyzer(ResultTypeAnalyzer())

        args: list[Argument] = []
        kwargs: dict[str, Argument] = {}

        _context = {}

        for arg in node.arguments:
            arg_result = code_analyzer.analyze(self.compile_expression(arg), _context)
            args.append(Argument(
                arg_result.code,
                arg_result.additional_information[ResultTypeAnalyzer].result_type
            ))

        for kw, arg in node.keyword_arguments.items():
            arg_result = code_analyzer.analyze(self.compile_expression(arg), _context)
            kwargs[kw] = Argument(
                arg_result.code,
                arg_result.additional_information[ResultTypeAnalyzer].result_type
            )

        callable_code = self.compile(node.callable)
        if isinstance(callable_code, BoundMemberCode):
            callable_type = callable_code.member.runtime_type
        else:
            callable_type: TypeProtocol = code_analyzer.analyze(callable_code.code, _context).additional_information[ResultTypeAnalyzer].result_type

        del _context

        if not isinstance(callable_type, ICallable):
            raise CodeCompilationError(f"Object of type '{callable_type}' is not callable", node.node)

        kwargs_pairs = [(key, value) for key, value in kwargs.items()]
        try:
            if node.operator == "()":
                result = callable_type.curvy_call(self.compiler, callable_code, args, kwargs_pairs)
            elif node.operator == "[]":
                result = callable_type.square_call(self.compiler, callable_code, args, kwargs_pairs)
            else:
                raise CodeCompilationError(f"Invalid call operator: '{node.operator}'", node.node)
        except OverloadMatchError as e:
            raise CodeCompilationError(f"Could not find a suitable overload for function '{e.group.name}' with types ({e.types})", node.node)

        if not isinstance(result, CodeGenerationResult):
            result = [vm.LoadObject(result)]
            # self.debug.emit(result.code[0], node.node)

        return result

    @_cpl
    def _(self, node: resolved.ResolvedIf):
        condition = self.compile_expression(node.condition)

        self.debug.emit(condition[0], Span.combine(node.node.token_info.keyword_if.span, node.node.token_info.right_parenthesis.span))

        result_type = ResultTypeAnalyzer.quick_analysis(condition, {}).result_type

        if result_type is not Boolean:
            # todo: this is also ugly
            arg = Argument(condition, result_type)
            assert isinstance(result_type, ScopeProtocol)
            to_bool = result_type.get_name("->bool")
            assert isinstance(to_bool.runtime_type, ICallable)
            result = to_bool.runtime_type.curvy_call(self.compiler, CodeGenerationResult([vm.LoadObject(to_bool)]), [arg], [])
            condition = result.code

        if_true = self.compile(node.if_body).code
        false_start = false_end = vm.NoOperation()
        if node.else_body:
            if_false = self.compile(node.else_body).code
            false_start = if_false[0]
            end = node.node.if_false
        else:
            if_false = ()
            end = node.node.if_true

        if isinstance(end, resolved.Block):
            self.debug.emit(false_end, node.node.if_false.token_info.right_bracket)

        return [
            *condition,
            vm.JumpIfFalse(false_start),
            *if_true,
            vm.Jump(false_end),
            *if_false,
            false_end
        ]

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
        code = self.compile_expression(node.object)

        result_type = ResultTypeAnalyzer.quick_analysis(code, {}).result_type

        if not isinstance(result_type, IScope):
            raise CodeCompilationError(f"{result_type} does not implement the IScope typeclass", node.node)

        result = result_type.get_member(CodeGenerationResult(code), node.member_name)

        return result

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

    @_cpl
    def _(self, node: resolved.ResolvedWhile):
        condition = self.compile_expression(node.condition)

        self.debug.emit(condition[0], Span.combine(node.node.token_info.keyword_while.span, node.node.token_info.right_parenthesis.span))

        result_type = ResultTypeAnalyzer.quick_analysis(condition, {}).result_type

        if result_type is not Boolean:
            # todo: this is also ugly
            arg = Argument(condition, result_type)
            assert isinstance(result_type, ScopeProtocol)
            to_bool = result_type.get_name("->bool")
            assert isinstance(to_bool.runtime_type, ICallable)
            result = to_bool.runtime_type.curvy_call(self.compiler, to_bool, [arg], [])
            condition = result.code

        # cpl = LoopBodyCompiler(...)
        with self.code_context(self._loop), self._loop.node(node) as ctx:
            if_true = [ctx.continue_target]
            if_true.extend(self.compile(node.while_body).code)
            if node.else_body:
                if_false = self.compile(node.else_body).code
                if_false.append(ctx.break_target)
            else:
                if_false = [ctx.break_target]

        return [
            *condition,
            vm.JumpIfFalse(if_false[0]),
            *if_true,
            vm.Jump(condition[0]),
            *if_false
        ]


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

        if self.state.has_errors:
            return

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
            raise CodeCompilationError(f"Import source must be a string", node.node)

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
    def _(self, node: resolved.ResolvedVar):
        local = self.context.cache(node)
        assert isinstance(local, Local)
        self.stack.push_local(local)
        return [
            vm.LoadLocal(local)
        ]

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
        if node.expression:
            result = self.code_compiler.compile(node.expression)
            if isinstance(result, CodeGenerationResult):
                result = result.code
        else:
            result = (vm.NoOperation(),)
        result = [*result, vm.Return()]
        self.debug.emit(result[0], node.node)
        return result

    @_cpl
    def _(self, node: VarDeclaration):
        if node.resolved.initializer:
            code = self.code_compiler.compile(node.resolved.initializer)
            if isinstance(code, CodeGenerationResult):
                code = code.code
            code.append(vm.SetLocal(node.var))
            self.debug.emit(code[0], node.node)
            return code
        return []


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


class LoopBodyCompiler(CodeContext):
    _cache: dict[resolved.ResolvedNode, LoopingCode]

    def __init__(self, compiler: "NodeCompiler"):
        super().__init__(compiler)
        self._cache = {}
        self._loop = None

    @contextmanager
    def node(self, node: resolved.ResolvedNode):
        code = self._cache[node] = LoopingCode([], vm.NoOperation(), vm.NoOperation())
        loop, self._loop = self._loop, node
        try:
            yield code
        finally:
            del self._cache[node]
            self._loop = loop

    def compile(self, node: resolved.ResolvedNode):
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        return None

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedBreak):
        loop = node.loop if node.loop is not None else self._loop
        loop_code = self._cache[loop]
        jmp = vm.Jump(loop_code.break_target)
        self.debug.emit(jmp, node.node)
        return [
            jmp
        ]


class GenericContextCompiler(CodeContext):
    def compile(self, node: resolved.ResolvedNode) -> list[Instruction]:
        return self._compile(node)

    @singledispatchmethod
    def _compile(self, node: resolved.ResolvedNode):
        ...

    _cpl = _compile.register

    @_cpl
    def _(self, node: resolved.ResolvedGenericParameter):
        param = self.context.cache(node)
        assert isinstance(param, GenericParameter)
        return [
            vm.LoadObject(param)
        ]


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
        dispatcher.register_compiler(Local, compiler.function_compiler)
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


class PatternConstructor(StatefulProcessor):
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

    def get_pattern_for(self, node: resolved.ResolvedNode) -> IPattern:
        return self._get_pattern(node)

    @singledispatchmethod
    def _get_pattern(self, node: resolved.ResolvedNode):
        raise CodeCompilationError(f"Could not create a pattern for node of type '{type(node)}'", node.node)

    _ptn = _get_pattern.register

    @_ptn
    def _(self, node: resolved.ResolvedMemberAccess):
        result = self.compiler.expression_compiler.compile(node)
        assert isinstance(result, BoundMemberCode)
        match result.member:
            case IField() as item:
                return patterns.FieldPattern(item)
            case IProperty() as item:
                return patterns.PropertyPattern(item)
            case _:
                raise CodeCompilationError(f"Can't assign member of type '{type(result.member)}'", node.node)

    @_ptn
    def _(self, node: resolved.ResolvedParameter):
        item = self.context.cache(node)
        assert isinstance(item, Parameter)
        return patterns.ParameterPattern(item)

    @_ptn
    def _(self, node: resolved.ResolvedVar):
        item = self.context.cache(node)
        match item:
            case Local() as item:
                return patterns.LocalPattern(item)
            case _:
                raise CodeCompilationError(f"Target type '{type(item)}' is not implemented", node.node)


class NodeCompiler(StatefulProcessor):
    _dispatcher: CompilerDispatcher

    _vm: Interpreter
    _context: CompilerContext

    _top_level_compiler: TopLevelCompiler
    _expression_compiler: CodeCompiler

    _class_compiler: ClassCompiler
    _function_compiler: FunctionCompiler
    _module_compiler: ModuleCompiler

    _generic_context_compiler: GenericContextCompiler

    _pattern_constructor: PatternConstructor

    _debug_context: DebugContext

    def __init__(self, state: State, context: CompilationContext):
        super().__init__(state)

        self.operators: dict[str, OverloadGroup] = {}

        self._vm = Interpreter()
        self._context = CompilerContext(self)

        self._expression_compiler = CodeCompiler(self)
        self._top_level_compiler = TopLevelCompiler(self)

        self._class_compiler = ClassCompiler(self)
        self._function_compiler = FunctionCompiler(self)
        self._module_compiler = ModuleCompiler(self)

        self._generic_context_compiler = GenericContextCompiler(self)

        self._pattern_constructor = PatternConstructor(self)

        self._dispatcher = CompilerDispatcher.standard(self)

        self._compilation_context = context

        self._debug_context = DebugContext(context.parent.debug_database)

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

    @property
    def debug_context(self):
        return self._debug_context

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

    @property
    def generic_context_compiler(self):
        return self._generic_context_compiler

    @property
    def pattern_constructor(self):
        return self._pattern_constructor

    # endregion Sub-Compilers

    def add_operator_function(self, name: str, fn: IFunction):
        if name not in self.operators:
            group = self.operators[name] = OverloadGroup(name, None)
        else:
            group = self.operators[name]
        group.overloads.append(fn)

    def get_operator_function(self, name: str):
        return self.operators[name]

    def declare(self, nodes: list[resolved.ResolvedNode] | resolved.ResolvedNode) -> list[tuple[resolved.ResolvedNode, IMiniZObject]] | IMiniZObject:
        self.run()

        if not isinstance(nodes, list):
            return self.context.cache(nodes, self.top_level_compiler.construct(nodes))

        return list(map(lambda n: (n, self.declare(n)), nodes))

    def define(self, pairs: list[tuple[resolved.ResolvedNode, IMiniZObject]] | tuple[resolved.ResolvedNode, IMiniZObject]) -> list[IMiniZObject] | IMiniZObject | None:
        self.run()

        if not isinstance(pairs, list):
            return self.dispatcher.compile(*pairs)

        return list(map(lambda p: self.dispatcher.compile(*p), pairs))

    def evaluate(self, expression: resolved.ResolvedExpression):
        if expression is None:
            return None
        return self.vm.run(self.expression_compiler.compile_expression(expression)).pop(default=None)

    def get_type_from_expression(self, expression: resolved.ResolvedExpression, default=_SENTINEL):
        result = self.get_value_from_expression(expression, default=default)
        assert isinstance(result, TypeProtocol)
        return result

    def get_value_from_expression(self, expression: resolved.ResolvedExpression, default=_SENTINEL):
        result = self.expression_compiler.compile_expression(expression)
        if not isinstance(result, ObjectProtocol):
            if default is _SENTINEL:
                result = self.vm.run(result).pop()
            else:
                result = self.vm.run(result).pop(default=default)
        return result
