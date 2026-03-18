from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from util import SPOKES

if TYPE_CHECKING:
    from cambc import Direction

_CIPHER = 0  # 0x2120B7E8
_TAG_SHIFT = 28

_DIR_INDEX = {d: i for i, d in enumerate(SPOKES)}


@dataclass
class SpawnMarker:
    spoke_idx: int

    def encode(self) -> int:
        return ((0 << _TAG_SHIFT) | (self.spoke_idx & 0xFFFFFFF)) ^ _CIPHER

    @staticmethod
    def decode(data: int) -> SpawnMarker:
        return SpawnMarker(spoke_idx=data)


@dataclass
class FrontierMarker:
    direction: Direction

    def encode(self) -> int:
        return ((1 << _TAG_SHIFT) | _DIR_INDEX[self.direction]) ^ _CIPHER

    @staticmethod
    def decode(data: int) -> FrontierMarker:
        return FrontierMarker(direction=SPOKES[data & 0x7])


Marker = SpawnMarker | FrontierMarker


def decode(encrypted: int) -> Marker:
    raw = encrypted ^ _CIPHER
    tag = raw >> _TAG_SHIFT
    data = raw & 0xFFFFFFF
    match tag:
        case 0:
            return SpawnMarker.decode(data)
        case 1:
            return FrontierMarker.decode(data)
        case _:
            raise AssertionError
