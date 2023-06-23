import typing
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, Generic

from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.ast.resolved import ResolvedNode
from zs.text.token import Token

if typing.TYPE_CHECKING:
    from zs.zs2miniz.toolchain import Toolchain
from zs.text.file_info import DocumentInfo
from zs.zs2miniz.errors import NameNotFoundError

_T = TypeVar("_T", bound=ObjectProtocol)
_NodeT = TypeVar("_NodeT", bound=Node)

_SENTINEL = object()


class IScopeItem:
    _owner: "Scope"
    _name: str

    def __init__(self, name: str, owner: "Scope"):
        self._name = name
        self._owner = owner

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def owner(self) -> "Scope":
        return self._owner

    def get(self):
        raise NotImplementedError

    def set(self, value: object):
        raise NotImplementedError


class TypedStorageUnit(IScopeItem):
    _value: ObjectProtocol
    _type: ...

    def __init__(self, name: str, owner: "Scope", type, value: ObjectProtocol):
        super().__init__(name, owner)
        self._value = value
        self._type = type

    @property
    def value(self):
        return self._value

    @property
    def type(self):
        return self._type

    def get(self):
        return self._value

    def set(self, value: ObjectProtocol):
        if not value.is_instance_of(self.type):
            raise TypeError
        self._value = value


class Variable(TypedStorageUnit):
    ...


class ReadOnly(TypedStorageUnit):
    def set(self, value: object):
        raise TypeError


class Scope:
    _parent: "Scope | None"
    _items: dict[str, IScopeItem]

    def __init__(self, parent: "Scope | None" = None, **items):
        self._parent = parent
        self._items = items

    @property
    def parent(self):
        return self._parent

    def _assert_name_unused(self, name: str):
        if name in self._items:
            raise ValueError(f"Name '{name}' is already bound to an object '{self._items[name].get()}' in scope {self}")

    def create_variable_name(self, name: str, value: ObjectProtocol, type) -> Variable:
        self._assert_name_unused(name)
        result = self._items[name] = Variable(name, self, value, type)
        return result

    def create_readonly_name(self, name: str, value: ObjectProtocol, type = None) -> ReadOnly:
        self._assert_name_unused(name)
        if type is None:
            type = value.runtime_type
        result = self._items[name] = ReadOnly(name, self, type, value)
        return result

    def delete_name(self, name: str, *, recursive_lookup: bool = False, must_exist: bool = True):
        if name in self._items:
            del self._items[name]
            return
        if recursive_lookup:
            if self.parent is not None:
                return self.parent.delete_name(name, recursive_lookup=recursive_lookup, must_exist=True)
            elif not must_exist:
                return
        if must_exist:
            raise NameNotFoundError(f"Could not delete name \'{name}\'.")

    def lookup_name(self, name: str, *, recursive_lookup: bool = True, default: _T = _SENTINEL) -> IScopeItem | _T:
        if name in self._items:
            return self._items[name]
        if recursive_lookup and self.parent is not None:
            return self.parent.lookup_name(name, recursive_lookup=recursive_lookup)
        if default is _SENTINEL:
            raise NameNotFoundError(f"Could not resolve name \'{name}\'.")
        return default


class DocumentContext:
    _info: DocumentInfo
    _scope: Scope
    _tokens: list[Token] | None
    _nodes: list[Node] | None
    _resolved: list[ResolvedNode] | None
    _build: list[list[ResolvedNode]] | None
    _objects: list[ObjectProtocol] | None

    def __init__(self, info: DocumentInfo, global_scope: Scope | None = None):
        self._info = info
        self._scope = Scope(global_scope)
        self._tokens = self._nodes = self._resolved = self._build = self._objects = None

    @property
    def info(self):
        return self._info

    @property
    def scope(self):
        return self._scope

    @property
    def tokens(self):
        return self._tokens

    @tokens.setter
    def tokens(self, value):
        self._tokens = value

    @property
    def nodes(self):
        return self._nodes

    @nodes.setter
    def nodes(self, value):
        self._nodes = value

    @property
    def resolved_nodes(self):
        return self._resolved

    @resolved_nodes.setter
    def resolved_nodes(self, value):
        self._resolved = value

    @property
    def build_order(self):
        return self._build

    @build_order.setter
    def build_order(self, value):
        self._build = value

    @property
    def objects(self):
        return self._objects

    @objects.setter
    def objects(self, value):
        self._objects = value


class CompilationContext:
    _documents: dict[str, DocumentContext]
    _current_document: DocumentContext | None
    _global_scope: Scope
    _scopes: list[Scope]
    _current_scope: Scope
    _toolchain: "Toolchain"

    def __init__(self, toolchain: "Toolchain", global_scope: Scope = Scope(), precompiled_documents: list[DocumentContext] = None):
        self._current_scope = self._global_scope = global_scope
        self._documents = {
            precompiled_document.info.path_string: precompiled_document
            for precompiled_document in precompiled_documents
        } if precompiled_documents is not None else {}
        self._current_document = None
        self._scopes = [global_scope]
        self._toolchain = toolchain

    @property
    def document(self):
        return self._current_document

    @property
    def global_scope(self):
        return self._global_scope

    @property
    def current_scope(self):
        return self._current_scope

    @property
    def toolchain(self):
        return self._toolchain

    @contextmanager
    def scope(self, parent: Scope | None = _SENTINEL, cls=Scope, **items):
        old, self._current_scope = self._current_scope, cls(parent if parent is not _SENTINEL else self._current_scope, **items)
        try:
            yield self._current_scope
        finally:
            self._current_scope = old

    def get_document_context(self, path: str | Path | DocumentInfo):
        try:
            return self._documents[DocumentInfo.from_path(path).path_string]
        except KeyError:
            return None

    def create_document_context(self, info: DocumentInfo | Path | str, *, global_scope: Scope = None, enable_caching: bool = True):
        info = DocumentInfo.from_path(info)
        context = DocumentContext(info, global_scope or self.global_scope)
        if enable_caching:
            self._documents[info.path_string] = context
        return context


@dataclass(slots=True, frozen=True)
class ObjectMetadata(Generic[_NodeT, _T]):
    node: _NodeT
    object: _T
    scope: Scope
