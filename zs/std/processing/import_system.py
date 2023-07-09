import re
from pathlib import Path

from miniz.interfaces.base import ScopeProtocol


class Importer:
    def import_from(self, source: str) -> ScopeProtocol | None:
        ...

    @lambda _: None
    def import_directory(self, path: Path) -> ScopeProtocol | None:
        ...


class ImportSystem(Importer):
    _path: list[str]
    _suffix_importers: dict[str, Importer]
    _importers: dict[str, Importer]
    _directory_importers: list[Importer]

    def __init__(self):
        super().__init__()
        self._path = []
        self._suffix_importers = {}
        self._importers = {}
        self._directory_importers = []

    def add_directory(self, path: str | Path):
        path = Path(path)
        if not path.is_dir():
            raise ValueError(f"Can only add directories to search path")
        if not path.is_absolute():
            path = self.resolve(path)
        if path is None:
            raise ValueError(f"Could not find path")
        self._path.append(str(path))

    def add_importer(self, importer: Importer, ext_or_type: str):
        if ext_or_type.startswith('.'):
            importers = self._suffix_importers
        else:
            importers = self._importers

        if ext_or_type in importers:
            raise ValueError(f"Importer for \"{ext_or_type}\" already exists")

        importers[ext_or_type] = importer
        if importer.import_directory is not None:
            self._directory_importers.append(importer)

    def import_directory(self, path: Path) -> ScopeProtocol | None:
        for importer in self._directory_importers:
            if result := importer.import_directory(path):
                return result
        return None

    def import_file(self, path: Path) -> ScopeProtocol | None:
        try:
            return self._suffix_importers[path.suffix].import_from(str(path))
        except KeyError as e:
            raise e

    def import_from(self, source: str) -> ScopeProtocol | None:
        if match := re.match(r"(?P<importer>[A-Za-z]+):(?P<source>.*)", source):
            groups = match.groupdict()
            return self._importers[groups["importer"]].import_from(groups["source"])
        path = Path(source)
        if path.is_dir():
            return self.import_directory(path)
        return self.import_file(path)

    def resolve(self, path: str | Path) -> Path | None:
        path = Path(path)
        if path.is_absolute():
            return path if path.exists() else None
        for directory in self._path:
            if (result := (str(directory) / path)).exists():
                return result
        if (result := (Path.cwd() / path)).exists():
            return result
        return None
