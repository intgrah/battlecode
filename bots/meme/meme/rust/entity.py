from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import EntityType, Team

from rust.base import RustStruct, enum_u8, i32, u32, u64

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

_ENTITY_BASE_OFF: dict[EntityType, int] = {
    EntityType.CORE: 32,
    EntityType.BUILDER_BOT: 16,
    EntityType.ROAD: 8,
    EntityType.BARRIER: 8,
    EntityType.MARKER: 12,
    EntityType.HARVESTER: 12,
    EntityType.CONVEYOR: 16,
    EntityType.SPLITTER: 16,
    EntityType.ARMOURED_CONVEYOR: 16,
    EntityType.BRIDGE: 16,
    EntityType.FOUNDRY: 16,
    EntityType.GUNNER: 20,
    EntityType.SENTINEL: 20,
    EntityType.BREACH: 20,
    EntityType.LAUNCHER: 20,
}


class EntityBase(RustStruct):
    """EntityBase (24 B): id@0, position.x@4, position.y@8, hp@12, max_hp@16, team@20."""

    id = u32(0)
    x = i32(4)
    y = i32(8)
    hp = i32(12)
    max_hp = i32(16)
    team = enum_u8(20, tuple(Team))


class Entity(RustStruct):
    """
    HashMap<i32, Entity> slot: key i32@0, pad, Entity@8 (slot_size=64).

    Entity (56 B): discriminant niche on Core.received.cap (high bit of usize).
      word0 high bit clear → Core
      word0 high bit set   → tag = word0 & 0x7FFF_FFFF_FFFF_FFFF
    """

    SLOT_SIZE: Final = 64
    KEY_OFF: Final = 0
    _ENTITY_OFF: Final = 8

    key = u32(0)
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
        return EntityBase(
            self._raw,
            self._addr + Entity._ENTITY_OFF + _ENTITY_BASE_OFF[self.entity_type],
        )

    @property
    def id(self) -> int:
        return self.base.id

    @property
    def x(self) -> int:
        return self.base.x

    @property
    def y(self) -> int:
        return self.base.y

    @property
    def hp(self) -> int:
        return self.base.hp

    @hp.setter
    def hp(self, val: int) -> None:
        self.base.hp = val

    @property
    def max_hp(self) -> int:
        return self.base.max_hp

    @property
    def team(self) -> Team:
        return self.base.team

    def __repr__(self) -> str:
        b = self.base
        return f"Entity({self.entity_type.value} id={b.id} pos=({b.x},{b.y}) hp={b.hp} team={b.team})"
