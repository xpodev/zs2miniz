from zs.ctrt.core import Module, Any, Type
from zs.ctrt.native import native_function


srf = Module("SRF", None, None)


def define_function(*args, **kwargs):
    def wrapper(fn):
        result = native_function(*args, **kwargs)(fn)
        srf.define(result.name, result)
    return wrapper


@define_function("typeof")
def srf__typeof(instance: Any) -> Type:
    return instance.runtime_type
