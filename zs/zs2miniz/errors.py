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
