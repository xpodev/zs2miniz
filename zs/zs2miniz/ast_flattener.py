from functools import singledispatchmethod

from zs.ast import resolved
from zs.processing import StatefulProcessor
from zs.utils import make_tuple


class ASTFlattener(StatefulProcessor):
    # region Flatten

    def flatten_tree(self, node: resolved.ResolvedNode) -> list[resolved.ResolvedNode]:
        return [
            node,
            *self._flatten_tree(node)
        ]

    @singledispatchmethod
    def _flatten_tree(self, node: resolved.ResolvedNode):
        raise NotImplementedError(f"Can't flatten node of type \'{type(node)}\' because it is not implemented yet")

    _flt = _flatten_tree.register

    @_flt
    def _(self, node: resolved.ResolvedImport):
        return node.imported_names

    @_flt
    def _(self, node: resolved.ResolvedModule):
        return sum(map(self.flatten_tree, node.items), [])

    @_flt
    def _(self, node: resolved.ResolvedClass):
        return sum(map(self.flatten_tree, node.items), [])

    @_flt
    def _(self, node: resolved.ResolvedFunction):
        return [
            *node.positional_parameters,
            *node.named_parameters,
            *make_tuple(node.variadic_positional_parameter),
            *make_tuple(node.variadic_named_parameter),
            node.body,
        ]

    @_flt
    def _(self, node: resolved.ResolvedOverloadGroup):
        return [
            *sum(map(self.flatten_tree, node.overloads), []),
            *(self.flatten_tree(node.parent) if node.parent else ())
        ]

    @_flt
    def _(self, _: resolved.ResolvedObject):
        return []

    @_flt
    def _(self, _: resolved.ResolvedVar):
        return []

    # endregion
