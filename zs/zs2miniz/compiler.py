"""
This module defines the class that's responsible for compiling a function body from resolved AST to a list of instructions.
"""

from contextlib import contextmanager
from functools import singledispatchmethod, wraps
from typing import TypeVar, Generic, Callable

from miniz.concrete.function import FunctionBody, Function
from miniz.concrete.module import Module
from miniz.concrete.oop import Class, Field, Method
from miniz.concrete.signature import Parameter
from miniz.generic.signature import GenericParameter
from miniz.interfaces.oop import IClass
from miniz.type_system import Any, is_type
from miniz.vm import instructions as vm
from zs.ast.resolved import ResolvedNode, ResolvedClass, ResolvedModule, ResolvedVar, ResolvedFunction, ResolvedParameter
from zs.ast import resolved as res
from zs.processing import StatefulProcessor, State
from zs.zs2miniz.lib import Scope, DocumentContext


_T = TypeVar("_T")
_SENTINEL = object()


class ASTCompiler(StatefulProcessor):
    _cache: dict[ResolvedNode, object] | None  # todo: ObjectProtocol
    _scope: Scope | None
    _document: DocumentContext | None

    _module_compiler: "ModuleCompiler"
    _function_compiler: "FunctionCompiler"
    _class_compiler: "ClassCompiler"

    def __init__(self, *, state: State | None = None):
        super().__init__(state or State())
        self._cache = None
        self._scope = None
        self._document = None

        self._module_compiler = ModuleCompiler(self)
        self._function_compiler = FunctionCompiler(self)
        self._class_compiler = ClassCompiler(self)

    @property
    def current_scope(self):
        return self._scope

    def compile(self, node: ResolvedNode, **kwargs):
        try:
            return self._cache[node]
        except KeyError:
            result = self._cache[node] = self._compile(node, **kwargs)
            return result

    @contextmanager
    def scope(self, parent: Scope | None = _SENTINEL, **items):
        scope, self._scope = self._scope, Scope(parent if parent is not _SENTINEL else self.current_scope, **items)
        try:
            yield self._scope
        finally:
            self._scope = scope

    @contextmanager
    def document(self, document: DocumentContext):
        self._cache = {}
        self._scope = document.scope
        self._document = document
        try:
            yield
        finally:
            self._document = self._scope = self._cache = None

    @singledispatchmethod
    def _compile(self, node: ResolvedNode, **kwargs):
        raise NotImplementedError(f"Can't compile node of type \'{type(node)}\' because it is not implemented yet")

    _cpl = _compile.register

    @staticmethod
    def _cached(fn: Callable[["ASTCompiler", _T, ...], object]):
        @wraps(fn)
        def wrapper(self: "ASTCompiler", node: _T, enable_caching: bool = True, **kwargs):
            if not enable_caching:
                return fn(self, node, **kwargs)
            try:
                return self.cache(node)
            except KeyError:
                result = fn(self, node, **kwargs)

                if node not in self._cache:
                    self.cache(node, result)

                return result

        return wrapper

    def cache(self, node: ResolvedNode, item: object = None):  # todo: ObjectProtocol
        if item is None:
            return self._cache[node]
        self._cache[node] = item

    @_cpl
    @_cached
    def _(self, node: ResolvedClass):
        return self._class_compiler.compile(node)

    @_cpl
    @_cached
    def _(self, node: ResolvedFunction, **kwargs):
        return self._function_compiler.compile(node, **kwargs)

        # if result.name:
        #     self.current_scope.create_readonly_name(result.name, result, object())

    @_cpl
    @_cached
    def _(self, node: ResolvedParameter, *, result: Parameter = None):
        if not result:
            result = Parameter(node.name)

        result.parameter_type = self.compile(node.type) if node.type is not None else Any
        result.default_value = self.compile(node.initializer) if node.initializer is not None else None

        return result

    @_cpl
    @_cached
    def _(self, node: ResolvedModule, *, result: Module = None):
        return self._module_compiler.compile(node)


class ContextualCompiler(StatefulProcessor, Generic[_T]):
    _context_item: _T | None
    _compiler: ASTCompiler

    def __init__(self, compiler: ASTCompiler):
        super().__init__(compiler.state)
        self._compiler = compiler
        self._context_item = None

    @property
    def current_context_item(self):
        return self._context_item

    @property
    def compiler(self):
        return self._compiler

    @contextmanager
    def context_item(self, item: _T):
        item, self._context_item = self._context_item, item
        try:
            with self.compiler.scope():
                yield self._context_item
        finally:
            self._context_item = item

    def compile(self, node: ResolvedNode, **kwargs) -> _T:
        try:
            return self.compiler.cache(node)
        except KeyError:
            return self._compile(node, **kwargs)

    def _compile(self, node: ResolvedNode, **_):
        raise NotImplementedError(f"Can't compile node of type \'{type(node)}\' because it is not implemented yet")


