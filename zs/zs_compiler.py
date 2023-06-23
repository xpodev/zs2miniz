from pathlib import Path

from zs.context import Context, GlobalContext, ToolchainContext
from zs.processing import State
from zs.zs2miniz.lib import DocumentContext
from zs.zs2miniz.toolchain import Toolchain, ToolchainResult
from zs.text.file_info import DocumentInfo

from zs.utils import SingletonMeta


class ZSCompiler(metaclass=SingletonMeta):
    """
    This class is used to construct a single Z# compiler for the current process. That's why it's a singleton.. :D
    """

    _toolchain: Toolchain

    def __init__(self, global_context: Context = None, toolchain: Toolchain = None, state: State = None):
        self._state = state or State()
        self._toolchain = toolchain or Toolchain(state=self._state)
        self._global_context = global_context or GlobalContext()

    @property
    def toolchain(self):
        return self._toolchain

    def import_document(self, file: DocumentInfo | str | Path) -> DocumentContext:
        return self.toolchain.fork_with(toolchain_context=ToolchainContext()).execute_document(file)

    def inline_document(self, file: DocumentInfo | str | Path):
        self.toolchain.resolver.add_nodes(*self._toolchain.execute_document(file, result=ToolchainResult.AST))
