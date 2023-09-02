from contextlib import contextmanager
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
        self._global_context = GlobalContext(self)
        self._toolchain = Toolchain(self._state, self, **toolchain_kwargs)

    @property
    def current_toolchain(self):
        return self._toolchain

    @property
    def context(self):
        return self._global_context

    @contextmanager
    def toolchain(self, **kwargs):
        toolchain, self._toolchain = self._toolchain, Toolchain(self.state, self, **kwargs)
        try:
            yield self._toolchain
        finally:
            self._toolchain = toolchain

    def import_document(self, file: DocumentInfo | str | Path, *, isolated: bool = False) -> DocumentContext:
        with self.toolchain(parser=lambda _: self.current_toolchain.parser, isolated=isolated) as toolchain:
            return toolchain.execute_document(file)

    def inline_document(self, file: DocumentInfo | str | Path):
        self.current_toolchain.resolver.add_nodes(*self.current_toolchain.execute_document(file, result=ToolchainResult.AST))
