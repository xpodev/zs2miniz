from contextlib import contextmanager
from functools import singledispatchmethod

from zs.ast import resolved
from zs.dependency_graph import DependencyGraph
from zs.processing import StatefulProcessor, State
from zs.utils import make_tuple


class DependencyFinder(StatefulProcessor):
    _dispatcher: "DependencyFinderDispatcher"

    def __init__(self, dispatcher: "DependencyFinderDispatcher"):
        super().__init__(dispatcher.state)

        self._dispatcher = dispatcher

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def graph(self):
        return self.dispatcher.current_graph

    def add(self, dependant: resolved.ResolvedNode, *dependencies: resolved.ResolvedNode):
        self.graph.add(dependant, *dependencies)
        for dependency in dependencies:
            self.dispatcher.find(dependency)

    def find_dependencies(self, node: resolved.ResolvedNode) -> list[resolved.ResolvedNode]:
        if isinstance(node, resolved.ResolvedObject):
            return []

        return self._find_dependencies(node)

    def _find_dependencies(self, node: resolved.ResolvedNode) -> list[resolved.ResolvedNode] | None:
        raise NotImplementedError(f"Can't find dependencies for node of type '{type(node)}' because it is not implemented yet")


"""
For example, a function's body. We only care for declarations because at RT
we know that everything is defined.

But declarations don't really exist! What I actually want for function calls is to depend
on the target SIGNATURE, not body.

However, a CT function call does depend on the function's body.

In fact, in order to fully define a CT function call, I need to find the total call chain,
flatten it and add all the functions as dependencies. HOWEVER, what if there a function that's
passed as an argument and then called inside the called function?

Well, everything referenced inside a CT called function should be defined. This makes things a bit easier.
Ok, so basically just find all the referenced objects and add them to a single list.

I'll also need to cache the objects walked over, so if there's "recursive dependencies", I can handle that.


Ok, I have split the 2 dependency finders, and there's one not for RT and CT.

However, there's a special case where we want to use the RT finder even though
it is a CT context: directly referenced types.

If a type is directly referenced, we don't want to require its definition. This
is also true for directly referenced imported names. In fact, this may hold true
for any direct references.

So maybe I should also add a new type of finder specifically for types.
This finder will try to find for specific types and if not found, only 
then it'll fall back to trying the CT finder.

Now I realize that I need a different way of doing things.

Why? Suppose that A -> B -> C, so I'll need to build C then B then A.

But what if I implement the finder for A to return the dependencies for B?
Then we'll have to do A -> C, so the order will be C then A.

My solution is that instead of having the finders return a list of nodes, 
they should mutate an existing graph.

However, this solution only works for nodes which are referencable.

For expressions, this may not work. Also, we don't want to include expressions
in the build order. When finding dependencies for an expression, we only want
to return the dependencies without making the expression as another dependant,
and also, I only want to have the nodes which the expressions depend on.
"""


class DependencyFinderDispatcher(StatefulProcessor):
    _finder: DependencyFinder | None
    _graph: DependencyGraph[resolved.ResolvedNode] | None

    _ct_finder: "CompileTimeDependencyFinder"
    _rt_finder: "RuntimeDependencyFinder"

    _typing_finder: "TypingDependencyFinder"
    _code_finder: "CodeDependencyFinder"

    def __init__(self, state: State):
        super().__init__(state)
        self._finder = None
        self._graph = None

        self._ct_finder = CompileTimeDependencyFinder(self)
        self._rt_finder = RuntimeDependencyFinder(self)

        self._typing_finder = TypingDependencyFinder(self)
        self._code_finder = CodeDependencyFinder(self)

    @property
    def current_finder(self):
        return self._finder

    @property
    def current_graph(self):
        return self._graph

    # region Finders

    @property
    def code_finder(self):
        return self._code_finder

    @property
    def compile_time_finder(self):
        return self._ct_finder

    @property
    def runtime_finder(self):
        return self._rt_finder

    @property
    def typing_finder(self):
        return self._typing_finder

    # endregion

    @contextmanager
    def finder(self, finder: DependencyFinder):
        finder, self._finder = self._finder, finder
        try:
            yield
        finally:
            self._finder = finder

    @contextmanager
    def graph(self, graph: DependencyGraph[resolved.ResolvedNode]):
        graph, self._graph = self._graph, graph
        try:
            yield
        finally:
            self._graph = graph

    def find(self, node: resolved.ResolvedNode, finder: DependencyFinder = None):
        if finder is None and self.current_finder is None:
            raise ValueError(f"Finder was {None}")
        return (finder or self.current_finder).find_dependencies(node)


