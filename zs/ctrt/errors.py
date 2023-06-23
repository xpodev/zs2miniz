from typing import Any


class ZSError(Exception):
    ...


class NameNotFoundError(ZSError):
    ...


class NameAlreadyExistsError(ZSError):
    ...


class NoParentScopeError(ZSError):
    ...


class NameAlreadyBoundError(ZSError):
    ...


class UnknownFieldError(ZSError):
    ...


class FieldAlreadyDefinedError(ZSError):
    ...


class MemberAlreadyDefinedError(ZSError):
    ...


class UnknownMemberError(ZSError):
    ...


# ########## FLOW CONTROL ############ #


class ReturnInstructionInvoked(Exception):
    _value: Any

    def __init__(self, value: Any):
        self._value = value

    @property
    def value(self):
        return self._value


class BreakInstructionInvoked(Exception):
    _loop: Any

    def __init__(self, loop: Any = None):
        self._loop = loop

    @property
    def loop(self):
        return self._loop


class ContinueInstructionInvoked(Exception):
    _loop: Any

    def __init__(self, loop: Any = None):
        self._loop = loop

    @property
    def loop(self):
        return self._loop
