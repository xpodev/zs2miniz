from contextlib import contextmanager

from miniz.interfaces.function import IFunctionBody, IFunction
from miniz.vm.instruction import Instruction
from utilz.debug.debug_information import FunctionBodyDebugInformation
from utilz.debug.file_info import DocumentInfo, Span
from utilz.debug.sequence_point import SequencePoint
from zs.ast.node import Node
from zs.text.token import Token


class DebugDatabase:
    _cache: dict[IFunctionBody, FunctionBodyDebugInformation]

    def __init__(self):
        self._cache = {}

    def create_debug_information(self, body: IFunctionBody, document: DocumentInfo):
        result = self._cache[body] = FunctionBodyDebugInformation(body, document)
        return result

    def get_debug_information(self, body: IFunctionBody):
        return self._cache[body]


class DebugContext:
    _dbi: FunctionBodyDebugInformation | None
    _debug_database: DebugDatabase
    _cache: list[SequencePoint] | None

    def __init__(self, db: DebugDatabase = None):
        self._dbi = None
        self._cache = None
        if db is None:
            db = DebugDatabase()
        self._debug_database = db

    @property
    def current_function_body(self):
        if self._dbi is None:
            return None
        return self._dbi.definition

    @property
    def current_function(self):
        if self._dbi is None:
            return None
        return self.current_function_body.owner

    @property
    def current_debug_information(self):
        return self._dbi

    @property
    def debug_database(self):
        return self._debug_database

    @contextmanager
    def function(self, fn: IFunction):
        with self.function_body(fn.body):
            yield

    @contextmanager
    def debug_information(self, dbi: FunctionBodyDebugInformation):
        dbi, self._dbi = self._dbi, dbi
        cache, self._cache = self._cache, []
        try:
            yield
        finally:
            self._dbi = dbi
            self._cache = cache

    @contextmanager
    def function_body(self, body: IFunctionBody):
        with self.debug_information(self.debug_database.get_debug_information(body)):
            yield

    def emit(self, inst: Instruction, node: Node | Token):
        if self.current_debug_information:
            sp = SequencePoint()
            if isinstance(node, Node):
                span = node.span
            elif isinstance(node, Token):
                span = node.span
            elif isinstance(node, Span):
                span = node
            else:
                raise TypeError
            sp.span = span
            sp.instruction = inst
            sp.document = self.current_debug_information.document
            self.current_debug_information.sequence_points.append(sp)
        else:
            raise TypeError

    # def append(self, sp: SequencePoint):
    #     self._cache.append(sp)
    #
    # def commit(self):
    #     self._dbi.sequence_points.extend(self._cache)
    #     self._cache.clear()
