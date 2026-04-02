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
    EXPLORE = auto()


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
class MarkerRole:
    role: int  # 2 bits
    birthday: int  # 11 bits
    turn: int  # 11 bits
    symmetry: int  # 2 bits (ROT=0, HOR=1, VER=2, UNKNOWN=3)

    def encode(self) -> int:
        val = (
            (2 << _TAG_SHIFT)
            | (self.role << 26)
            | (self.birthday << 15)
            | (self.turn << 4)
            | (self.symmetry << 2)
        )
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerRole:
        return MarkerRole(
            role=(payload >> 26) & 0x3,
            birthday=(payload >> 15) & 0x7FF,
            turn=(payload >> 4) & 0x7FF,
            symmetry=(payload >> 2) & 0x3,
        )


SYMMETRY_UNKNOWN = 3

type Marker = MarkerTaskClaim | MarkerEureka | MarkerRole


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
            return MarkerRole.decode(payload)
        case _:
            return None


def is_stale(claim: MarkerTaskClaim, current_turn: int) -> bool:
    age = current_turn - claim.turn
    return age >= CLAIM_TTL or age < 0
