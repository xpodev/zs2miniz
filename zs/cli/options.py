from argparse import ArgumentParser


_arg_parser = ArgumentParser(
    description="The Z# programming language compiler & interpreter bundle"
)


class Options:
    _validate: bool
    _engine: str
    _output: str | None
    _source: str
    _engine_args: list[str]

    def __init__(self, validate: bool = True, engine: str = "run", output: str = None, source: str = "", args: list[str] = None):
        super().__init__()
        self._validate = validate
        self._engine = engine
        self._output = output
        self._source = source
        self._engine_args = args

    @property
    def validate(self):
        return self._validate

    @property
    def engine(self):
        return self._engine

    @property
    def output(self):
        return self._output

    @property
    def source(self):
        return self._source

    @property
    def engine_args(self):
        return self._engine_args

    @classmethod
    def from_args(cls, ns, rest) -> "Options":
        return Options(ns.validate, ns.engine, ns.output, ns.source, rest)


class InitOptions:
    _project_name: str | None
    _source_directory: bool

    def __init__(self, name: str | None, src: bool = True):
        self._project_name = name
        self._source_directory = src

    @property
    def project_name(self):
        return self._project_name

    @property
    def source_directory(self):
        return self._source_directory

    @classmethod
    def from_args(cls, ns, _):
        return cls(ns.project_name)


_sub_parsers = _arg_parser.add_subparsers()

_options_parser = _sub_parsers.add_parser("c")
_options_parser.add_argument("-v", "--validate", action="store_true", default=False)
_options_parser.add_argument("-e", "--engine", choices=["run"], default="run")
_options_parser.add_argument("-o", "--output", default=None)
_options_parser.add_argument("source")
_options_parser.set_defaults(constructor=Options.from_args)

_init_project_parser = _sub_parsers.add_parser("init")
_init_project_parser.add_argument("--src", action="store_true")
_init_project_parser.set_defaults(constructor=InitOptions.from_args, project_name=None)

_new_project_parser = _sub_parsers.add_parser("new")
_new_project_parser.add_argument("project_name")
# _new_project_parser.add_argument("--src", action="store_true")
_new_project_parser.set_defaults(constructor=InitOptions.from_args)


def get_options() -> Options | InitOptions:
    args, rest = _arg_parser.parse_known_args()
    return args.constructor(args, rest)
