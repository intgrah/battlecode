from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import RustStruct, u64

if TYPE_CHECKING:
    from collections.abc import Iterator

    from rust.raw_mem import RawMem


class HashMap(RustStruct):
    """
    HashMap<K, V>: ctrl@0 (*u8), bucket_mask@8, growth_left@16, items@24,
    hash_builder (RandomState, 16B) @32 for std HashMap.

    Slot i is at ctrl - (i+1) * slot_size; ctrl byte i at ctrl + i.
    Control byte high bit set ⇒ empty/deleted.
    """

    ctrl = u64(0)
    bucket_mask = u64(8)
    growth_left = u64(16)
    items = u64(24)

    def __init__(
        self, raw: RawMem, addr: int, *, slot_size: int, key_size: int
    ) -> None:
        super().__init__(raw, addr)
        self._slot_size: Final = slot_size
        self._key_size: Final = key_size

    def occupied_slots(self) -> Iterator[int]:
        bucket_mask = self.bucket_mask
        if bucket_mask == 0:
            return
        ctrl = self.ctrl
        slot_size = self._slot_size
        for i in range(bucket_mask + 1):
            if self._raw.read_u8(ctrl + i) & 0x80 == 0:
                yield ctrl - (i + 1) * slot_size

    def keys_i32(self) -> Iterator[int]:
        for slot in self.occupied_slots():
            yield self._raw.read_u32(slot)
