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
    DEFEND = auto()


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
class MarkerOpeningBook:
    map_index: int

    def encode(self) -> int:
        val = (2 << _TAG_SHIFT) | self.map_index
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerOpeningBook:
        return MarkerOpeningBook(map_index=payload & 0xFFFF)


@dataclass(frozen=True)
class MarkerRole:
    role: int
    birthday: int
    turn: int

    def encode(self) -> int:
        val = (3 << _TAG_SHIFT) | (self.role << 22) | (self.birthday << 11) | (self.turn & 0x7FF)
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerRole:
        return MarkerRole(
            role=(payload >> 22) & 0x3,
            birthday=(payload >> 11) & 0x7FF,
            turn=payload & 0x7FF,
        )


CHAIN_PLAN_TTL = 30


@dataclass(frozen=True)
class MarkerChainPlan:
    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (4 << _TAG_SHIFT) | (self.tile_index << 11) | (self.turn & 0x7FF)
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerChainPlan:
        return MarkerChainPlan(
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


EXPLORE_CLAIM_TTL = 20


@dataclass(frozen=True)
class MarkerExploreClaim:
    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (5 << _TAG_SHIFT) | (self.tile_index << 11) | (self.turn & 0x7FF)
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerExploreClaim:
        return MarkerExploreClaim(
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


type Marker = MarkerTaskClaim | MarkerEureka | MarkerOpeningBook | MarkerRole | MarkerChainPlan | MarkerExploreClaim


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
            return MarkerOpeningBook.decode(payload)
        case 3:
            return MarkerRole.decode(payload)
        case 4:
            return MarkerChainPlan.decode(payload)
        case 5:
            return MarkerExploreClaim.decode(payload)
        case _:
            return None


def is_stale(claim: MarkerTaskClaim, current_turn: int) -> bool:
    age = current_turn - claim.turn
    return age >= CLAIM_TTL or age < 0
