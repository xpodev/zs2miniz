""" core.py
This module defines some core types in the Z# programming language.
"""
import typing
from dataclasses import dataclass
from typing import Optional

from . import get_runtime
from .errors import NameNotFoundError, NameAlreadyExistsError, ReturnInstructionInvoked
from .protocols import ClassProtocol, TypeProtocol, ObjectProtocol, SetterProtocol, GetterProtocol, BindProtocol, CallableTypeProtocol, CallableProtocol
from miniz.interfaces.base import ScopeProtocol
from ..utils import SingletonMeta

__all__ = [
    "Any",
    "CallableAndBindProtocol",
    "Class",
    "ClassType",
    "FunctionType",
    "Module",
    "Null",
    "Nullable",
    "Object",
    "Scope",
    "Type",
    "TypeClass",
    "TypeClassImplementation",
    "Unit",
    "Void",
]

_T = typing.TypeVar("_T")


# Special Types


class _TypeType(TypeProtocol, metaclass=SingletonMeta):
    """
    The `type` type. This type is the base class of all Z# types.
    """

    def __init__(self):
        self.runtime_type = self

    def assignable_from(self, source: "TypeProtocol") -> bool:
        return isinstance(source, TypeProtocol)

    def __repr__(self):
        return "type"


Type = _TypeType()
del _TypeType


class _VoidType(TypeProtocol, metaclass=SingletonMeta):
    """
    The `void` type. This type doesn't have any instances.
    """

    def __init__(self):
        self.runtime_type = Type

    def assignable_to(self, target: "TypeProtocol") -> bool:
        return False

    def assignable_from(self, _: "TypeProtocol") -> bool:
        return False

    def __repr__(self):
        return "void"


Void = _VoidType()
del _VoidType


class _UnitType(TypeProtocol, metaclass=SingletonMeta):
    """
    The `unit` type. This type only has 1 instance, the unit instance `()`.
    """

    class _Unit(ObjectProtocol, metaclass=SingletonMeta):
        def __init__(self, unit_type: "_UnitType"):
            self.runtime_type = unit_type

        def __str__(self):
            return "()"

    Instance = None

    def __init__(self):
        if self.Instance is None:
            _UnitType.Instance = self._Unit(self)
        self.runtime_type = Type

    def default(self) -> ObjectProtocol:
        return self.Instance

    def __repr__(self):
        return "unit"


Unit = _UnitType()
del _UnitType


class _BoolType(TypeProtocol, metaclass=SingletonMeta):
    """
    The `bool` type. This type has exactly 2 instances: `true` and `false`.
    """

    class _Boolean(ObjectProtocol):
        def __init__(self, bool_type: "_BoolType", value: bool):
            self.runtime_type = bool_type
            self.__value = value

        def __str__(self):
            return "true" if self is self.__value else "false"

    TRUE: _Boolean = None
    FALSE: _Boolean = None

    def __init__(self):
        if self.TRUE is None:
            _BoolType.TRUE = self._Boolean(self, True)
        if self.FALSE is None:
            _BoolType.FALSE = self._Boolean(self, False)
        self.runtime_type = Type

    def default(self) -> ObjectProtocol:
        return self.FALSE

    def __repr__(self):
        return "bool"


Bool = _BoolType()
del _BoolType


class _AnyType(TypeProtocol, metaclass=SingletonMeta):
    """
    The `any` type. This type is compatible with all Z# types (ObjectProtocol).
    """

    class _Undefined(ObjectProtocol):
        def __init__(self, undefined_type: "_AnyType"):
            self.runtime_type = undefined_type

        def __repr__(self):
            return "undefined"

    Undefined = None

    def __init__(self):
        if self.Undefined is None:
            _AnyType.Undefined = self._Undefined(self)
        self.runtime_type = Type

    def get_name(self, name: str, instance: ObjectProtocol):
        return instance.runtime_type.get_name(name, instance=instance)

    def is_instance(self, instance: ObjectProtocol) -> bool:
        return isinstance(instance, ObjectProtocol)

    def assignable_to(self, target: "TypeProtocol") -> bool:
        return target is self

    def assignable_from(self, source: "TypeProtocol") -> bool:
        return isinstance(source, TypeProtocol)

    def default(self) -> ObjectProtocol:
        return self.Undefined

    def __repr__(self):
        return "any"


