from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import RustStruct, u64

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from rust.raw_mem import RawMem


class HashMap[K, V](RustStruct):
    """
    std::HashMap<K, V> (48 B, align 8):

      +0   8   ctrl          *u8 (NonNull)
      +8   8   bucket_mask   usize
      +16  8   growth_left   usize
      +24  8   items         usize
      +32  16  hash_builder  RandomState

    Viewed as a Python `Mapping[K, V]`. Supports `len(hm)`, `key in hm`,
    `hm[key]`, iteration over keys, `.keys()`, `.values()`, `.items()`,
    `.get()`. Lookups are linear over occupied buckets — fine for the
    typical Battlecode case (<50 entries).

    Caller supplies:
      slot_size — sizeof((K, V)) tuple incl. padding (= bucket stride).
      key       — (raw, slot_addr) → K, reads one bucket's key.
      value     — (raw, slot_addr) → V, reads one bucket's value.
    """

    _CTRL_OFF: Final = 0
    _BUCKET_MASK_OFF: Final = 8
    _GROWTH_LEFT_OFF: Final = 16
    _ITEMS_OFF: Final = 24

    _ctrl = u64(_CTRL_OFF)
    _bucket_mask = u64(_BUCKET_MASK_OFF)
    _growth_left = u64(_GROWTH_LEFT_OFF)
    _items = u64(_ITEMS_OFF)

    def __init__(
        self,
        raw: RawMem,
        addr: int,
        *,
        slot_size: int,
        key: Callable[[RawMem, int], K],
        value: Callable[[RawMem, int], V],
    ) -> None:
        super().__init__(raw, addr)
        self._slot_size: Final = slot_size
        self._key: Final = key
        self._value: Final = value

    def _slots(self) -> Iterator[int]:
        bm = self._bucket_mask
        if bm == 0:
            return
        ctrl = self._ctrl
        slot_size = self._slot_size
        for i in range(bm + 1):
            if self._raw.read_u8(ctrl + i) & 0x80 == 0:
                yield ctrl - (i + 1) * slot_size

    def __len__(self) -> int:
        return self._items

    def __iter__(self) -> Iterator[K]:
        for s in self._slots():
            yield self._key(self._raw, s)

    def __contains__(self, key: K) -> bool:
        return any(self._key(self._raw, s) == key for s in self._slots())

    def __getitem__(self, key: K) -> V:
        for s in self._slots():
            if self._key(self._raw, s) == key:
                return self._value(self._raw, s)
        raise KeyError(key)

    def get(self, key: K, default: V | None = None) -> V | None:
        for s in self._slots():
            if self._key(self._raw, s) == key:
                return self._value(self._raw, s)
        return default

    def keys(self) -> Iterator[K]:
        return iter(self)

    def values(self) -> Iterator[V]:
        for s in self._slots():
            yield self._value(self._raw, s)

    def items(self) -> Iterator[tuple[K, V]]:
        for s in self._slots():
            yield self._key(self._raw, s), self._value(self._raw, s)
