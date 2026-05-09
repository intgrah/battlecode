from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rust.base import U64, RustStruct

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
    `.get()`.

    Lookups use a per-instance `dict[K, int]` cache mapping each key to
    its bucket address. Entries are populated lazily during scans and
    invalidated whenever `ctrl_ptr` changes (which only happens on a
    hashbrown reallocation — i.e. an insert that grew the table). With
    a stable `ctrl_ptr`, repeated lookups are O(1).

    Caller supplies:
      slot_size — sizeof((K, V)) tuple incl. padding (= bucket stride).
      key       — (raw, slot_addr) → K, reads one bucket's key.
      value     — (raw, slot_addr) → V, reads one bucket's value.
    """

    _CTRL_OFF: Final = 0
    _BUCKET_MASK_OFF: Final = 8
    _GROWTH_LEFT_OFF: Final = 16
    _ITEMS_OFF: Final = 24

    _ctrl = U64(_CTRL_OFF)
    _bucket_mask = U64(_BUCKET_MASK_OFF)
    _growth_left = U64(_GROWTH_LEFT_OFF)
    _items = U64(_ITEMS_OFF)

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
        self._cached_ctrl: int = 0
        self._cache: dict[K, int] = {}
        self._cache_complete: bool = False

    def _check_ctrl(self) -> None:
        """Drop the cache if hashbrown has reallocated since last use."""
        ctrl = self._ctrl
        if ctrl != self._cached_ctrl:
            self._cache.clear()
            self._cache_complete = False
            self._cached_ctrl = ctrl

    def _slots(self) -> Iterator[int]:
        bm = self._bucket_mask
        if bm == 0:
            return
        ctrl = self._ctrl
        slot_size = self._slot_size
        for i in range(bm + 1):
            if self._raw.read_u8(ctrl + i) & 0x80 == 0:
                yield ctrl - (i + 1) * slot_size

    def _slot_for(self, key: K) -> int | None:
        """Find the bucket address for `key`, or None. Caches as it scans."""
        self._check_ctrl()
        cached = self._cache.get(key)
        if cached is not None or self._cache_complete:
            return cached
        for s in self._slots():
            k = self._key(self._raw, s)
            self._cache[k] = s
            if k == key:
                return s
        self._cache_complete = True
        return None

    def __len__(self) -> int:
        return self._items

    def __iter__(self) -> Iterator[K]:
        # Populate the cache as a side effect — every key gets memoized.
        self._check_ctrl()
        if self._cache_complete:
            yield from self._cache
            return
        for s in self._slots():
            k = self._key(self._raw, s)
            self._cache[k] = s
            yield k
        self._cache_complete = True

    def __contains__(self, key: K) -> bool:
        return self._slot_for(key) is not None

    def __getitem__(self, key: K) -> V:
        s = self._slot_for(key)
        if s is None:
            raise KeyError(key)
        return self._value(self._raw, s)

    def get(self, key: K, default: V | None = None) -> V | None:
        s = self._slot_for(key)
        return default if s is None else self._value(self._raw, s)

    def keys(self) -> Iterator[K]:
        return iter(self)

    def values(self) -> Iterator[V]:
        for k in self:
            yield self._value(self._raw, self._cache[k])

    def items(self) -> Iterator[tuple[K, V]]:
        for k in self:
            yield k, self._value(self._raw, self._cache[k])
