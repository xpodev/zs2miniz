from dotnet import DotNETCompiler, DotNETContext
from miniz import type_system as ts
from miniz.concrete.module import Module
from zs.zs2miniz.toolchain import Toolchain
from zs.zs_compiler import ZSCompiler

from zs.processing import State

from zs.std.modules.module_core import core
from zs.std.modules.module_filesystem import filesystem
from zs.std.modules.module_srf import srf

from zs.std.parsers import base as base_language


def main():
    project_name = "zscore"
    from Mono import Cecil as mc
    import System
    assembly = mc.AssemblyDefinition.CreateAssembly(mc.AssemblyNameDefinition(project_name, System.Version("1.0.0")), project_name, mc.ModuleKind.Dll)

    state = State()

    parser = base_language.get_parser(state)

    parser.setup()

    compiler = ZSCompiler(toolchain=Toolchain(state=state, parser=parser))
    context = compiler.toolchain.context

    dotnet_compiler = DotNETCompiler(DotNETContext.standard(assembly.MainModule.TypeSystem))

    context.add_module_to_cache("core", core)
    context.add_module_to_cache("srf", srf)
    context.add_module_to_cache("filesystem", filesystem)

    module = Module("zscore")
    for cls in [
        ts.Unit,
        ts.Boolean,
        ts.Null,
        ts.Any,
        ts.Void
    ]:
        module._classes.append(cls)

    dotnet_compiler.compile_module(module, assembly.MainModule)

    assembly.Write(project_name + ".dll")


main()
