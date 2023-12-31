from zs.ast.node import Node


class ZSharpError(Exception):
    """
    Base exception for all Z# errors
    """


class NameNotFoundError(ZSharpError):
    """
    Raised when a name lookup fails in a certain scope
    """


class NameAlreadyBoundError(ZSharpError):
    """
    Raised when a name is being defined in a scope in which this name already exists
    """


class CodeCompilationError(ZSharpError):
    """
    Raised when compiling code fails
    """

    def __init__(self, message: str, node: Node, *args):
        super().__init__(message, *args)
        self.message = message
        self.node = node


class OverloadMatchError(ZSharpError):
    """
    Raised when matching an overload group with certain args and kwargs fails.
    """

    def __init__(self, group, types, *args):
        super().__init__(group, types, args)
        self.group = group
        self.types = types