class RuntimeDependencyFinder(DependencyFinder):
    """
    The RT dependency finder finds dependencies by declarations, because we can be sure that we'll have
    definitions at RT. This is the `regular` dependency finder, which calls the CT dependency finder when
    needed.
    """

    def __init__(self, dispatcher: DependencyFinderDispatcher):
        super().__init__(dispatcher)

    @singledispatchmethod
    def _find_dependencies(self, node: resolved.ResolvedNode):
        super()._find_dependencies(node)

    _dep = _find_dependencies.register

    # region Implementation

    @_dep
    def _(self, node: resolved.ResolvedClass):
        with self.dispatcher.finder(self.dispatcher.typing_finder):
            self.add(node, *sum(map(self.dispatcher.find, node.bases), []))

    @_dep
    def _(self, node: resolved.ResolvedExpression):
        return self.dispatcher.code_finder.find_dependencies(node)

    @_dep
    def _(self, node: resolved.ResolvedFunction):
        self.add(node, *node.positional_parameters)
        self.add(node, *node.named_parameters)

        self.add(node, *make_tuple(node.variadic_positional_parameter))
        self.add(node, *make_tuple(node.variadic_named_parameter))

        if node.return_type is None:
            # self.add(node, node.body)
            ...
        else:
            self.add(node, *self.dispatcher.typing_finder.find_dependencies(node.return_type))

    @_dep
    def _(self, node: resolved.ResolvedFunctionBody):
        if node.instructions is not None:
            self.add(node, *sum(map(self.dispatcher.find, node.instructions), []))

    @_dep
    def _(self, _: resolved.ResolvedGenericParameter):
        return

    @_dep
    def _(self, node: resolved.ResolvedImport):
        self.add(node, *self.dispatcher.code_finder.find_dependencies(node.source))

    @_dep
    def _(self, node: resolved.ResolvedModule):
        self.add(node)

    @_dep
    def _(self, node: resolved.ResolvedParameter):
        with self.dispatcher.finder(self.dispatcher.typing_finder):
            if node.type:
                self.add(node, *self.dispatcher.code_finder.find_dependencies(node.type))
            if node.initializer:
                self.add(node, node.initializer)

    @_dep
    def _(self, node: resolved.ResolvedStatement):
        return self.dispatcher.code_finder.find_dependencies(node)

    @_dep
    def _(self, node: resolved.ResolvedVar):
        if node.type:
            self.add(node, *self.dispatcher.typing_finder.find_dependencies(node.type))
        if node.initializer:
            self.add(node, *self.dispatcher.code_finder.find_dependencies(node.initializer))
        return [node]

    # endregion

    del _dep


class CompileTimeDependencyFinder(DependencyFinder):
    """
    The CT dependency finder finds dependency by definitions because it is intended to be used when trying
    to figure out which object should be built in what order to be able to fully access a certain object
    """

    _cache: dict[resolved.ResolvedNode, list[resolved.ResolvedNode]]
    _visited: set[resolved.ResolvedNode]

    def __init__(self, dispatcher: DependencyFinderDispatcher):
        super().__init__(dispatcher)

        self._cache = {}
        self._visited = set()

    def add(self, dependant: resolved.ResolvedNode, *dependencies: resolved.ResolvedNode):
        if dependant not in self._cache:
            self._cache[dependant] = []
        self._cache[dependant].extend(dependencies)

    def find_dependencies(self, node: resolved.ResolvedNode):
        if node in self._cache:
            return self._cache[node]
        if node not in self._visited:
            self._visited.add(node)
            return super().find_dependencies(node)

    @singledispatchmethod
    def _find_dependencies(self, node: resolved.ResolvedNode):
        super()._find_dependencies(node)

    _dep = _find_dependencies.register

    # region Implementation

    @_dep
    def _(self, node: resolved.ResolvedClass):
        self.dispatcher.runtime_finder.find_dependencies(node)
        self.add(node, *node.items)

    @_dep
    def _(self, node: resolved.ResolvedExpression):
        return self.dispatcher.code_finder.find_dependencies(node)

    @_dep
    def _(self, node: resolved.ResolvedStatement):
        return self.dispatcher.code_finder.find_dependencies(node)

    @_dep
    def _(self, node: resolved.ResolvedFunction):
        return [
            *self.find_dependencies(node.body),
        ]

    @_dep
    def _(self, node: resolved.ResolvedFunctionBody):
        return [
            *(self.dispatcher.runtime_finder.find_dependencies(node.owner) or ()),
            *sum(map(self.find_dependencies, node.instructions), [])
        ]

    @_dep
    def _(self, _: resolved.ResolvedGenericParameter):
        return

    @_dep
    def _(self, node: resolved.ResolvedImport):
        self.add(node, *self.dispatcher.code_finder.find_dependencies(node.source))

    @_dep
    def _(self, node: resolved.ResolvedModule):
        self.add(node, *node.items)

    @_dep
    def _(self, node: resolved.ResolvedOverloadGroup):
        return [
            *self.find_dependencies(node.parent),
            *sum(map(self.find_dependencies, node.overloads), []),
        ]

    @_dep
    def _(self, node: resolved.ResolvedParameter):
        with self.dispatcher.finder(self.dispatcher.typing_finder):
            if node.type:
                self.add(node, *self.dispatcher.code_finder.find_dependencies(node.type))
            if node.initializer:
                self.add(node, node.initializer)

    # endregion

    del _dep


