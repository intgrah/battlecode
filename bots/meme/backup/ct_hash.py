import hashlib
from types import MethodDescriptorType

CT_HASH = "f9216f08210068b4243a01e0065ca90276a92d0c6baea2a0b9fc1aa72c36295b"


def ct_changed(ct: object) -> bool:
    cls = ct.__class__
    hash_engine = hashlib.sha256()

    for name in sorted(cls.__dict__.keys()):
        attr = cls.__dict__[name]
        hash_engine.update(name.encode("utf-8"))

        if isinstance(attr, MethodDescriptorType):
            obj_class = getattr(attr, "__objclass__", cls).__name__
            id_string = f"{obj_class}.{name}"
            hash_engine.update(id_string.encode("utf-8"))

    digest = hash_engine.hexdigest()
    return digest != CT_HASH
