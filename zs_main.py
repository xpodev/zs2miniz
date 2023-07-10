import sys

from pathlib import Path

from dotnet import DotNETCompiler, DotNETContext
from miniz.concrete.module import Module
from zs.std.importers import ZSImporter, ModuleImporter
from zs.zs_compiler import ZSCompiler

from zs.cli.options import Options, get_options, InitOptions

from zs.modules.module_core import module as core

from zs.std.parsers import base as base_language


def main(options: Options):
    if isinstance(options, InitOptions):
        from zs import project
        return project.init(options)

    project_name = Path(options.source).name.split('.')[0].replace('_', ' ').title().replace(' ', "")
    from Mono import Cecil as mc
    import System
    assembly = mc.AssemblyDefinition.CreateAssembly(mc.AssemblyNameDefinition(project_name, System.Version("1.0.0")), project_name, mc.ModuleKind.Dll)

    dotnet_compiler = DotNETCompiler(DotNETContext.standard(assembly.MainModule.TypeSystem))

    compiler = ZSCompiler(parser=base_language.get_parser)
    context = compiler.context
    state = compiler.state

    compiler.toolchain.parser.setup()

    context.import_system.add_directory(Path(options.source).parent)

    context.import_system.add_importer(ZSImporter(compiler.context.import_system), ".zs")
    context.import_system.add_importer(ModuleImporter(compiler), "module")

    context.add_module("core", core)
    # context.add_module("srf", srf)
    # context.add_module("filesystem", filesystem)

    try:
        result = compiler.import_document(options.source)
    except Exception as e:
        raise e
    else:
        module = result.object_scope.lookup_name(project_name)
        if not isinstance(module, Module):
            raise TypeError

        dotnet_compiler.compile_module(module, assembly.MainModule)
        assembly.Write(module.name + ".dll")
    finally:
        state.reset()

        for message in state.messages:
            print(f"[{message.processor.__class__.__name__}] [{message.type.value}] {message.origin} -> {message.content}")


if __name__ == '__main__':
    sys.setrecursionlimit(10000)
    main(get_options())
