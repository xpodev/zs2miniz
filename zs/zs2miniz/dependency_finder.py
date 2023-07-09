from functools import singledispatchmethod

from zs.ast.resolved import ResolvedNode, ResolvedModule, ResolvedClass, ResolvedFunction, ResolvedParameter, ResolvedOverloadGroup, ResolvedObject
from zs.processing import StatefulProcessor, State


class DependencyFinder(StatefulProcessor):
    _cache: dict[ResolvedNode, list[ResolvedNode]]

    def __init__(self, *, state: State):
        super().__init__(state)
        self._cache = {}

    def flatten_tree(self, node: ResolvedNode) -> list[ResolvedNode]:
        return self._flatten_tree(node)

    @singledispatchmethod
    def _flatten_tree(self, node: ResolvedNode):
        return []
        raise NotImplementedError(f"Can't flatten node of type \'{type(node)}\' because it is not implemented yet")

    _flt = _flatten_tree.register

    @_flt
    def _(self, node: ResolvedModule):
        return sum((self.flatten_tree(node) for node in node.items), node.items)

    @_flt
    def _(self, node: ResolvedClass):
        return sum((self.find_dependencies(base) for base in node.bases), [])

    @_flt
    def _(self, node: ResolvedFunction):
        # result = [*node.positional_parameters, *node.named_parameters]
        # if node.variadic_positional_parameter:
        #     result.append(node.variadic_positional_parameter)
        # if node.variadic_named_parameter:
        #     result.append(node.variadic_named_parameter)
        return []

    @_flt
    def _(self, node: ResolvedOverloadGroup):
        return sum((self.flatten_tree(fn) for fn in node.overloads), [])

    @_flt
    def _(self, _: ResolvedObject):
        return []

    def find_dependencies(self, node: ResolvedNode) -> list[ResolvedNode]:
        if node is None:
            return []
        try:
            return self._cache[node]
        except KeyError:
            result = self._cache[node] = self._find_dependencies(node)
            if result is None:
                result = self._cache[node] = []
            return result

    @singledispatchmethod
    def _find_dependencies(self, node: ResolvedNode) -> list[ResolvedNode]:
        return []
        raise NotImplementedError(f"Can't find dependencies for node of type \'{type(node)}\' because it is not implemented yet")

    _dep = _find_dependencies.register

    @_dep
    def _(self, node: ResolvedModule):
        return []

    @_dep
    def _(self, node: ResolvedClass):
        return node.bases

    @_dep
    def _(self, node: ResolvedFunction):
        return [
            *sum(map(self.find_dependencies, node.positional_parameters), []),
            *sum(map(self.find_dependencies, node.named_parameters), []),
            *self.find_dependencies(node.variadic_positional_parameter),
            *self.find_dependencies(node.variadic_named_parameter),
        ]

    @_dep
    def _(self, node: ResolvedOverloadGroup):
        return sum((self.find_dependencies(fn) for fn in node.overloads), [])

    @_dep
    def _(self, node: ResolvedParameter):
        return [
            *self.find_dependencies(node.type),
            *self.find_dependencies(node.initializer)
        ]

    @_dep
    def _(self, _: ResolvedObject):
        return []
