import typing
from pathlib import Path
from typing import TypeVar

if typing.TYPE_CHECKING:
    from miniz.type_system import ObjectProtocol
from zs.ast.node import Node
from zs.ast.resolved import ResolvedNode
from zs.text.token import Token
from zs.zs2miniz.import_system import ImportSystem

if typing.TYPE_CHECKING:
    from miniz.concrete.module import Module
    from zs.zs_compiler import ZSCompiler

from zs.text.file_info import DocumentInfo
from zs.zs2miniz.errors import NameNotFoundError

_T = TypeVar("_T")
_U = TypeVar("_U")

_NodeT = TypeVar("_NodeT", bound=Node)


_SENTINEL = object()


class Scope(typing.Generic[_T]):
    _parent: "Scope | None"
    _items: dict[str, _T]
    _definitions: dict[str, _T]

    def __init__(self, parent: "Scope[_U] | None" = None, **items):
        self._parent = parent
        self._items = items.copy()
        self._definitions = items.copy()

    @property
    def parent(self):
        return self._parent

    @property
    def items(self):
        return list(self._items.values())

    @property
    def names(self):
        return list(self._items.items())

    @property
    def defined_items(self):
        return list(self._definitions.values())

    @property
    def defined_names(self):
        return list(self._definitions.items())

    def _assert_name_unused(self, name: str):
        if name in self._items:
            raise ValueError(f"Name '{name}' is already bound to an object '{self._items[name]}' in scope {self}")

    def create_name(self, name: str, value: _T, *, define: bool = True):
        self._assert_name_unused(name)
        self._items[name] = value
        if define:
            self._definitions[name] = value

    def delete_name(self, name: str, *, recursive_lookup: bool = False, must_exist: bool = True) -> None:
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

    def lookup_name(self, name: str, *, recursive_lookup: bool = True, default: _U | None = _SENTINEL) -> _T | _U | None:
        if name in self._items:
            return self._items[name]
        if recursive_lookup and self.parent is not None:
            return self.parent.lookup_name(name, recursive_lookup=recursive_lookup, default=default)
        if default is _SENTINEL:
            raise NameNotFoundError(f"Could not resolve name \'{name}\'.")
        return default

    def refer_name(self, name: str, value: _T):
        self.create_name(name, value, define=False)

    def __iter__(self):
        return iter(self._items.items())


class DocumentContext:
    _info: DocumentInfo
    _object_scope: Scope["ObjectProtocol"]
    _node_scope: Scope[ResolvedNode] | None
    _tokens: list[Token] | None
    _nodes: list[Node] | None
    _resolved: list[ResolvedNode] | None
    _build: list[list[ResolvedNode]] | None
    _objects: list["ObjectProtocol"] | None

    def __init__(self, info: DocumentInfo, global_scope: Scope["ObjectProtocol"] | None = None):
        self._info = info
        self._object_scope = Scope(global_scope)
        self._node_scope = self._tokens = self._nodes = self._resolved = self._build = self._objects = None

    @property
    def info(self):
        return self._info

    @property
    def object_scope(self):
        return self._object_scope

    @property
    def node_scope(self):
        return self._node_scope

    @node_scope.setter
    def node_scope(self, value):
        self._node_scope = value

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
    _scope: Scope["ObjectProtocol"]
    _modules: dict[str, "Module"]
    _documents: dict[str, DocumentContext]
    _import_system: ImportSystem

    def __init__(self, compiler: "ZSCompiler", *, isolated: bool = False):
        self._scope = Scope(compiler.context.scope if not isolated else None)
        self._modules = {}
        self._documents = {}
        self._import_system = ImportSystem(compiler, compiler.context.import_system if not isolated else None)

    @property
    def scope(self):
        return self._scope

    @property
    def import_system(self):
        return self._import_system

    def add_module(self, name: str, module: "Module", *, override: bool = False):
        if name in self._modules and not override:
            raise ValueError(f"Module \'{name}\' is already registered")
        self._modules[name] = module

    def get_module(self, name: str, *, default=_SENTINEL):
        try:
            return self._modules[name]
        except KeyError:
            if default is _SENTINEL:
                raise
            return default

    def add_document_context(self, document: DocumentContext, path: str | Path | None = None, *, override: bool = False):
        if path is None:
            path = document.info.path
        path = str(path)

        if path in self._documents and not override:
            raise ValueError(f"Document @ {path} is already added")

        self._documents[path] = document

    def create_document_context(self, path: str | Path, *, isolated: bool = False, cache: bool = True, override: bool = False):
        context = DocumentContext(DocumentInfo.from_path(path), self.scope if not isolated else None)
        if cache:
            self.add_document_context(context, override=override)
        return context

    def get_document_context(self, path: str | Path, *, default=_SENTINEL):
        try:
            return self._documents[str(path)]
        except KeyError:
            if default is _SENTINEL:
                raise
            return default


class GlobalContext(CompilationContext):
    """
    This context is shared between all Z# files executing in the current process.
    """

    def get_global(self, name: str) -> object:
        return self.scope.lookup_name(name, recursive_lookup=False)

    def del_global(self, name: str):
        self.scope.delete_name(name, recursive_lookup=False, must_exist=True)

    def set_global(self, name: str, value: "ObjectProtocol"):
        self.scope.create_name(name, value)
