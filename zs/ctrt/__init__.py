import typing

if typing.TYPE_CHECKING:
    from .runtime import Interpreter
else:
    Interpreter = None

_InterpreterInstance: Interpreter = None


def get_runtime() -> Interpreter:
    return _InterpreterInstance
