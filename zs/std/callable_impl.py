from miniz.concrete.oop import Class
from miniz.concrete.overloading import OverloadGroup, OverloadGroupType
from miniz.core import ObjectProtocol
from miniz.generic import IGeneric
from miniz.generic.function import GenericFunctionInstanceType, GenericFunctionInstance
from miniz.interfaces.overloading import Argument
from miniz.type_system import OOPDefinitionType
from miniz.vm import instructions as vm

from utilz.callable import ICallable
from utilz.code_generation.core import CodeGenerationResult
from utilz.code_generation.interfaces import CallSiteCode


class __OverloadGroupICallable(ICallable[OverloadGroupType]):
    def curvy_call(self, compiler, group: OverloadGroup, args: list[Argument], kwargs: list[tuple[str, Argument]]) -> CodeGenerationResult:
        matches = group.match(args, kwargs, strict=True, recursive=False)

        if not matches:
            matches = group.match(args, kwargs, strict=False, recursive=True)

        if len(matches) != 1:
            raise TypeError(f"Could not find a suitable overload")

        match = matches[0]

        return CallSiteCode([
            *sum((arg.code for arg in match.matched_args), []),
            *sum((arg.code for arg in match.matched_kwargs.values()), []),
            *((match.call_instruction,) if match.has_callee else match.callee_instructions),
        ])

    def square_call(self, compiler, group: OverloadGroup, args: list[Argument], kwargs: dict[str, Argument]) -> CodeGenerationResult:
        if kwargs:
            raise TypeError(f"Generic instantiation is not allowed with keyword arguments yet.")

        result = []

        for overload in group.overloads:
            if not isinstance(overload, IGeneric):
                continue

            try:
                result.append(overload.instantiate_generic([arg.code[0].object for arg in args]))
            except ValueError:
                ...

        if len(result) != 1:
            raise TypeError(f"Could not find a suitable overload")

        return CodeGenerationResult([
            vm.LoadObject(result[0])
        ])


class __OOPDefinitionTypeICallable(ICallable[OOPDefinitionType]):
    def curvy_call(self, compiler, cls: Class, args: list[Argument], kwargs: list[tuple[str, Argument]]) -> CodeGenerationResult:
        args.insert(0, Argument([], cls))

        matches = cls.constructor.match(args, kwargs, strict=True, recursive=False)

        if not matches:
            matches = cls.constructor.match(args, kwargs, strict=False, recursive=True)

        if len(matches) != 1:
            raise TypeError(f"Could not find a suitable overload")

        match = matches[0]

        return CallSiteCode([
            *sum((arg.code for arg in match.matched_args), []),
            *sum((arg.code for arg in match.matched_kwargs.values()), []),
            vm.CreateInstance(match.callee),
        ])

    def square_call(self, compiler, cls: Class, args: list[Argument], kwargs: dict[str, Argument]) -> CodeGenerationResult:
        if kwargs:
            raise TypeError(f"Generic instantiation is not allowed with keyword arguments yet.")

        result = cls.instantiate_generic([compiler.vm.run(arg.code).pop() for arg in args])

        return CodeGenerationResult([
            vm.LoadObject(result)
        ])


class __ClassICallable(ICallable[Class]):
    def curvy_call(self: Class, compiler, item: ObjectProtocol, args: list[Argument], kwargs: list[tuple[str, Argument]]) -> CodeGenerationResult:
        matches = self.get_name(f"_()")

        if not matches:
            raise TypeError

        assert isinstance(matches, OverloadGroup)

        args.insert(0, Argument(item, self))

        return matches.runtime_type.curvy_call(compiler, matches, args, kwargs)

    def square_call(self: Class, compiler, item: ObjectProtocol, args: list[Argument], kwargs: list[tuple[str, Argument]]) -> CodeGenerationResult:
        matches = self.get_name(f"_[]")

        if not matches:
            raise TypeError

        assert isinstance(matches, OverloadGroup)

        args.insert(0, Argument(item, self))

        return matches.runtime_type.curvy_call(compiler, matches, args, kwargs)


class __GenericFunctionInstanceICallable(ICallable[GenericFunctionInstanceType]):
    def curvy_call(self, compiler, fn: GenericFunctionInstance, args: list[Argument], kwargs: list[tuple[str, Argument]]) -> CodeGenerationResult:
        match = fn.origin.match(args, kwargs)

        if match is None:
            raise TypeError(f"Can't call '{fn}' with specified arguments")

        if not match.has_callee:
            raise TypeError(f"Generic function may only be called directly")

        match.callee = fn
        match.call_instruction = type(match.call_instruction)(fn)

        return CallSiteCode([
            *sum((arg.code for arg in match.matched_args), []),
            *sum((arg.code for arg in match.matched_kwargs.values()), []),
            *((match.call_instruction,) if match.has_callee else match.callee_instructions),
        ])

    def square_call(self, compiler, fn: GenericFunctionInstance, args: list[Argument], kwargs: dict[str, Argument]) -> CodeGenerationResult:
        if kwargs:
            raise TypeError(f"Generic instantiation is not allowed with keyword arguments yet.")

        raise TypeError(f"Can't generic instantiate a generic instantiation")
