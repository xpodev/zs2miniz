from pathlib import Path

from zs.processing import State, StatefulProcessor
from zs.text.file_info import DocumentInfo
from zs.utils import SingletonMeta
from zs.zs2miniz.lib import DocumentContext, GlobalContext
from zs.zs2miniz.toolchain import Toolchain, ToolchainResult


class ZSCompiler(StatefulProcessor, metaclass=SingletonMeta):
    """
    This class is used to construct a single Z# compiler for the current process. That's why it's a singleton.. :D
    """

    _toolchain: Toolchain

    def __init__(self, state: State = None, **toolchain_kwargs):
        super().__init__(state or State())
        self._global_context = GlobalContext(self, isolated=True)
        self._toolchain = Toolchain(self._state, self, **toolchain_kwargs)

    @property
    def toolchain(self):
        return self._toolchain

    @property
    def context(self):
        return self._global_context

    def import_document(self, file: DocumentInfo | str | Path, *, isolated: bool = False) -> DocumentContext:
        return Toolchain(self.state, self, parser=lambda _: self.toolchain.parser, isolated=isolated).execute_document(file)

    def inline_document(self, file: DocumentInfo | str | Path):
        self.toolchain.resolver.add_nodes(*self.toolchain.execute_document(file, result=ToolchainResult.AST))
