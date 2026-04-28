from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final, override

from cambc import EntityType
from util.symmetry import Symmetry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cambc import Controller, Position, Team


class Marker(ABC):
    """Base class. Subclasses are registered and tagged automatically at
    class-definition time: `TAG` is set to the next unused slot in
    `_registry`. No manual tag assignment, no risk of collisions — but tag
    values depend on class-definition order, so don't reorder/delete
    existing subclasses if markers must decode consistently across builds
    (fine within a single run; markers don't persist across runs).
    """

    KEY: Final[int] = 0xDEADBEEF
    TAG_SHIFT: Final[int] = 28
    TAG_MASK: Final[int] = 0xF
    PAYLOAD_MASK: Final[int] = (1 << TAG_SHIFT) - 1

    TAG: ClassVar[int]
    _registry: ClassVar[dict[int, type[Marker]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.TAG = len(Marker._registry)
        Marker._registry[cls.TAG] = cls

    def encode(self) -> int:
        val = (self.TAG << Marker.TAG_SHIFT) | self._encode_payload()
        return val ^ Marker.KEY

    @staticmethod
    def decode(encrypted: int) -> Marker | None:
        raw = encrypted ^ Marker.KEY
        tag = (raw >> Marker.TAG_SHIFT) & Marker.TAG_MASK
        cls = Marker._registry.get(tag)
        if cls is None:
            return None
        return cls._decode_payload(raw & Marker.PAYLOAD_MASK)

    @abstractmethod
    def _encode_payload(self) -> int: ...

    @classmethod
    @abstractmethod
    def _decode_payload(cls, payload: int) -> Marker: ...


@dataclass(frozen=True)
class MarkerSymmetry(Marker):
    symmetry: Symmetry

    @override
    def _encode_payload(self) -> int:
        return self.symmetry.value

    @classmethod
    @override
    def _decode_payload(cls, payload: int) -> MarkerSymmetry:
        return cls(symmetry=Symmetry(payload & 0x3))


def find_symmetry_marker(
    ct: Controller,
    nearby_tiles: Iterable[Position],
    my_team: Team,
) -> Symmetry | None:
    for pos in nearby_tiles:
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            continue
        if ct.get_entity_type(bid) != EntityType.MARKER:
            continue
        if ct.get_team(bid) != my_team:
            continue
        m = Marker.decode(ct.get_marker_value(bid))
        if isinstance(m, MarkerSymmetry):
            return m.symmetry
    return None
