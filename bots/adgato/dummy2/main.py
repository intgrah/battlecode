import hashlib
from types import MethodDescriptorType
from cambc import Controller

CT_HASH = "f9216f08210068b4243a01e0065ca90276a92d0c6baea2a0b9fc1aa72c36295b"

def ct_changed(ct: object) -> bool:
    cls = ct.__class__
    hash_engine = hashlib.sha256()
    
    for name in sorted(cls.__dict__.keys()):
        attr = cls.__dict__[name]
        hash_engine.update(name.encode('utf-8'))

        if isinstance(attr, MethodDescriptorType):
            obj_class = getattr(attr, "__objclass__", cls).__name__
            id_string = f"{obj_class}.{name}"
            hash_engine.update(id_string.encode('utf-8'))

    digest = hash_engine.hexdigest()
    return digest != CT_HASH


class Player:

    def __init__(self):
        pass

    def run(self, ct: Controller):
        #if ct_changed(ct):
        #    return
        #counter = 0
        #while ct.get_cpu_time_elapsed() < 1950:
        #    counter += 1
        pass