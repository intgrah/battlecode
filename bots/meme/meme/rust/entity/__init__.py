from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Final

from cambc import EntityType, Team

from rust.base import RustStruct, enum_u8, i32, position, u32, u64

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

_TAG_TO_ENTITY_TYPE: tuple[EntityType, ...] = (
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
    EntityType.GUNNER,
    EntityType.SENTINEL,
    EntityType.BREACH,
    EntityType.LAUNCHER,
)


class EntityBase(RustStruct):
    """
    EntityBase (24 B, align 4):

      +0   4  id        i32
      +4   8  position  Pos
      +12  4  hp        i32
      +16  4  max_hp    i32
      +20  1  team      Team
    """

    _ID_OFF: Final = 0
    _POSITION_OFF: Final = 4
    _HP_OFF: Final = 12
    _MAX_HP_OFF: Final = 16
    _TEAM_OFF: Final = 20

    id = u32(_ID_OFF)
    position = position(_POSITION_OFF)
    hp = i32(_HP_OFF)
    max_hp = i32(_MAX_HP_OFF)
    team = enum_u8(_TEAM_OFF, tuple(Team))


class Variant(RustStruct):
    """
    Common base for all 15 Entity variants.

    Each variant subclass sets `_BASE_OFF` — the bucket offset where the
    variant's `EntityBase` starts. Subclasses inherit `.base` from here.
    """

    _BASE_OFF: ClassVar[int]

    @property
    def base(self) -> EntityBase:
        return EntityBase(self._raw, self._addr + self._BASE_OFF)


# Per-variant EntityBase offsets within Entity (matches deref jump table at rodata 0xbbaa0).
_BASE_OFF_BY_TYPE: dict[EntityType, int] = {
    EntityType.CORE: 32,
    EntityType.BUILDER_BOT: 16,
    EntityType.ROAD: 8,
    EntityType.BARRIER: 8,
    EntityType.MARKER: 12,
    EntityType.HARVESTER: 12,
    EntityType.CONVEYOR: 16,
    EntityType.SPLITTER: 16,
    EntityType.ARMOURED_CONVEYOR: 16,
    EntityType.BRIDGE: 24,
    EntityType.FOUNDRY: 16,
    EntityType.GUNNER: 20,
    EntityType.SENTINEL: 20,
    EntityType.BREACH: 20,
    EntityType.LAUNCHER: 20,
}


class Entity(RustStruct):
    """
    HashMap<i32, Entity> bucket (72 B, align 8):

      +0   4   key           i32
      +4   4   pad
      +8   64  entity        Entity (enum, 64 B)

    Entity discriminant uses a niche on `Core.received: Vec<ResourceType>.cap`
    at Entity[0..8]:
      word0 high bit clear → Core   (cap is a valid Vec capacity)
      word0 high bit set   → tag = word0 & 0x7FFF_FFFF_FFFF_FFFF
    """

    SLOT_SIZE: Final = 72
    _KEY_OFF: Final = 0
    _ENTITY_OFF: Final = 8

    key = u32(_KEY_OFF)
    _word0 = u64(_ENTITY_OFF)

    def __init__(self, raw: RawMem, slot: int) -> None:
        super().__init__(raw, slot)

    @property
    def entity_type(self) -> EntityType:
        w = self._word0
        if w >> 63 == 0:
            return EntityType.CORE
        return _TAG_TO_ENTITY_TYPE[w & 0x7FFF_FFFF_FFFF_FFFF]

    @property
    def base(self) -> EntityBase:
        off = Entity._ENTITY_OFF + _BASE_OFF_BY_TYPE[self.entity_type]
        return EntityBase(self._raw, self._addr + off)

    def __repr__(self) -> str:
        b = self.base
        p = b.position
        return f"Entity({self.entity_type.value} id={b.id} pos={p} hp={b.hp} team={b.team})"