Any = _AnyType()
del _AnyType


class _NullType(TypeProtocol, metaclass=SingletonMeta):
    """
    The type of the `null` value. This value is places in the bottom of the inheritance tree and can
    be case to all object types.
    """

    class _Null(ObjectProtocol, metaclass=SingletonMeta):
        def __init__(self, null_type: "_NullType"):
            super().__init__()
            self.runtime_type = null_type

        def __str__(self):
            return "null"

    Instance: _Null = None

    def __init__(self):
        super().__init__()
        if self.Instance is None:
            _NullType.Instance = self._Null(self)
        self.runtime_type = Type

    def __repr__(self):
        return "nulltype"


Null = _NullType()
del _NullType


class Union(TypeProtocol):
    """
    The `union` type. This type can be constructed by the or operator: `int | string`
    """

    types: tuple[TypeProtocol, ...]

    def __init__(self, *types: TypeProtocol):
        self.types = types
        self.runtime_type = Type

    def assignable_from(self, source: "TypeProtocol") -> bool:
        return any(map(source.assignable_to, self.types))


class Tuple(ObjectProtocol):
    items: tuple[ObjectProtocol, ...]
    runtime_type: "TupleType"

    def __init__(self, *args: ObjectProtocol):
        self.items = args
        self.runtime_type = TupleType(*map(lambda t: t.runtime_type, args))


class TupleType(Tuple, TypeProtocol):
    """
    The `tuple` type. This type can be constructed with a tuple literal: `(int, string)`
    """

    items: tuple[TypeProtocol, ...]

    def __init__(self, *args: TypeProtocol):
        if all(map(lambda t: t is Type, args)):
            self.items = args
            self.runtime_type = self
        else:
            super().__init__(*args)

    def assignable_from(self, source: "TypeProtocol") -> bool:
        # todo: packed protocol

        if not isinstance(source, TupleType):
            return False

        if len(self.items) != len(source.items):
            return False

        return all(map(lambda ts: ts[1].assignable_to(ts[0]), zip(self.items, source.items)))

    def default(self) -> ObjectProtocol:
        return Tuple(*map(lambda t: t.default(), self.items))


class FunctionType(CallableTypeProtocol):
    def __init__(self, parameters: list[TypeProtocol], returns: TypeProtocol):
        self.parameters = parameters
        self.returns = returns
        self.runtime_type = Type

    def assignable_from(self, source: "TypeProtocol") -> bool:
        if not isinstance(source, CallableTypeProtocol):
            return False

        return self.compare_type_signature(source)

    def get_type_of_call(self, types: list[TypeProtocol]) -> TypeProtocol:
        if len(types) != len(self.parameters):
            raise TypeError
        for type, parameter in zip(types, self.parameters):
            if not type.assignable_to(parameter):
                raise TypeError
        return self.returns

    def compare_type_signature(self, other: CallableTypeProtocol) -> bool:
        try:
            if not other.get_type_of_call(self.parameters).assignable_to(self.returns):
                return False
        except TypeError:
            return False

        return True


# End Special Types


class CallableAndBindProtocol(CallableProtocol, BindProtocol):
    ...


class DefaultCallableProtocol(CallableAndBindProtocol):
    def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        return _PartialCallImpl(self, args, kwargs)


