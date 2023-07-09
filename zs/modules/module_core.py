from miniz.concrete.module import Module
from miniz.type_system import Any, Boolean, Null, Object, String, Type, Unit, Void

module = Module("core")

module.types.append(Any)
module.types.append(Boolean)
module.types.append(Null)
module.types.append(Object)
module.types.append(String)
module.types.append(Type)
module.types.append(Unit)
module.types.append(Void)
