from zs.ctrt.core import Module, Type, Any, Unit, Void, Class
from zs.ctrt.native import String, Int64, Boolean, Float64, native_function

core = Module("Core", None, None)


def define_function(*args, **kwargs):
    def wrapper(fn):
        result = native_function(*args, **kwargs)(fn)
        core.define(result.name, result)
    return wrapper


core.define("Boolean", Boolean)
core.define("Int64", Int64)
core.define("Float64", Float64)
core.define("String", String)

core.define("Type", Type)
core.define("Any", Any)
core.define("Void", Void)
core.define("Unit", Unit)

# core.define("Union", Union)  # srf
# core.define("Tuple", Tuple)  # srf

# core.define("Class", Class)  # srf


define_print = define_function("print")


@define_print
def core__print(arg1: Any) -> None:
    print(arg1)


@define_print
def core__print(arg1: Any, arg2: Any) -> None:
    print(arg1, arg2)
