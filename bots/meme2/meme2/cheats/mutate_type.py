"""Manipulate `tp_flags` on a CPython type.

PyO3 `#[pyclass]` types set `Py_TPFLAGS_IMMUTABLETYPE` (1<<8), so plain
`Controller.get_team = func` raises `TypeError: cannot set attribute`.
Clearing the bit allows the assignment.

CPython also caches method lookups when `Py_TPFLAGS_VALID_VERSION_TAG`
(1<<19) is set. Normal Python `setattr(cls, ...)` calls
`PyType_Modified` which clears this bit and invalidates the cache; raw
memory writes do not. So after the override, we must also clear the
version tag, otherwise `instance.method()` keeps resolving to the
cached original method even though `cls.method` is the new function.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

PY_TPFLAGS_IMMUTABLETYPE: Final = 1 << 8
PY_TPFLAGS_VALID_VERSION_TAG: Final = 1 << 19
TP_FLAGS_OFFSET: Final = 168


def make_type_mutable(cls: type, raw: RawMem) -> int:
    """Clear `Py_TPFLAGS_IMMUTABLETYPE`. Returns original `tp_flags`."""
    addr = raw.id(cls)
    flags = raw.read_u64(addr + TP_FLAGS_OFFSET)
    raw.write_u64(addr + TP_FLAGS_OFFSET, flags & ~PY_TPFLAGS_IMMUTABLETYPE)
    return flags


def restore_type_flags_invalidate_cache(cls: type, raw: RawMem, flags: int) -> None:
    """Restore `flags` but with `Py_TPFLAGS_VALID_VERSION_TAG` cleared,
    so the method cache is rebuilt on the next attribute lookup."""
    addr = raw.id(cls)
    raw.write_u64(addr + TP_FLAGS_OFFSET, flags & ~PY_TPFLAGS_VALID_VERSION_TAG)


def restore_type_flags(cls: type, raw: RawMem, flags: int) -> None:
    addr = raw.id(cls)
    raw.write_u64(addr + TP_FLAGS_OFFSET, flags)
