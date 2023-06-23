from dotnet import DotNETCompiler
from zs.std.processing.import_system import Importer


class DotNETImporter(Importer):
    def __init__(self, dotnet_compiler: DotNETCompiler):
        self._compiler = dotnet_compiler

    # def import_from(self, source: str) -> ScopeProtocol | None:
    #     return super().import_from(source)
