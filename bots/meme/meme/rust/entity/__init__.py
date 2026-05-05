from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cambc import EntityType

from rust.base import RustStruct, u32, u64
from rust.entity.armoured_conveyor import ArmouredConveyor
from rust.entity.barrier import Barrier
from rust.entity.breach import Breach
from rust.entity.bridge import Bridge
from rust.entity.builder_bot import BuilderBot
from rust.entity.conveyor import Conveyor
from rust.entity.core import Core
from rust.entity.foundry import Foundry
from rust.entity.gunner import Gunner
from rust.entity.harvester import Harvester
from rust.entity.launcher import Launcher
from rust.entity.marker import Marker
from rust.entity.road import Road
from rust.entity.sentinel import Sentinel
from rust.entity.splitter import Splitter
from rust.entity.variant import EntityBase, Variant  # noqa: TC001

if TYPE_CHECKING:
    from rust.raw_mem import RawMem

_CORE_TAG: Final = 10

# Variants in source-declaration order. Tag 10 = Core; for non-Core variants
# the niche value at Entity[0..8] is `(1 << 63) | tag` (high bit set), and
# for Core the same bytes hold a valid `Vec.cap` value with the high bit
# CLEAR. Decoding is uniform: if the sign bit is clear, the tag defaults
# to 10 (Core); otherwise the tag is the low bits of the niche.
_TAG_TO_ENTITY_TYPE: tuple[EntityType, ...] = (
    EntityType.BUILDER_BOT,  # 0
    EntityType.CONVEYOR,  # 1
    EntityType.SPLITTER,  # 2
    EntityType.ARMOURED_CONVEYOR,  # 3
    EntityType.BRIDGE,  # 4
    EntityType.HARVESTER,  # 5
    EntityType.FOUNDRY,  # 6
    EntityType.ROAD,  # 7
    EntityType.BARRIER,  # 8
    EntityType.MARKER,  # 9
    EntityType.CORE,  # 10
    EntityType.GUNNER,  # 11
    EntityType.SENTINEL,  # 12
    EntityType.BREACH,  # 13
    EntityType.LAUNCHER,  # 14
)

_VARIANT_CLASS_BY_TYPE: dict[EntityType, type[Variant]] = {
    EntityType.CORE: Core,
    EntityType.BUILDER_BOT: BuilderBot,
    EntityType.ROAD: Road,
    EntityType.BARRIER: Barrier,
    EntityType.MARKER: Marker,
    EntityType.HARVESTER: Harvester,
    EntityType.CONVEYOR: Conveyor,
    EntityType.SPLITTER: Splitter,
    EntityType.ARMOURED_CONVEYOR: ArmouredConveyor,
    EntityType.BRIDGE: Bridge,
    EntityType.FOUNDRY: Foundry,
    EntityType.GUNNER: Gunner,
    EntityType.SENTINEL: Sentinel,
    EntityType.BREACH: Breach,
    EntityType.LAUNCHER: Launcher,
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
        tag = _CORE_TAG if w >> 63 == 0 else w & 0x7FFF_FFFF_FFFF_FFFF
        return _TAG_TO_ENTITY_TYPE[tag]

    @property
    def as_variant(self) -> Variant:
        """Construct the typed variant subclass for this entity."""
        return _VARIANT_CLASS_BY_TYPE[self.entity_type](self._raw, self._addr)

    @property
    def base(self) -> EntityBase:
        return self.as_variant.base

    def __repr__(self) -> str:
        return repr(self.as_variant)