class TypingDependencyFinder(DependencyFinder):
    # _EMPTY = []

    # @singledispatchmethod
    # def _find_dependencies(self, node: resolved.ResolvedNode):
    #     return self.dispatcher.compile_time_finder.find_dependencies(node)
    #
    # _dep = _find_dependencies.register
    #
    # # region Implementation
    #
    # @_dep
    # def _(self, _: resolved.ResolvedClass):
    #     return self._EMPTY
    #
    # @_dep
    # def _(self, _: resolved.ResolvedImport.ImportedName):
    #     return self._EMPTY
    #
    # # endregion

    # del _dep

    def _find_dependencies(self, node: resolved.ResolvedNode):
        if any(isinstance(node, cls) for cls in {
            resolved.ResolvedClass,
            resolved.ResolvedImport.ImportedName,
        }):
            finder = self.dispatcher.runtime_finder
        else:
            finder = self.dispatcher.compile_time_finder
        with self.dispatcher.finder(finder):
            return self.dispatcher.code_finder.find_dependencies(node)


class CodeDependencyFinder(DependencyFinder):
    def find_dependencies(self, node: resolved.ResolvedNode) -> list[resolved.ResolvedNode]:
        if any(isinstance(node, cls) for cls in {
            resolved.ResolvedClass,
            resolved.ResolvedFunction,
            resolved.ResolvedGenericParameter,
            resolved.ResolvedParameter,
            resolved.ResolvedImport,
            resolved.ResolvedVar
        }):
            result = self.dispatcher.find(node)
            if result is None:
                return [node]
            return result
        return super().find_dependencies(node)

    @singledispatchmethod
    def _find_dependencies(self, node: resolved.ResolvedNode):
        super()._find_dependencies(node)

    _dep = _find_dependencies.register

    # region Implementation

    @_dep
    def _(self, node: resolved.ResolvedBinary):
        return [
            *self.find_dependencies(node.left),
            *self.find_dependencies(node.right)
        ]

    @_dep
    def _(self, node: resolved.ResolvedExpressionStatement):
        return [
            *self.find_dependencies(node.expression),
        ]

    @_dep
    def _(self, node: resolved.ResolvedFunctionCall):
        return [
            *self.find_dependencies(node.callable),
            *sum(map(self.find_dependencies, node.arguments), []),
            *sum(map(self.find_dependencies, node.keyword_arguments.values()), []),
        ]

    @_dep
    def _(self, node: resolved.ResolvedImport.ImportedName):
        return [node.origin]

    @_dep
    def _(self, node: resolved.ResolvedMemberAccess):
        return self.find_dependencies(node.object)

    @_dep
    def _(self, node: resolved.ResolvedOverloadGroup):
        return [
            *(self.find_dependencies(node.parent) if node.parent is not None else ()),
            *sum(map(self.find_dependencies, node.overloads), [])
        ]

    @_dep
    def _(self, node: resolved.ResolvedReturn):
        if node.expression is None:
            return []
        return self.find_dependencies(node.expression)

    # endregion

    del _dep