class _PartialCallImpl(DefaultCallableProtocol):
    callable: CallableProtocol
    args: list[ObjectProtocol]

    class _PartialCallImplType(CallableTypeProtocol):
        def __init__(self, bound: list[TypeProtocol], origin: CallableTypeProtocol):
            self.bound = bound
            self.origin = origin

        def get_type_of_application(self, types: list[TypeProtocol]) -> TypeProtocol:
            return self.origin.get_type_of_call(self.bound + types)

        def compare_type_signature(self, other: "CallableProtocol") -> bool:
            return other.runtime_type.compare_type_signature(self.origin)

    def __init__(self, callable_: CallableProtocol, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol], type: CallableTypeProtocol):
        self.callable = callable_
        self.args = args
        self.kwargs = kwargs
        # self.runtime_type = self._PartialCallImplType(self.get_bound_argument_types(), self.callable.runtime_type)
        self.runtime_type = type

    def get_bound_argument_types(self):
        return list(map(lambda arg: arg.runtime_type, self.args))

    def get_type_of_application(self, types: list[TypeProtocol]) -> TypeProtocol:
        return self.callable.runtime_type.get_type_of_call(self.get_bound_argument_types() + types)

    def compare_type_signature(self, other: "CallableTypeProtocol") -> bool:
        return other.compare_type_signature(self.runtime_type)

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        return self.callable.call(self.args + args, {**self.kwargs, **kwargs})


class OverloadGroupType(CallableTypeProtocol):
    group: "OverloadGroup"

    def __init__(self, group: "OverloadGroup"):
        self.group = group
        self.runtime_type = Type

    def compare_type_signature(self, other: "CallableTypeProtocol") -> bool:
        return any(overload.runtime_type.compare_type_signature(other) for overload in self.group.overloads)

    def get_type_of_call(self, types: list[TypeProtocol]) -> TypeProtocol:
        overloads = self.group.get_matching_overloads_for_types(types)

        if not overloads:
            raise TypeError
        if len(overloads) > 1:
            raise TypeError

        return overloads[0].runtime_type.get_type_of_call(types)


class OverloadGroup(CallableAndBindProtocol):
    overloads: list[CallableProtocol]
    runtime_type: OverloadGroupType
    parent: "OverloadGroup | None"

    def __init__(self, parent: "OverloadGroup | None", *overloads: CallableProtocol):
        self.parent = parent
        self.overloads = list(overloads)
        self.runtime_type = OverloadGroupType(self)
        self.build()

    def add_overload(self, fn: CallableProtocol):
        self.overloads.append(fn)

    def get_matching_overloads(self, args: list[ObjectProtocol]):
        return self.get_matching_overloads_for_types(list(map(lambda arg: arg.runtime_type, args)))

    def get_matching_overloads_for_types(self, types: list[TypeProtocol]):
        result = []
        for overload in self.overloads:
            try:
                if overload.runtime_type.get_type_of_call(types):
                    result.append(overload)
            except TypeError:
                ...
            else:
                result.append(overload)
        if not result and self.parent:
            return self.parent.get_matching_overloads_for_types(types)
        return result

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        overloads = self.get_matching_overloads(args)

        if not overloads:
            raise TypeError
        if len(overloads) > 1:
            raise TypeError

        return overloads[0].call(args, kwargs)

    def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        result = []
        for overload in self.overloads:
            if not isinstance(overload, BindProtocol):
                continue
            try:
                result.append(overload.bind(args, kwargs))
            except TypeError:
                result.append(overload)
        return OverloadGroup(self.parent.bind(args, kwargs) if self.parent else None, *result)

    def build(self):
        # self.runtime_type =
        ...


@dataclass(slots=True)
class Parameter:
    _owner: "FunctionSignature"
    name: str
    _type: TypeProtocol
    default_value: ObjectProtocol | None
    _index: int

    @property
    def owner(self):
        return self._owner

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self.type = value
        self._owner.build()

    @property
    def index(self):
        return self._index


@dataclass(slots=True)
class Variable(GetterProtocol, SetterProtocol):
    name: str
    type: TypeProtocol
    value: ObjectProtocol

    def __init__(self, name: str, type: TypeProtocol, initializer: ObjectProtocol | None = None):
        self.name = name
        self.type = type
        self.value = initializer or type.default()

    def get(self):
        return self.value

    def set(self, value: ObjectProtocol):
        if not value.runtime_type.assignable_to(self.type):
            raise TypeError
        self.value = value


