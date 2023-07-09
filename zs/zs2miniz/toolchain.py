import typing
from enum import Enum
from pathlib import Path

from utils import DependencyGraph
from zs.processing import State, StatefulProcessor
from zs.text.file_info import DocumentInfo, SourceFile
from zs.text.parser import Parser
from zs.text.token_stream import TokenStream
from zs.text.tokenizer import Tokenizer
from zs.zs2miniz.ast_resolver import NodeProcessor
from zs.zs2miniz.compiler import NodeCompiler
from zs.zs2miniz.dependency_finder import DependencyFinder
from zs.zs2miniz.lib import CompilationContext

if typing.TYPE_CHECKING:
    from zs.zs_compiler import ZSCompiler

_SENTINEL = object()


class ToolchainResult(Enum):
    Tokens = 1
    AST = 2
    ResolvedAST = 3
    BuildOrder = 4
    BuiltObjects = 5
    MiniZObjects = 6
    DocumentContext = 7
    Default = DocumentContext


class Toolchain(StatefulProcessor):
    _tokenizer: Tokenizer  # SourceFile -> Iterable[Token]
    _parser: Parser  # Iterable[Token] -> List[Node]
    _node_processor: NodeProcessor  # List[Node] -> List[ResolvedNode]
    _compiler: NodeCompiler  # List[ResolvedNode] -> List[ObjectProtocol]

    _compilation_context: CompilationContext

    def __init__(
            self,
            state: State,
            compiler: "ZSCompiler",
            *,
            tokenizer: typing.Callable[[State], Tokenizer] = None,
            parser: typing.Callable[[State], Parser] = None,
            isolated: bool = False):
        super().__init__(state)
        self._compilation_context = CompilationContext(compiler, isolated=isolated)
        self._tokenizer = (tokenizer or Tokenizer)(state)
        self._parser = (parser or Parser)(state)
        self._node_processor = NodeProcessor(state=state, global_scope=self._compilation_context.scope)
        self._compiler = NodeCompiler(state=state, context=self._compilation_context)

    @property
    def tokenizer(self):
        return self._tokenizer

    @property
    def parser(self):
        return self._parser

    @property
    def resolver(self):
        return self._node_processor

    @property
    def compiler(self):
        return self._compiler

    @property
    def import_system(self):
        return self._compilation_context.import_system

    @property
    def context(self):
        return self._compilation_context

    def execute_document(self, path: str | Path | DocumentInfo, result: ToolchainResult = ToolchainResult.Default):
        """
        Executes the given file.
        :param path: The path to the file to execute.
        :param result: The result type to return.
        :return: The result of the execution.
        """

        info = DocumentInfo.from_path(path)

        if (document := self.context.get_document_context(info.path_string, default=None)) is None:
            document = self.context.create_document_context(info.path_string)

        match result:
            case ToolchainResult.Tokens:
                if document.tokens is None:
                    document.tokens = list(self.tokenizer.tokenize(SourceFile.from_info(info)))
                return document.tokens
            case ToolchainResult.AST:
                if document.nodes is None:
                    document.nodes = self.parser.parse(TokenStream(self.execute_document(info, result=ToolchainResult.Tokens), info.path_string))
                return document.nodes
            case ToolchainResult.ResolvedAST:
                if document.resolved_nodes is None:
                    for node in self.execute_document(info, result=ToolchainResult.AST):
                        self.resolver.add_node(node)
                    document.resolved_nodes = self.resolver.resolve()
                return document.resolved_nodes
            case ToolchainResult.BuildOrder:
                if document.build_order is None:
                    dependency_finder = DependencyFinder(state=self.state)
                    nodes = self.execute_document(info, result=ToolchainResult.ResolvedAST)
                    nodes = sum((dependency_finder.flatten_tree(node) for node in nodes), nodes)
                    document.build_order = DependencyGraph.from_list(
                        nodes, dependency_finder.find_dependencies
                    )
                return document.build_order
            case ToolchainResult.MiniZObjects:
                if document.objects is None:
                    document.objects = self.compiler.compile(sum(self.execute_document(info, result=ToolchainResult.BuildOrder), []))
                    for name, item in self.resolver.context.current_scope.defined_names:
                        document.scope.create_name(name, self.compiler.compile(item))
                return document.objects
            case ToolchainResult.DocumentContext:
                self.execute_document(info, result=ToolchainResult.MiniZObjects)
                return document
            case _:
                raise ValueError(f"Unexpected result type: \'{result}\'")
