from pathlib import Path

from zs.ctrt.core import Module, Type, Any, Unit, Void, Class
from zs.ctrt.native import String, Int64, Boolean, Float64, native_function, NativeClass, native_constructor, _Self, native_fn

filesystem = Module("FileSystem", None, None)


def define_function(*args, **kwargs):
    def wrapper(fn):
        result = native_function(*args, **kwargs)(fn)
        filesystem.define(result.name, result)
    return wrapper


class Directory(NativeClass):
    def __init__(self, path: Path):
        super().__init__()
        if not path.is_dir():
            raise ValueError(f"argument must be a valid directory \"{path}\"")
        self.path = path

    @native_fn("cwd")
    # @classmethod
    def cwd(self):
        self.path = Path.cwd()

    @native_constructor
    # @classmethod
    def construct(self: _Self, path: String) -> _Self:
        self.__init__(Path(path.native))
        return self


filesystem.define("Directory", Directory)
