from enum import Enum
from pathlib import Path

from utils import DependencyGraph
from zs.context import ToolchainContext
from zs.processing import State, StatefulProcessor
from zs.text.file_info import DocumentInfo, SourceFile
from zs.text.parser import Parser
from zs.text.token_stream import TokenStream
from zs.text.tokenizer import Tokenizer
from zs.zs2miniz.ast_resolver import ASTResolver
from zs.zs2miniz.compiler import ASTCompiler
from zs.zs2miniz.dependency_finder import DependencyFinder
from zs.zs2miniz.lib import CompilationContext


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
    _resolver: ASTResolver  # List[Node] -> List[ResolvedNode]
    _compiler: ASTCompiler  # List[ResolvedNode] -> list[ObjectProtocol]

    _toolchain_context: ToolchainContext
    _compilation_context: CompilationContext

    # _document_stack: list[DocumentContext]

    def __init__(
            self,
            state: State = None,
            tokenizer: Tokenizer = None,
            parser: Parser = None,
            resolver: ASTResolver = None,
            compiler: ASTCompiler = None,
            compilation_context: CompilationContext = None,
            toolchain_context: ToolchainContext = None,
    ):
        state = state or State()
        super().__init__(state)
        self._compilation_context = compilation_context or CompilationContext(self)
        self._toolchain_context = toolchain_context or ToolchainContext()
        self._tokenizer = tokenizer or Tokenizer(state=state)
        self._parser = parser or Parser(state=state)
        self._resolver = resolver or ASTResolver(state=state, context=self._compilation_context)
        self._compiler = compiler or ASTCompiler(state=state)

    @property
    def tokenizer(self):
        return self._tokenizer

    @property
    def parser(self):
        return self._parser

    @property
    def resolver(self):
        return self._resolver

    @property
    def compiler(self):
        return self._compiler

    @property
    def compilation_context(self):
        return self._compilation_context

    @property
    def context(self):
        return self._toolchain_context

    def execute_document(self, path: str | Path | DocumentInfo, result: ToolchainResult = ToolchainResult.Default):
        """
        Executes the given file.
        :param path: The path to the file to execute.
        :param result: The result type to return.
        :return: The result of the execution.
        """

        info = DocumentInfo.from_path(path)

        if (document := self.compilation_context.get_document_context(info)) is None:
            document = self.compilation_context.create_document_context(info)

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
                    with self.compiler.document(document):
                        document.objects = sum(([self.compiler.compile(item) for item in items] for items in self.execute_document(info, result=ToolchainResult.BuildOrder)), [])
                        document.objects += [self.compiler.compile(node) for node in self.execute_document(info, result=ToolchainResult.ResolvedAST)]
                return document.objects
            case ToolchainResult.DocumentContext:
                self.execute_document(info, result=ToolchainResult.MiniZObjects)
                return document
            case _:
                raise ValueError(f"Unexpected result type: \'{result}\'")

    def fork_with(
            self,
            state: State = None,
            tokenizer: Tokenizer = None,
            parser: Parser = None,
            resolver: ASTResolver = None,
            compiler: ASTCompiler = None,
            compilation_context: CompilationContext = None,
            toolchain_context: ToolchainContext = None,):
        """
        Creates a new toolchain which is a copy of this one, except for the given arguments.
        :return: A new toolchain, using this toolchain's tools if not provided in the argument list.
        """

        return Toolchain(
            state=state or self.state,
            tokenizer=tokenizer or self.tokenizer,
            parser=parser or self.parser,
            resolver=resolver or self.resolver,
            compiler=compiler or self.compiler,
            compilation_context=compilation_context or self.compilation_context,
            toolchain_context=toolchain_context or self.context,
        )
