from miniz.concrete.module import Module
from miniz.type_system import ObjectProtocol

from zs.zs2miniz.lib import Scope, DocumentContext


class Context:
    ...


class ToolchainContext(Context):
    _cache: dict[str, "DocumentContext"]
    _modules: dict[str, Module]

    def __init__(self):
        self._cache = {}
        self._modules = {}

    def get_scope_from_cached(self, path: str) -> "DocumentContext | None":
        try:
            return self._cache[path]
        except KeyError:
            return None

    def add_scope_to_cache(self, path: str, scope: "DocumentContext"):
        self._cache[path] = scope

    def add_module_to_cache(self, name: str, module: Module):
        self._modules[name] = module

    def get_module_from_cache(self, name: str) -> Module | None:
        try:
            return self._modules[name]
        except KeyError:
            return None


class GlobalContext(Context):
    """
    This context is shared between all Z# files executing in the current process.
    """

    _globals: "Scope"

    def __init__(self, __globals: "Scope" = None):
        self._globals = __globals or Scope()

    def get_global(self, name: str) -> object:
        return self._globals.lookup_name(name, recursive_lookup=False)

    def del_global(self, name: str):
        self._globals.delete_name(name, recursive_lookup=False, must_exist=True)

    def set_global(self, name: str, value: ObjectProtocol):
        self._globals.create_readonly_name(name, value, getattr(value, "runtime_type", type(value)))
