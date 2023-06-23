from pathlib import Path

from zs.cli.options import InitOptions


def init(options: InitOptions):
    name = options.project_name

    cwd = Path.cwd()

    if name is None:
        project_dir = cwd
    else:
        project_dir = (cwd / name)

        if project_dir.exists():
            raise FileExistsError(f"Directory '{cwd / name}' already exists")

        project_dir.mkdir()

    source_dir = project_dir / "src"
    source_dir.mkdir()

    env_dir = project_dir / "env"
    env_dir.mkdir()

    with (env_dir / "setup-env.zs").open("w") as setup_env:
        setup_env.write("""import {
    Void,
    Unit,
    Any,
    Type,

    Boolean,
    String,
    Int64,
    Float64,

    print,
} from "module:core";

set void = Void;
set unit = Unit;
set any = Any;
set type = Type;

set bool = Boolean;
set string = String;
set i64 = Int64;
set f64 = Float64;

set print = print;
""")

    with (project_dir / f"{name}.main.zs").open("w") as project_file:
        project_file.write('\n'.join([
            "import {} from \"env/setup-env.zs\";",
            f"import {{ {name} }} from \"src/main.zs\";", '',
            f"// here we'll import the compiler and compile the {name} module.", ''
        ]))

    with (source_dir / "main.zs").open("w") as main_file:
        main_file.write('\n'.join([
            f"export module {name} {{", ''
            f"}}", '',
            f"{name}.entry_point = fun() {{",
            "\tprint(\"Hello, World!\");",
            f"}};", ''
        ]))

    with (project_dir / "readme.md").open("w") as readme_file:
        readme_file.write('\n'.join([
            f"# {name}", "",
            "To run the project, `cd` to the project folder and execute the following command:",
            "```cmd", "./run.bat", "```",
            '',
            "You can learn more about Z# in our [documentation](https://xpodev.github.io/zs-py/)."
        ]))

    with (project_dir / "run.bat").open("w") as compile_script:
        compile_script.write(f"py -m zs c ./{name}.main.zs\n")
