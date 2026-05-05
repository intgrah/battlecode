from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import EntityType, Team

if TYPE_CHECKING:
    from collections.abc import Iterator

    from raw_mem import RawMem

_DISC_TO_ENTITY_TYPE: tuple[EntityType, ...] = (
    EntityType.BUILDER_BOT,
    EntityType.CONVEYOR,
    EntityType.SPLITTER,
    EntityType.ARMOURED_CONVEYOR,
    EntityType.BRIDGE,
    EntityType.HARVESTER,
    EntityType.FOUNDRY,
    EntityType.ROAD,
    EntityType.BARRIER,
    EntityType.MARKER,
    EntityType.CORE,
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.BREACH,
    EntityType.LAUNCHER,
)

_DISC_TO_TEAM: tuple[Team, ...] = tuple(Team)


class Vec:
    """
    Vec<T> layout (cap-first, as observed in this build):

      +0:  cap  usize
      +8:  ptr  *T
      +16: len  usize
    """

    _CAP_OFF: Final = 0
    _PTR_OFF: Final = 8
    _LEN_OFF: Final = 16

    def __init__(self, raw: RawMem, addr: int, elem_size: int) -> None:
        self._raw: Final = raw
        self._addr: Final = addr
        self._elem_size: Final = elem_size

    @property
    def _ptr(self) -> int:
        return self._raw.read_u64(self._addr + Vec._PTR_OFF)

    def __len__(self) -> int:
        return self._raw.read_u64(self._addr + Vec._LEN_OFF)

    def __getitem__(self, i: int) -> int:
        n = len(self)
        if i < 0 or i >= n:
            raise IndexError(i)
        return self._raw.read_u32(self._ptr + i * self._elem_size)

    def __iter__(self) -> Iterator[int]:
        ptr = self._ptr
        es = self._elem_size
        for i in range(len(self)):
            yield self._raw.read_u32(ptr + i * es)


class HashMap:
    """
    HashMap<K, V> layout (RawTable first, then RandomState — Rust places larger field first):

      +0:  ctrl: *u8                  (pointer to control byte array)
      +8:  bucket_mask: usize
      +16: growth_left: usize
      +24: items: usize               (number of occupied entries)
      +32: hash_builder: RandomState  (16 bytes, not read)

    Control byte semantics:
      0x80       = empty
      0xFE       = deleted (tombstone)
      0x00-0x7F  = occupied (low 7 bits of h2 hash)

    Slot i is located at:  ctrl_ptr - (capacity - i) * slot_size
    where capacity = bucket_mask + 1.

    slot_size and key_size must match the (K, V) Rust layout including
    any alignment padding between K and V.
    """

    _CTRL_OFF: Final = 0
    _BUCKET_MASK_OFF: Final = 8
    _GROWTH_LEFT_OFF: Final = 16
    _ITEMS_OFF: Final = 24

    def __init__(
        self, raw: RawMem, addr: int, *, slot_size: int, key_size: int
    ) -> None:
        self._raw: Final = raw
        self._addr: Final = addr
        self._slot_size: Final = slot_size
        self._key_size: Final = key_size

    @property
    def _ctrl_ptr(self) -> int:
        return self._raw.read_u64(self._addr + HashMap._CTRL_OFF)

    @property
    def _bucket_mask(self) -> int:
        return self._raw.read_u64(self._addr + HashMap._BUCKET_MASK_OFF)

    @property
    def items(self) -> int:
        return self._raw.read_u64(self._addr + HashMap._ITEMS_OFF)

    def _occupied_slots(self) -> Iterator[int]:
        """Yield the address of each occupied slot."""
        bucket_mask = self._bucket_mask
        ctrl_ptr = self._ctrl_ptr
        if bucket_mask == 0:
            return
        capacity = bucket_mask + 1
        slot_size = self._slot_size
        for i in range(capacity):
            if self._raw.read_u8(ctrl_ptr + i) & 0x80 == 0:
                yield ctrl_ptr - (capacity - i) * slot_size

    def keys_i32(self) -> Iterator[int]:
        """Iterate all keys when K = i32."""
        for slot in self._occupied_slots():
            yield self._raw.read_u32(slot)

    def value_addr(self, slot_addr: int) -> int:
        """Address of V within a slot, aligned up from key_size."""
        key_end = slot_addr + self._key_size
        align = self._slot_size - self._key_size
        return (key_end + align - 1) & ~(align - 1)


class Entity:
    """
    HashMap<i32, Entity> slot layout (Rust reorders (i32, Entity) — Entity first, align 8):
      +0:   entity data  (64 bytes)
      +64:  key i32      (4 bytes)
      slot_size = 72

    Entity enum in memory:
      +0:  discriminant  u8  (see _ENTITY_KINDS)
      +1-7: padding
      +8:  variant data

    EntityBase (first in every variant's chain):
      +8:  id          i32
      +12: position.x  i32
      +16: position.y  i32
      +20: hp          i32
      +24: max_hp      i32
      +28: team        u8  (0=A, 1=B)
    """

    SLOT_SIZE: Final = 72
    KEY_OFF: Final = 64
    _DATA: Final = 8

    def __init__(self, raw: RawMem, slot: int) -> None:
        self._raw: Final = raw
        self._slot: Final = slot

    @property
    def entity_type(self) -> EntityType:
        return _DISC_TO_ENTITY_TYPE[self._raw.read_u8(self._slot)]

    @property
    def key(self) -> int:
        return self._raw.read_u32(self._slot + Entity.KEY_OFF)

    @property
    def id(self) -> int:
        return self._raw.read_u32(self._slot + Entity._DATA)

    @property
    def x(self) -> int:
        return self._raw.read_u32(self._slot + Entity._DATA + 4)

    @property
    def y(self) -> int:
        return self._raw.read_u32(self._slot + Entity._DATA + 8)

    @property
    def hp(self) -> int:
        return self._raw.read_u32(self._slot + Entity._DATA + 12)

    @property
    def max_hp(self) -> int:
        return self._raw.read_u32(self._slot + Entity._DATA + 16)

    @property
    def team(self) -> Team:
        return _DISC_TO_TEAM[self._raw.read_u8(self._slot + Entity._DATA + 20)]

    def __repr__(self) -> str:
        return f"Entity({self.entity_type.value} id={self.id} pos=({self.x},{self.y}) hp={self.hp} team={self.team})"
