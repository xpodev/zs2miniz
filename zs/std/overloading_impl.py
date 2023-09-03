from miniz.concrete.function import Function
from miniz.concrete.oop import Method
from miniz.concrete.signature import Parameter
from miniz.core import TypeProtocol
from miniz.generic import GenericParameter
from miniz.interfaces.oop import Binding
from miniz.interfaces.overloading import IOverloaded, Argument, OverloadMatchResult
from miniz.vm import instructions as vm


class _FunctionIOverloaded(IOverloaded[Function]):
    def match(
            self: Function,
            positional_arguments: list[Argument],
            named_arguments: list[tuple[str, Argument]],
            *,
            strict: bool = False,
            type_mappings: dict[GenericParameter, TypeProtocol] = None,
            **kwargs
    ) -> OverloadMatchResult | None:
        from miniz.type_system import assignable_to, are_identical

        compare_type = assignable_to if not strict else are_identical

        args_match: dict[Parameter, Argument] = {}
        kwargs_match: dict[Parameter, Argument] = {}

        if type_mappings is None:
            type_mappings = {}

        def check_assignability(source: TypeProtocol, target: Parameter):
            if isinstance(target.parameter_type, GenericParameter):
                try:
                    generic_type = type_mappings[target.parameter_type]
                except KeyError:
                    generic_type = type_mappings[target.parameter_type] = source
                return compare_type(source, generic_type)
            return compare_type(source, target.parameter_type)

        sig = self.signature
        if len(positional_arguments) > len(sig.positional_parameters) and sig.variadic_positional_parameter is None:
            return None
        if len(named_arguments) > len(sig.named_parameters) and sig.variadic_named_parameter is None:
            return None

        for arg, param in zip(positional_arguments, sig.positional_parameters):
            if not check_assignability(arg.type, param):
                return None
            args_match[param] = arg
        if len(positional_arguments) > len(sig.positional_parameters):
            for arg in positional_arguments[len(sig.positional_parameters):]:
                if not check_assignability(arg.type, sig.variadic_positional_parameter):
                    return None
                raise TypeError(f"Variadic parameters are not supported yet")
        elif len(positional_arguments) < len(sig.positional_parameters):
            for param in sig.positional_parameters[len(positional_arguments):]:
                if not param.has_default_value:
                    return None
                args_match[param] = Argument([vm.LoadObject(param.default_value)], param.parameter_type)

        kw_params = {
            param.name: param for param in sig.named_parameters
        }
        for name, arg in named_arguments:
            try:
                param = kw_params[name]
                kwargs_match[param] = arg
            except KeyError:
                if sig.variadic_named_parameter is None:
                    return
                param = sig.variadic_named_parameter
            if not check_assignability(arg.type, param):
                return None
        else:
            if len(named_arguments) > len(sig.named_parameters):
                for arg in positional_arguments[len(sig.named_parameters):]:
                    if not check_assignability(arg.type, sig.variadic_positional_parameter):
                        return None
                    raise TypeError(f"Variadic parameters are not supported yet")
            elif len(named_arguments) < len(sig.named_parameters):
                for param in sig.named_parameters[len(named_arguments):]:
                    if not param.has_default_value:
                        return None
                    kwargs_match[param] = Argument([vm.LoadObject(param.default_value)], param.parameter_type)

        result = OverloadMatchResult()
        result.matched_args = [
            args_match[param] for param in sig.positional_parameters
        ]
        result.matched_kwargs = {
            param.name: kwargs_match[param] for param in sig.named_parameters
        }
        result.callee = self
        result.call_instruction = vm.Call(self)

        result.unmatched_args = result.unmatched_kwargs = None

        return result


class _MethodIOverloaded(IOverloaded[Method]):
    def match(
            self: Method,
            positional_arguments: list[Argument],
            named_arguments: list[tuple[str, Argument]],
            *,
            strict: bool = False,
            type_mappings: dict[GenericParameter, TypeProtocol] = None,
            instance: Argument = None,
            **kwargs
    ) -> OverloadMatchResult | None:
        from miniz.type_system import assignable_to, are_identical

        compare_type = assignable_to if not strict else are_identical

        if instance and self.is_instance_bound:
            positional_arguments = [instance, *positional_arguments]

        args_match: dict[Parameter, Argument] = {}
        kwargs_match: dict[Parameter, Argument] = {}

        if type_mappings is None:
            type_mappings = {}

        def check_assignability(source: TypeProtocol, target: Parameter):
            if isinstance(target.parameter_type, GenericParameter):
                try:
                    generic_type = type_mappings[target.parameter_type]
                except KeyError:
                    generic_type = type_mappings[target.parameter_type] = source
                return compare_type(source, generic_type)
            return compare_type(source, target.parameter_type)

        sig = self.signature
        if len(positional_arguments) > len(sig.positional_parameters) and sig.variadic_positional_parameter is None:
            return None
        if len(named_arguments) > len(sig.named_parameters) and sig.variadic_named_parameter is None:
            return None

        for arg, param in zip(positional_arguments, sig.positional_parameters):
            if not check_assignability(arg.type, param):
                return None
            args_match[param] = arg
        if len(positional_arguments) > len(sig.positional_parameters):
            for arg in positional_arguments[len(sig.positional_parameters):]:
                if not check_assignability(arg.type, sig.variadic_positional_parameter):
                    return None
                raise TypeError(f"Variadic parameters are not supported yet")
        elif len(positional_arguments) < len(sig.positional_parameters):
            for param in sig.positional_parameters[len(positional_arguments):]:
                if not param.has_default_value:
                    return None
                args_match[param] = Argument([vm.LoadObject(param.default_value)], param.parameter_type)

        kw_params = {
            param.name: param for param in sig.named_parameters
        }
        for name, arg in named_arguments:
            try:
                param = kw_params[name]
                kwargs_match[param] = arg
            except KeyError:
                if sig.variadic_named_parameter is None:
                    return
                param = sig.variadic_named_parameter
            if not check_assignability(arg.type, param):
                return None
        else:
            if len(named_arguments) > len(sig.named_parameters):
                for arg in positional_arguments[len(sig.named_parameters):]:
                    if not check_assignability(arg.type, sig.variadic_positional_parameter):
                        return None
                    raise TypeError(f"Variadic parameters are not supported yet")
            elif len(named_arguments) < len(sig.named_parameters):
                for param in sig.named_parameters[len(named_arguments):]:
                    if not param.has_default_value:
                        return None
                    kwargs_match[param] = Argument([vm.LoadObject(param.default_value)], param.parameter_type)

        result = OverloadMatchResult()
        result.matched_args = [
            args_match[param] for param in sig.positional_parameters
        ]
        result.matched_kwargs = {
            param.name: kwargs_match[param] for param in sig.named_parameters
        }
        result.callee = self
        result.call_instruction = vm.Call(self)

        result.unmatched_args = result.unmatched_kwargs = None

        return result