class ModuleCompiler(ContextualCompiler[Module]):
    def _compile(self, node: ResolvedModule, **_):
        with self.context_item(Module(node.name)) as module:
            self.compiler.cache(node, module)

            if module.name:
                self.compiler.current_scope.parent.create_readonly_name(module.name, module, object())

            for item in node.items:
                self._compile_item(item)

            return module

    @singledispatchmethod
    def _compile_item(self, item: ResolvedNode):
        super()._compile(item)

    _cpl = _compile_item.register

    @_cpl
    def _(self, node: ResolvedClass):
        cls = self.compiler.compile(node)
        self.current_context_item._classes.append(cls)
        return cls

    @_cpl
    def _(self, node: ResolvedFunction):
        fn = self.compiler.compile(node)
        self.current_context_item._functions.append(fn)
        return fn


class FunctionCompiler(ContextualCompiler[Function]):
    _function_body_compiler: "FunctionBodyCompiler"

    def __init__(self, compiler: ASTCompiler):
        super().__init__(compiler)

        self._function_body_compiler = FunctionBodyCompiler(compiler)

    @singledispatchmethod
    def _compile(self, node: ResolvedFunction, factory: Callable[[str], Function] = Function):
        with self.context_item(factory(node.name)) as fn:  # type: Function
            self.compiler.cache(node, fn)

            if fn.name:
                self.compiler.current_scope.parent.create_readonly_name(fn.name, fn, object())

            for parameter in node.positional_parameters:
                fn.positional_parameters.append(self._compile_parameter(parameter))

            for parameter in node.named_parameters:
                fn.named_parameters.append(self._compile_parameter(parameter))

            if node.variadic_positional_parameter:
                fn.variadic_positional_parameter = self._compile_parameter(node.variadic_positional_parameter)

            if node.variadic_named_parameter:
                fn.variadic_named_parameter = self._compile_parameter(node.variadic_named_parameter)

            fn.return_type = self.compile(node.return_type) if node.return_type is not None else Any

            if node.body is not None:
                with self._function_body_compiler.context_item(fn.body):
                    for instruction in node.body:
                        self._function_body_compiler.compile(instruction)

            return fn

    _cpl = _compile.register

    def _compile_parameter(self, node: ResolvedParameter):
        parameter_type = self.compiler.compile(node.type) if node.type else Any
        if is_type(parameter_type):
            factory = Parameter
        else:
            factory = GenericParameter
        result = factory(node.name, parameter_type)
        self.compiler.cache(node, result)
        return result


class FunctionBodyCompiler(ContextualCompiler[FunctionBody]):
    @singledispatchmethod
    def _compile(self, node: ResolvedNode):
        super()._compile(node)

    _cpl = _compile.register

    @_cpl
    def _(self, node: res.ResolvedClassCall):
        for arg in node.arguments:
            self._compile(arg)
        # todo: named args
        # todo: find suitable constructor
        cls = self.compiler.compile(node.callable)
        assert isinstance(cls, Class)
        constructor = cls.constructors[0]
        self.current_context_item.instructions.append(vm.CreateInstance(constructor))

    @_cpl
    def _(self, node: res.ResolvedFunctionCall):
        for arg in node.arguments:
            self._compile(arg)
        # todo: named args
        self.current_context_item.instructions.append(vm.Call(self.compiler.compile(node.callable)))

    @_cpl
    def _(self, node: ResolvedParameter):
        self.current_context_item.instructions.append(vm.LoadArgument(self.compiler.compile(node)))

    @_cpl
    def _(self, node: res.ResolvedReturn):
        # if self.current_context_item.return_type is Void:
        #     if node.expression is not None:
        #         raise TypeError(f"A 'void' function must not return an expression")
        if node.expression:
            self._compile(node.expression)
        self.current_context_item.instructions.append(vm.Return())


class ClassCompiler(ContextualCompiler[Class]):
    def _compile(self, node: ResolvedClass, **_):
        with self.context_item(Class(node.name)) as cls:  # type: Class
            self.compiler.cache(node, cls)

            if cls.name:
                self.compiler.current_scope.parent.create_readonly_name(cls.name, cls)

            bases = list(map(self.compiler.compile, node.bases))

            if bases:
                if isinstance(bases[0], IClass):
                    cls.base = bases[0]

                    if any(isinstance(base, IClass) for base in bases[1:]):
                        raise TypeError(f"A class may only inherit 1 class! Class \'{cls.name}\' already inherits {cls.base}")
                else:
                    cls.specifications.extend(bases)

            for item in node.items:
                self._compile_item(item)

            return cls

    @singledispatchmethod
    def _compile_item(self, node: ResolvedNode):
        super()._compile(node)

    _cpl = _compile_item.register

    @_cpl
    def _(self, node: ResolvedClass):
        cls = self.compiler.compile(node)
        self.current_context_item.nested_definitions.append(cls)
        return cls

    @_cpl
    def _(self, node: ResolvedVar):
        try:
            fld = self.compiler.cache(node)
        except KeyError:
            fld = Field(node.name)  # todo: execute expression? or maybe by build order
            if node.type:
                fld.field_type = self.compiler.compile(node.type)
        self.current_context_item.fields.append(fld)

    @_cpl
    def _(self, node: ResolvedFunction):
        fn = self.compiler.compile(node, factory=Method)
        assert isinstance(fn, Method)
        if fn.name == self.current_context_item.name:
            self.current_context_item.constructors.append(fn)
        else:
            self.current_context_item.methods.append(fn)
        return fn
