""" native.py
This file contains utilities to create facade classes between the Python backend and the
Z# interpreter.
"""
import inspect
import typing
from functools import partial
from typing import Callable

from .core import Class, CallableAndBindProtocol, FunctionType, Any, Type, Unit, OverloadGroup
from .protocols import *
from .protocols import ObjectProtocol


class _NativeClassMeta(type, Class):
    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, object]):
        super().__init__(name, bases, namespace)
        base = None
        for b in bases:
            if isinstance(b, Class):
                if base is not None:
                    raise TypeError("May only inherit a single Z# class")
                base = b
        Class.__init__(cls, name, base, None, None)
        for name, item in namespace.items():
            # if getattr(item, "__zs_native_function__", False):
            _is_constructor = False
            try:
                if isinstance(item, NativeConstructor):
                    _is_constructor = True
                    item = item.function
            except NameError:
                ...
            if isinstance(item, NativeFn):
                item = py_function_to_zs_function(name, item, {
                    _Self: cls,
                    inspect.Signature.empty: Any
                })
                name = item.name
            if not isinstance(item, ObjectProtocol):
                continue
            if _is_constructor:
                cls.define_constructor(item)
            if isinstance(item, OverloadGroup):
                for overload in item.overloads:
                    method = cls.define_method(name, overload)
            if isinstance(item, NativeFunction):
                method = cls.define_method(name, item)
            elif isinstance(item, NativeField):
                cls.define_field(name, item.type, item.value)
            elif isinstance(item, Class):
                cls.define_class(name, item)

        cls.type = cls.runtime_type


class NativeFn:
    def __init__(self, fn, name: str):
        self.name = name
        self.overloads = [fn]

    def overload(self, fn):
        self.overloads.append(fn)


def py_function_to_zs_function(name, fn, transform: dict = None):
    if isinstance(fn, NativeFn):
        name = fn.name or name
        overloads = list(map(lambda o: py_function_to_zs_function(name, o, transform), fn.overloads))
        group = OverloadGroup(None, *overloads)
        group.name = name
        return group

    if not callable(fn):
        raise TypeError
    if transform is None:
        transform = {}
    sig = inspect.signature(fn)
    types = []
    for parameter in sig.parameters.values():
        annotation = parameter.annotation
        if annotation in transform:
            annotation = transform[annotation]
        if not isinstance(annotation, TypeProtocol):
            raise TypeError(f"Native function must only have Z# types as parameters")
        types.append(annotation)
    if sig.return_annotation in transform:
        return_type = transform[sig.return_annotation]
    else:
        return_type = sig.return_annotation
    fn_type = FunctionType(types, return_type)

    def wrapper(*args, **kwargs):
        nonlocal return_type

        result = fn(*args, **kwargs)
        if not isinstance(result, ObjectProtocol) or not return_type.is_instance(result):
            try:
                return return_type(result)
            except TypeError:
                return return_type.default()
        return result

    return NativeFunction(wrapper, fn_type, getattr(fn, "__zs_native_name__", name))


class NativeClass(ObjectProtocol, metaclass=_NativeClassMeta):
    def __init__(self):
        self.type = self.runtime_type = type(self)


_T = typing.TypeVar("_T")
_U = typing.TypeVar("_U")
_Self = typing.TypeVar("_Self")


class NativeField:
    def __init__(self, type: TypeProtocol, value=None, name: str = None):
        self.name = name
        self.type = type
        self.value = value or type.default()


class NativeFunction(CallableAndBindProtocol):
    name: str
    _native: Callable[..., typing.Any]
    runtime_type: FunctionType

    def __init__(self, native: Callable[..., typing.Any], type: FunctionType, name: str = None):
        self._native = native
        try:
            self.name = name or native.__name__
        except AttributeError:
            self.name = ''
        self.runtime_type = type

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        return self.invoke(*args, **kwargs)

    def invoke(self, *args, **kwargs):
        return self._native(*args, **kwargs)

    def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        if isinstance(self._native, staticmethod):
            return self
        if len(args) > len(self.runtime_type.parameters):
            raise TypeError(f"Can't bind function {self.name} to more than {len(self.runtime_type.parameters)} arguments (got {len(args)})")
        for arg, parameter in zip(args, self.runtime_type.parameters):
            if not arg.is_instance_of(parameter):
                raise TypeError(f"Can't assign argument of type {arg.runtime_type} to parameter of type {parameter}")
        return NativeFunction(partial(self._native, *args, **kwargs), FunctionType(self.runtime_type.parameters[len(args):], self.runtime_type.returns))

    def __call__(self, *args, **kwargs):
        return self.invoke(*args, **kwargs)