class FunctionSignature(ObjectProtocol):
    """
    Represents a function signature.
    Mainly used for stub functions.
    """

    runtime_type: FunctionType

    _return_type: TypeProtocol

    name: str | None
    parameters: list[Parameter]

    def __init__(self, name: str | None, return_type: TypeProtocol):
        self.name = name
        self.parameters = []
        self._return_type = return_type
        self.runtime_type = FunctionType([], return_type)

    @property
    def return_type(self):
        return self._return_type

    @return_type.setter
    def return_type(self, value):
        self._return_type = value
        self.runtime_type = FunctionType(self.runtime_type.parameters, value)

    def define_parameter(self, name: str, type: TypeProtocol, default_value: ObjectProtocol | None = None, index: int = -1):
        if index == -1:
            index = len(self.parameters)
        parameter = Parameter(self, name, type, default_value, index)
        self.parameters.insert(index, parameter)

        return parameter

    def build(self):
        self.runtime_type = FunctionType(list(map(lambda p: p.type, self.parameters)), self.return_type)


class Function(CallableAndBindProtocol):
    """
    Represents a Z# function.
    """

    class _Argument(GetterProtocol, SetterProtocol):
        parameter: Parameter
        value: ObjectProtocol

        def __init__(self, parameter: Parameter, value: ObjectProtocol):
            if not value.runtime_type.assignable_to(parameter.type):
                raise TypeError
            self.parameter = parameter
            self.value = value

        @property
        def type(self):
            return self.parameter.type

        def get(self):
            return self.value

        def set(self, value: ObjectProtocol):
            if not value.runtime_type.assignable_to(self.parameter.type):
                raise TypeError
            self.value = value

    _signature: FunctionSignature
    lexical_scope: ScopeProtocol | None

    def __init__(self, name: str, return_type: TypeProtocol, lexical_scope: ScopeProtocol | None, body: list):
        self._signature = FunctionSignature(name, return_type)
        self.lexical_scope = lexical_scope
        self.body = body  # this is currently a list of nodes, but might as well be a list of instructions

    @property
    def signature(self):
        return self._signature

    @property
    def name(self):
        return self.signature.name

    @property
    def runtime_type(self):
        return self.signature.runtime_type

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        if not self.runtime_type.get_type_of_call(list(map(lambda arg: arg.runtime_type, args))).assignable_to(self.signature.return_type):
            raise TypeError

        runtime = get_runtime()

        # todo: match arguments with parameters

        with runtime.x.frame(self):
            for parameter, argument in zip(self.signature.parameters, args):
                runtime.x.current_scope.define(parameter.name, self._Argument(parameter, argument))

            try:
                for item in self.body:
                    runtime.process(item)
                if self.signature.return_type is not Void:
                    try:
                        return self.signature.return_type.default()
                    except TypeError:
                        raise TypeError(f"Function {self} marked as non-void did not return value")
            except ReturnInstructionInvoked as e:
                return e.value

    def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        if len(args) > len(self.signature.parameters):
            raise TypeError
        for arg, parameter in zip(args, self.signature.parameters):
            if not arg.is_instance_of(parameter.type):
                raise TypeError
        return _PartialCallImpl(self, args, kwargs, FunctionType(list(map(lambda p: p.type, self.signature.parameters[len(args):])), self.signature.return_type))


