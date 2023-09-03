from pathlib import Path
from typing import Iterable

from miniz.core import ObjectProtocol, TypeProtocol, ScopeProtocol
from zs.zs2miniz.import_system import Importer, ImportSystem
from zs.zs2miniz.lib import DocumentContext


class ZSImportResult(ScopeProtocol):
    _document: DocumentContext
    _items: dict[str, tuple[TypeProtocol, ObjectProtocol]]

    def __init__(self, document: DocumentContext):
        super().__init__()
        self._document = document
        self._items = dict(document.object_scope)

    def all(self) -> Iterable[tuple[str, tuple[TypeProtocol, ObjectProtocol]]]:
        for name, item in self._items.items():
            yield name, item

    def get_name(self, name: str, **_) -> tuple[TypeProtocol, ObjectProtocol]:
        return self._items[name]


class ZSImporter(Importer):
    _import_system: ImportSystem

    def __init__(self, import_system: ImportSystem):
        super().__init__()
        self._import_system = import_system

    def import_from(self, source: str) -> ScopeProtocol | None:
        return self.import_file(Path(source))

    def import_file(self, path: Path) -> ScopeProtocol | None:
        path = self._import_system.resolve(path)

        if path is None:
            return self._import_system.state.error(f"Could not find file \'{path}\'")

        if self._import_system.compiler.current_toolchain.context.get_document_context(path, default=None) is not None:
            return self._import_system.state.error(f"Document \'{path}\' was already imported")

        document = self._import_system.compiler.import_document(path)

        return ZSImportResult(document)


class ModuleImporter(Importer):
    def __init__(self, compiler):
        self._compiler = compiler

    def import_from(self, source: str) -> ScopeProtocol | None:
        return self._compiler.context.get_module(source)
