from miniz.concrete.oop import Class, MethodGroup
from miniz.core import ScopeProtocol, ObjectProtocol
from miniz.interfaces.oop import IField, IMethod, IOOPMemberDefinition, Binding, IProperty
from miniz.type_system import OOPDefinitionType
from miniz.vm import instructions as vm
from utilz.code_generation.code_objects import BoundMemberCode
from utilz.code_generation.core import CodeGenerationResult
from utilz.scope import IScope


class __ScopeProtocolIScope(IScope[ScopeProtocol]):
    def get_member(self: ScopeProtocol, item: CodeGenerationResult, name: str) -> CodeGenerationResult:
        return CodeGenerationResult([vm.LoadObject(self.get_name(name))])


class __OOPDefinitionTypeIScope(IScope[OOPDefinitionType]):
    def get_member(self: OOPDefinitionType, item: CodeGenerationResult, name: str) -> CodeGenerationResult | ObjectProtocol:
        member = self.get_name(name)

        member_code = []

        if isinstance(member, IField):
            if member.is_static_bound:
                member_code.append(vm.LoadField(member))
            elif member.is_instance_bound:
                return member
        elif isinstance(member, IProperty):
            if member.is_static_bound:
                return member
            elif member.is_instance_bound:
                member_code.append(vm.Call(member.getter))
        elif isinstance(member, IMethod):
            # todo: create bound delegate
            ...
        elif isinstance(member, MethodGroup):
            ...

        result = BoundMemberCode(member_code, [], member)

        return result


class __ClassIScope(IScope[Class]):
    def get_member(self: Class, item: CodeGenerationResult, name: str) -> BoundMemberCode:
        member = self.get_name(name)

        member_code = []

        if isinstance(member, IField):
            member_code.append(vm.LoadField(member))
        elif isinstance(member, IProperty):
            member_code.append(vm.Call(member.getter))
        elif isinstance(member, IMethod):
            # todo: create bound delegate
            ...
        elif isinstance(member, MethodGroup):
            member_code.append(vm.LoadObject(member))

        # instance = item.code
        # if isinstance(member, IOOPMemberDefinition):
        #     if member.binding in (Binding.Static, Binding.Class):
        #         instance = []

        result = BoundMemberCode(item.code + member_code, item.code, member)

        return result