class _ObjectType(ClassProtocol, metaclass=SingletonMeta):
    class Instance(ObjectProtocol):
        def __init__(self):
            self.runtime_type = Object

        def __repr__(self):
            return f"<Z# Object>"

    def get_base(self) -> "ClassProtocol | None":
        return None

    def is_subclass_of(self, base: "ClassProtocol") -> bool:
        return False

    def create_instance(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        if len(args):
            raise TypeError(f"'object type' constructor may not be called with arguments.")

        return self.Instance()

    def assignable_from(self, source: "TypeProtocol") -> bool:
        if not isinstance(source, ClassProtocol):
            return False

        return self.is_superclass_of(source)

    def __repr__(self):
        return "object"


Object = _ObjectType()
del _ObjectType


class Scope(ScopeProtocol):
    _parent: Optional[ScopeProtocol]

    class _Scope(typing.Generic[_T]):
        """
        An internal type which wraps a dictionary to allow for function overloading.

        This does not handle any other protocol except the `CallableProtocol`
        """

        _items: dict[str, _T]

        def __init__(self, owner: "Scope", **items: _T):
            self._items = items
            self._owner = owner

        def items(self):
            return self._items.items()

        def __contains__(self, key: str):
            return key in self._items

        def __getitem__(self, key: str) -> _T:
            return self._items[key]

        def __setitem__(self, key: str, value: _T):
            def _get_overload_group_parent(scope: Scope | None = self._owner.parent):
                if scope is None:
                    return None
                try:
                    parent = scope.get_name(key)
                except NameNotFoundError:
                    return None
                else:
                    if isinstance(parent, CallableProtocol):
                        parent = OverloadGroup(_get_overload_group_parent(scope.parent), parent)
                    if not isinstance(parent, OverloadGroup):
                        return _get_overload_group_parent(scope.parent)
                    return parent

            if isinstance(value, Function):
                value = OverloadGroup(_get_overload_group_parent(), value)

            if key in self._items:
                if not isinstance(value, CallableProtocol):
                    raise NameAlreadyExistsError(key, self._owner, self)
                original = self._items[key]
                if not isinstance(original, CallableProtocol):
                    raise NameAlreadyExistsError(key, self._owner, self)
                if isinstance(original, OverloadGroup):
                    if isinstance(value, OverloadGroup):
                        group = OverloadGroup(original.parent, *original.overloads, *value.overloads)
                    else:
                        group = OverloadGroup(original.parent, *original.overloads, value)
                    self._items[key] = group
                    return group.build()

                value = OverloadGroup(_get_overload_group_parent(), original, value)
            self._items[key] = value

    _items: _Scope[ObjectProtocol]
    _members: _Scope[ObjectProtocol]

    def __init__(self, parent: Optional[ScopeProtocol] = None, **items: ObjectProtocol):
        self._parent = parent
        self._items = self._Scope(self, **items)
        self._members = self._Scope(self, **items)

    @property
    def is_toplevel_scope(self):
        return self._parent is None

    @property
    def parent(self):
        return self._parent

    @property
    def items(self):
        return self._items.items()

    @property
    def members(self):
        return self._members.items()

    def get_name(self, name: str, **_):
        """
        Get a value bound to the given name in this or a parent scope.

        :raises: `NameNotFoundError` if the name doesn't exist in the current context.
        """
        if name in self._items:
            return self._items[name]
        if self.parent is None:
            raise NameNotFoundError(name, self)
        return self.parent.get_name(name)

    def define(self, name: str, value, type=None):
        self._items[name] = value
        self._members[name] = value

    def refer(self, name: str, value, type=None):
        self._items[name] = value

    def all(self) -> list[tuple[str, ObjectProtocol]]:
        return [(name, item) for name, item in self._members.items()]


class ExportScope(Scope):
    def refer(self, name: str, value):
        self._members[name] = value


class ObjectImpl:
    class CallableProtocol(CallableProtocol):
        runtime_type: "Class"

        def call(self: "Class._Instance", args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
            result = self.runtime_type.get_name("_()", instance=self)
            if not isinstance(result, CallableProtocol):
                raise TypeError
            if not isinstance(result, BindProtocol):
                return result.call([self, *args], kwargs)
            return result.bind([self], {}).call(args, kwargs)


class Class(ClassProtocol, ScopeProtocol):
    class _Instance(ObjectProtocol):
        data: dict[str, ObjectProtocol]
        runtime_type: "Class"

        def __init__(self, runtime_type: "Class"):
            self.runtime_type = runtime_type
            self.data = {}

        def __repr__(self):
            return f"<Z# Object of type {self.runtime_type.name}>"

    class _Member(typing.Generic[_T], BindProtocol):
        _dynamic: bool
        _instance: bool

        name: str
        owner: "Class"
        original: _T | None

        def __init__(self, name: str, owner: "Class", original: _T | None = None):
            self.name = name
            self.owner = owner
            self.original = original
            self._instance = False
            self._dynamic = False

        @property
        def is_instance(self) -> bool:
            return self._instance

        @is_instance.setter
        def is_instance(self, value):
            self._instance = value

        @property
        def is_dynamic_binding(self):
            return self._dynamic

        @is_dynamic_binding.setter
        def is_dynamic_binding(self, value):
            self._dynamic = value

        @property
        def is_virtual(self):
            return self.is_dynamic_binding and self.is_instance

        @is_virtual.setter
        def is_virtual(self, value):
            if value:
                self.is_dynamic_binding = self.is_instance = True
            else:
                raise ValueError

        @property
        def is_static(self):
            return not self.is_dynamic_binding and not self.is_instance

        @is_static.setter
        def is_static(self, value):
            if value:
                self.is_dynamic_binding = self.is_instance = False
            else:
                raise ValueError

        @property
        def is_class(self):
            return self.is_dynamic_binding and not self.is_instance

        @is_class.setter
        def is_class(self, value):
            if value:
                self.is_dynamic_binding = True
                self.is_instance = False
            else:
                raise ValueError

    class _Field(_Member[Variable]):
        class _BoundField(GetterProtocol, SetterProtocol):
            instance_or_class: "Class._Instance | Class"
            name: str

            def __init__(self, instance_or_class: "Class._Instance | Class", name: str):
                self.instance_or_class = instance_or_class
                self.name = name

            def get(self):
                result = self.instance_or_class.data[self.name]
                if isinstance(result, GetterProtocol):
                    return result.get()
                return result

            def set(self, value: ObjectProtocol):
                try:
                    result = self.instance_or_class.data[self.name]
                except KeyError:
                    self.instance_or_class.data[self.name] = value
                else:
                    if isinstance(result, SetterProtocol):
                        result.set(value)

        def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
            assert not kwargs

            if self.is_static:
                return self.owner.data[self.name]
            if not args:
                return self
            instance = args[0]
            if self.is_instance:
                if not isinstance(instance, Class._Instance) or not instance.is_instance_of(self.owner):
                    raise TypeError(f"Can only bind field '{self.owner}.{self.name}' to an instance of the owning class '{self.owner}'")
                return self._BoundField(instance, self.name)
            if instance.is_instance_of(self.owner):
                instance = instance.runtime_type
            if not isinstance(instance, Class) or not instance.is_subclass_of(self.owner):
                raise TypeError(f"Can only bind class field '{self.owner}.{self.name}' to subclasses of {self.owner}")
            return self._BoundField(instance, self.name)

    class _Method(_Member[CallableAndBindProtocol], CallableProtocol):
        def __init__(self, name: str, owner: "Class", original: CallableAndBindProtocol):
            super().__init__(name, owner, original)

        @property
        def runtime_type(self):
            return self.original.runtime_type

        def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
            return self.bind(args, kwargs).call([], {})

        def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
            if self.is_static:
                return self.original.bind(args, kwargs)
            if not args:
                return self
            instance = args[0]
            if self.is_instance:
                if isinstance(instance, Class) and instance.is_subclass_of(self.owner):
                    return self
                if instance.is_instance_of(self.owner) or isinstance(self.owner, TypeClassImplementation) and instance.is_instance_of(self.owner.implemented_type):
                    return self.original.bind(args, kwargs)
                else:
                    raise TypeError(f"Can only bind method '{self.owner}.{self.name}' to an instance of the owning class '{self.owner}'")
            if instance.is_instance_of(self.owner):
                instance = instance.runtime_type
            if not isinstance(instance, Class) or not instance.is_subclass_of(self.owner):
                raise TypeError(f"Can only bind class method '{self.owner}.{self.name}' to subclasses of {self.owner}")
            return self.original.bind(args, kwargs)

    name: str | None
    base: ClassProtocol | None
    constructor: OverloadGroup

    _fields: list[_Field]
    _methods: list[_Method]

    _tc_implementations: dict["TypeClass", "TypeClassImplementation"]

    _scope: Scope

    data: dict[str, Variable]  # static fields

    def __init__(self, name: str | None = None, base: ClassProtocol | None = None, lexical_scope: ScopeProtocol | None = None, metaclass: "Class | None" = None):
        self.name = name
        self.base = base or Object

        self._fields = []
        self._methods = []
        self.data = {}

        self._scope = Scope(lexical_scope)

        self.constructor = OverloadGroup(None)
        self.runtime_type = metaclass or ClassType

        self._instance_factory = self._Instance

    def create_instance(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        instance = self._instance_factory(self)
        result = self.constructor.call([instance, *args], kwargs)
        return result if result != Unit.Instance else instance

    def get_base(self) -> "ClassProtocol":
        return self.base

    def get_name(self, name: str, instance: "Class | Class._Instance" = None) -> ObjectProtocol:
        if instance is None:
            return self._scope.parent.get_name(name)
        result = self._scope.get_name(name, instance=instance)

        return result

    def all(self) -> list[tuple[str, ObjectProtocol]]:
        return self._scope.all()

    def define(self, name: str, value: ObjectProtocol, type: TypeProtocol = None):
        type = type or value.runtime_type
        match value:
            case Function() as function:
                if name == self.name:
                    self.define_constructor(function)
                else:
                    self.define_method(name, function)
            case Variable() as variable:
                self.define_field(name, variable.type, variable.value)
            case Class() as class_:
                ...
            case _:
                self._scope.define(name, value)

    def refer(self, name: str, value: ObjectProtocol):
        self._scope.refer(name, value)

    def delete(self, name: str):
        raise TypeError(f"You may not delete values from a class")

    def on_exit(self):
        if not self.constructor.overloads:
            constructor = Function(self.name, Unit, None, [])
            constructor.signature.define_parameter("this", self)
            constructor.signature.build()
            self.define_constructor(constructor)

        bases = [self._Instance]
        # check for CallableProtocol implementation
        for method in self._methods:
            if method.name == "_()":  # call operator
                bases.append(ObjectImpl.CallableProtocol)
                break

        self._instance_factory = type(self.name or "{Anonymous}", tuple(bases), {})

    def on_typeclass_implementation(self, tc: "TypeClass", impl: "TypeClassImplementation"):
        for name, item in impl.all():
            self.define(name, item)

    # OOP Class Stuff

    def define_constructor(self, function: CallableProtocol):
        self.constructor.add_overload(function)

    def define_field(self, name: str, type: TypeProtocol, initializer: ObjectProtocol = None):
        field = self._Field(name, self, Variable(name, type, initializer))
        field.is_instance = True
        self._scope.define(name, field)
        self._fields.append(field)

    def define_method(self, name: str, function: CallableAndBindProtocol):
        method = self._Method(name, self, function)
        method.is_instance = True
        self._scope.define(name, method)
        self._methods.append(method)
        return method

    def define_class(self, name: str, class_: ClassProtocol):
        ...

    # End OOP Class Stuff

    def __repr__(self):
        return f"<Z# Class {self.name}>" if self.name else "<{Anonymous} Z# Class>"


class _ClassType(Class, CallableTypeProtocol, metaclass=SingletonMeta):
    def __init__(self):
        super().__init__("Class", Object, None, self)

    def get_base(self) -> "ClassProtocol | None":
        return Object

    def assignable_from(self, source: "TypeProtocol") -> bool:
        if isinstance(source, CallableTypeProtocol):
            return self.compare_type_signature(source)
        return super().assignable_from(source)

    def compare_type_signature(self, other: "CallableTypeProtocol") -> bool:
        return self.constructor.runtime_type.compare_type_signature(other)

    def get_type_of_call(self, types: list[TypeProtocol]) -> TypeProtocol:
        return self.constructor.runtime_type.get_type_of_call(types)

    def get_name(self, name: str, instance: "Class" = None) -> ObjectProtocol:
        if isinstance(instance, Class):
            return instance.get_name(name, instance)


ClassType = _ClassType()
del _ClassType


class Nullable(TypeProtocol):
    type: TypeProtocol

    def __init__(self, type: TypeProtocol):
        if not isinstance(type, _ObjectType):
            raise TypeError("Nullables may only be used with class types")
        self.type = type
        self.runtime_type = Type

    def assignable_from(self, source: "TypeProtocol") -> bool:
        if source is Null:
            return True

        return source.assignable_to(self.type)

    def default(self) -> ObjectProtocol:
        return Null.Instance


class TypeClass(Class):
    class _TypeClassImplementationInfo:
        type: TypeProtocol
        implementation: "TypeClassImplementation"
        type_class: "TypeClass"

        def __init__(self, type: TypeProtocol, implementation: "TypeClassImplementation", type_class: "TypeClass"):
            self.type = type
            self.implementation = implementation
            self.type_class = type_class

    _implementations: dict[TypeProtocol, _TypeClassImplementationInfo]

    def __init__(self, name: str, base: "TypeClass | None", lexical_scope: ScopeProtocol):
        if base and not isinstance(base, TypeClass):
            raise TypeError(f"typeclasses may only inherit other typeclasses")
        super().__init__(name, base, lexical_scope)
        self._implementations = {}

    def assignable_from(self, source: "TypeProtocol") -> bool:
        return source in self._implementations

    def get_name(self, name: str, instance: ObjectProtocol = None):
        if instance is None:
            return super().get_name(name)
        try:
            return self._implementations[instance.runtime_type].implementation.get_name(name, instance)
        except KeyError:
            raise TypeError(f"type {instance.runtime_type} does not implement typeclass {self.name}")

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        if len(args) != 1:
            raise TypeError(f"Parameterized typeclasses are not yet implemented")
        type = args[0]
        if not isinstance(type, TypeProtocol):
            raise TypeError(f"May only get typeclass implementation for a type")
        return self._implementations[type].implementation

    def add_implementation(self, type: TypeProtocol, implementation: "TypeClassImplementation"):
        if type in self._implementations:
            raise TypeError(f"type '{type}' already implements '{self}'")
        self._implementations[type] = self._TypeClassImplementationInfo(type, implementation, self)

        try:
            type.on_typeclass_implementation(self, implementation)
        except (AttributeError, TypeError):
            ...

    def get_implementation(self, type: TypeProtocol) -> "TypeClassImplementation":
        return self._implementations[type].implementation

    def __repr__(self):
        return f"<Z# TypeClass {self.name}>" if self.name else "<{Anonymous} Z# TypeClass>"


class TypeClassImplementation(Class):
    implemented_type: TypeProtocol

    def __init__(self, name: str, lexical_scope: ScopeProtocol, implemented_type: TypeProtocol):
        super().__init__(name, None, lexical_scope)
        self.implemented_type = implemented_type

    def dispose(self):
        super().dispose()

        def _bind_to_implemented_type(member):
            if isinstance(member, self._Member):
                member.owner = self.implemented_type
            if isinstance(member, OverloadGroup):
                for overload in member.overloads:
                    _bind_to_implemented_type(overload)

        _ = [*map(_bind_to_implemented_type, self._scope.members.mapping.values())]


class ModuleType(TypeProtocol, ScopeProtocol):
    def get_name(self, name: str, instance: "Module" = None, **_) -> ObjectProtocol:
        if not isinstance(instance, Module):
            raise TypeError
        return instance.get_name(name, instance=instance, **_)


class Module(ObjectProtocol, ScopeProtocol):
    """
    A class that represents a Z# module.
    """

    _scope: Scope

    name: str
    entry_point: CallableProtocol | None

    runtime_type = ModuleType()

    def __init__(self, name: str, lexical_scope: ScopeProtocol | None, entry_point: CallableProtocol | None = None):
        self.name = name
        self.entry_point = entry_point
        self._scope = Scope(lexical_scope)

    def define(self, name: str, value: ObjectProtocol):
        self._scope.define(name, value)

    def refer(self, name: str, value: ObjectProtocol):
        self._scope.refer(name, value)

    def get_name(self, name: str, **_) -> ObjectProtocol:
        return self._scope.get_name(name, **_)

    def all(self) -> list[tuple[str, ObjectProtocol]]:
        return self._scope.all()

    def on_exit(self):
        ...

    def __repr__(self):
        return f"<Z# Module {self.name if self.name else '{Anonymous}'}>"
