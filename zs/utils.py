def make_tuple(value):
    return (value,) if value is not None else ()


def code_generation(fn):
    fn.__code_generation__ = True
    return fn


def is_code_generation_function(fn):
    return getattr(fn, "__code_generation__", False)


class SingletonMeta(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
