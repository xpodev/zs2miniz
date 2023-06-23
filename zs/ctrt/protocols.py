""" protocols.py
This file contains different protocols for the Python backend of Z# objects.

"""


class ObjectProtocol:
    """
    The base protocol for all Z# objects.

    Z# objects only hold data (i.e. other objects). How this data is stored is not part of the standard.

    The only thing an object has to have is a `runtime_type` attribute, which should hold the exact type
    of the object.
    """
    runtime_type: "TypeProtocol"

    def is_instance_of(self, type: "TypeProtocol") -> bool:
        """
        Returns whether this object is an instance of the given `type`
        """
        return type.is_instance(self)


class TypeProtocol(ObjectProtocol):
    """
    Protocol for objects that can behave as types. All types are also objects.

    The minimal definition of a type is a group of values. Therefore, the minimal type API is to
    tell whether a value is part of the group (i.e. `is_instance`).
    """

    def is_instance(self, instance: ObjectProtocol) -> bool:
        """
        Returns whether the given instance is an instance of this type.
        """
        return instance.runtime_type.assignable_to(self)

    def assignable_to(self, target: "TypeProtocol") -> bool:
        """
        Returns whether instances of 'this' type are assignable to the given `target` type.
        """
        return target.assignable_from(self)

    def assignable_from(self, source: "TypeProtocol") -> bool:
        """
        Returns whether this type accepts values from the given source type.
        """
        return source is self

    def default(self) -> ObjectProtocol:
        """
        The default value of the type, or raise `TypeError` if the type doesn't have a default value.
        """
        raise TypeError(f"type {self} does not have a default value")


class GetterProtocol:
    def get(self):
        """
        Get the value associated with this getter.
        """


class SetterProtocol:
    def set(self, value: ObjectProtocol):
        """
        Set the value associated with this setter to the given value.

        This method is responsible for typechecking as well.
        """


class ScopeProtocol:
    """
    Represents a scope
    """

    def get_name(self, name: str, **_) -> ObjectProtocol:
        """
        Returns the value associated with the given `name` in this scope.

        :raises NameNotFoundError: if the given name could not be found.
        """

    def all(self) -> list[tuple[str, ObjectProtocol]]:
        """
        Returns a list of pairs of (name, value) of all values defined in this scope.
        """

    def define(self, name: str, value: ObjectProtocol, type: TypeProtocol = None):
        """
        Define a new value in this scope.
        """

    def refer(self, name: str, value: ObjectProtocol, type: TypeProtocol = None):
        """
        Bind a name to a value from an external source in this scope.
        """

    def delete(self, name: str):
        """
        Delete a value bound to the given `name` in this scope.

        :raises NameNotFoundError: if the name could not be found.
        :raises TypeError: if this scope does not support deleting items.
        """

    def on_exit(self):
        """
        Called when the scope object is exited (i.e. end of scope)
        """


class CallableProtocol(ObjectProtocol):
    runtime_type: "CallableTypeProtocol"

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        """
        Apply actual values to the object.
        """


class ClassProtocol(TypeProtocol, ScopeProtocol, CallableProtocol):
    def get_base(self) -> "ClassProtocol | None": ...

    def is_subclass_of(self, base: "ClassProtocol") -> bool:
        """
        Returns whether this type is a subtype of `base`
        """
        cls = self
        while cls is not None:
            if cls == base:
                return True
            cls = cls.get_base()
        return False

    def is_superclass_of(self, child: "ClassProtocol") -> bool:
        return child.is_subclass_of(self)

    def call(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol:
        return self.create_instance(args, kwargs)

    def create_instance(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]) -> ObjectProtocol: ...


class BindProtocol:
    def bind(self, args: list[ObjectProtocol], kwargs: dict[str, ObjectProtocol]):
        """
        Returns an object that's bound to the given arguments.
        """


class CallableTypeProtocol(TypeProtocol):
    def assignable_from(self, source: "TypeProtocol") -> bool:
        if not isinstance(source, CallableTypeProtocol):
            raise TypeError

        return self.compare_type_signature(source)

    def compare_type_signature(self, other: "CallableTypeProtocol") -> bool:
        """
        Returns whether this callable has the same type signature as the given callable.
        """

    def get_type_of_call(self, types: list[TypeProtocol]) -> TypeProtocol:
        """
        Returns the result type when called with the given types.

        :raises TypeError: if the types given do not match this callable's type.
        """
