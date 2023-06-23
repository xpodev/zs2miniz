from pathlib import Path
from typing import Iterable

from zs.ctrt.core import Scope
from zs.ctrt.protocols import ObjectProtocol, ScopeProtocol, TypeProtocol
from zs.std.processing.import_system import Importer, ImportSystem


class ZSImportResult(ScopeProtocol):
    _scope: Scope
    _items: dict[str, tuple[TypeProtocol, ObjectProtocol]]

    def __init__(self, scope: Scope):
        super().__init__()
        self._scope = scope
        self._items = dict(scope.members)

    def all(self) -> Iterable[tuple[str, tuple[TypeProtocol, ObjectProtocol]]]:
        for name, item in self._items.items():
            yield name, item

    def get_name(self, name: str, **_) -> tuple[TypeProtocol, ObjectProtocol]:
        return self._items[name]


class ZSImporter(Importer):
    _import_system: ImportSystem

    def __init__(self, import_system: ImportSystem, compiler):
        super().__init__()
        self._import_system = import_system
        self._compiler = compiler

    def import_from(self, source: str) -> ScopeProtocol | None:
        return self.import_file(Path(source))

    def import_file(self, path: Path) -> ScopeProtocol | None:
        path = self._import_system.resolve(path)

        if path is None:
            return None

        document: Scope = self._compiler.compile(path)

        return ZSImportResult(document)


class ModuleImporter(Importer):
    def __init__(self, compiler):
        self._compiler = compiler

    def import_from(self, source: str) -> ScopeProtocol | None:
        return self._compiler.context.get_module_from_cache(source)