class NativeConstructor(ObjectProtocol):
    function: NativeFunction

    def __init__(self, function: NativeFunction):
        self.function = function


class NativeValue(NativeClass, typing.Generic[_T]):
    _native: _T

    def __init__(self, native: _T):
        super().__init__()
        self._native = native
        self.runtime_type = type(self)

    @property
    def native(self):
        return self._native

    # Python stuff

    def __str__(self):
        return str(self._native)

    def __int__(self):
        return int(self._native)

    def __bool__(self):
        return bool(self._native)

    def __float__(self):
        return float(self._native)

    def __eq__(self, other):
        return self._native == other


# interop utility


def native_fn(name_or_fn: str | Callable = None):
    def wrapper(fn):
        if not callable(fn):
            raise TypeError
        # fn.__zs_native_function__ = True
        # if name_or_fn:
        #     fn.__zs_native_name__ = name_or_fn
        # return fn
        return NativeFn(fn, name_or_fn)

    if callable(name_or_fn):
        fn_ = name_or_fn
        name_or_fn = None
        return wrapper(fn_)
    return wrapper


def native_constructor(fn: Callable[[_T], _U]):
    return NativeConstructor(native_fn(fn))


_DEFAULT = object()


def native_function(name: str = None, transform: dict = _DEFAULT):
    def wrapper(fn):
        nonlocal transform

        if not callable(fn):
            raise TypeError

        if transform is _DEFAULT:
            transform = {
                str: String,
                int: Int64,
                float: Float64,
                bool: Boolean,
                type: Type,
                None: Unit
            }

        return py_function_to_zs_function(name or fn.__name__, native_fn(fn), transform)

    return wrapper


# native types


class String(NativeValue[str]):
    @classmethod
    def default(cls):
        return cls("")

    @native_fn("_+_")
    def __add__(self: _Self, right: _Self) -> _Self:
        return String(self.native + right.native)

    @native_fn("length")
    def __len__(self):
        return Int64(len(self.native))


class Character(NativeValue[str]):
    @classmethod
    def default(cls):
        return cls('\0')

    @native_fn("_+_")
    def __add__(self: _Self, other: String) -> String:
        return self.native + other.native

    @__add__.overload
    def _(self: _Self, other: _Self) -> String:
        return self.native + other.native

    @__add__.overload
    def _(self: String, other: _Self) -> String:
        return self.native + other.native


class Int64(NativeValue[int]):
    @native_fn("_+_")
    def __add__(self: _Self, right: _Self):
        if not isinstance(right, Int64):
            raise TypeError
        return Int64(self.native + right.native)

    @__add__.overload
    def _(self: _Self, other: Character) -> Character:
        return chr(ord(other.native) + self.native)

    @__add__.overload
    def _(self: Character, other: _Self) -> Character:
        return chr(other.native + ord(self.native))

    @classmethod
    def default(cls):
        return cls(0)


class Float64(NativeValue[float]):
    @classmethod
    def default(cls):
        return cls(0.0)

    @native_fn("_+_")
    def __add__(self: _Self, right: _Self):
        return Float64(self.native + right.native)


class Boolean(NativeValue[bool]):
    @classmethod
    def default(cls):
        return cls.FALSE

    TRUE = FALSE = None


Boolean.TRUE = Boolean(True)
Boolean.FALSE = Boolean(False)

# Utility


# class NodeWrapper(NativeObject, Generic[_T]):
#     _node: _T
#
#     def __init__(self, node: _T):
#         super().__init__()
#         self._node = node
#         self.owner = None
#
#     @property
#     def node(self):
#         return self._node
#
#
# class WhileWrapper(NodeWrapper[While]):
#     ...
