import sys

from pathlib import Path

from dotnet import DotNETCompiler, DotNETContext
from miniz.concrete.module import Module
from zs.zs2miniz.toolchain import Toolchain
from zs.zs_compiler import ZSCompiler

from zs.cli.options import Options, get_options, InitOptions
from zs.processing import State

from zs.std.modules.module_core import core
from zs.std.modules.module_filesystem import filesystem
from zs.std.modules.module_srf import srf

from zs.std.parsers import base as base_language


def main(options: Options):
    if isinstance(options, InitOptions):
        from zs import project
        return project.init(options)

    project_name = Path(options.source).name.split('.')[0].replace('_', ' ').title().replace(' ', "")
    from Mono import Cecil as mc
    import System
    assembly = mc.AssemblyDefinition.CreateAssembly(mc.AssemblyNameDefinition(project_name, System.Version("1.0.0")), project_name, mc.ModuleKind.Dll)

    state = State()

    parser = base_language.get_parser(state)

    parser.setup()

    compiler = ZSCompiler(toolchain=Toolchain(state=state, parser=parser))
    context = compiler.toolchain.context
    # import_system = compiler.toolchain.interpreter.import_system

    # import_system.add_directory(Path(options.source).parent.resolve())

    dotnet_compiler = DotNETCompiler(DotNETContext.standard(assembly.MainModule.TypeSystem))

    # import_system.add_importer(ZSImporter(import_system, compiler), ".zs")
    # import_system.add_importer(ModuleImporter(compiler), "module")
    # import_system.add_importer(DotNETImporter(dotnet_compiler), "dotnet")

    context.add_module_to_cache("core", core)
    context.add_module_to_cache("srf", srf)
    context.add_module_to_cache("filesystem", filesystem)

    try:
        result = compiler.import_document(options.source)
    except Exception as e:
        raise e
    else:
        module = result.scope.lookup_name(project_name).get()
        if not isinstance(module, Module):
            raise TypeError

        dotnet_compiler.compile_module(module, assembly.MainModule)
        assembly.Write(module.name + ".dll")
        # for module in compiler.context.modules:
        #     if module.entry_point:
        #         print("Module:", module.name, " | Entry:", module.entry_point)
        #     else:
        #         print("Module:", module.name)
        #     for name, member in module.members.items:
        #         print('\t', name, " :: ", member)
    finally:
        state.reset()

        for message in state.messages:
            print(f"[{message.processor.__class__.__name__}] [{message.field_type.value}] {message.origin} -> {message.content}")


if __name__ == '__main__':
    sys.setrecursionlimit(10000)
    main(get_options())
