from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, auto

from .xor import decrypt, encrypt

CLAIM_TTL = 8

_TAG_SHIFT = 28
_TAG_MASK = 0xF


class TaskKind(IntEnum):
    NAV_ORE = auto()
    FIX_EXCESS = auto()


@dataclass(frozen=True)
class MarkerTaskClaim:
    kind: TaskKind
    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (
            (0 << _TAG_SHIFT) | (self.kind << 23) | (self.tile_index << 11) | self.turn
        )
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerTaskClaim:
        return MarkerTaskClaim(
            kind=TaskKind((payload >> 23) & 0x1F),
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


@dataclass(frozen=True)
class MarkerEureka:
    symmetry: int

    def encode(self) -> int:
        val = (1 << _TAG_SHIFT) | self.symmetry
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerEureka:
        return MarkerEureka(symmetry=payload & 0x3)


@dataclass(frozen=True)
class MarkerIdleGunner:
    gunner_tile_index: int

    def encode(self) -> int:
        val = (2 << _TAG_SHIFT) | (self.gunner_tile_index & 0xFFF)
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerIdleGunner:
        return MarkerIdleGunner(gunner_tile_index=payload & 0xFFF)


type Marker = MarkerTaskClaim | MarkerEureka | MarkerIdleGunner


def decode(encrypted: int) -> Marker | None:
    raw = decrypt(encrypted)
    tag = (raw >> _TAG_SHIFT) & _TAG_MASK
    payload = raw & 0x0FFFFFFF
    match tag:
        case 0:
            return MarkerTaskClaim.decode(payload)
        case 1:
            return MarkerEureka.decode(payload)
        case 2:
            return MarkerIdleGunner.decode(payload)
        case _:
            return None


def is_stale(claim: MarkerTaskClaim, current_turn: int) -> bool:
    age = current_turn - claim.turn
    return age >= CLAIM_TTL or age < 0
