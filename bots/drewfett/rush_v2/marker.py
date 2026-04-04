"""Marker encode/decode for inter-unit communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

_TAG_SHIFT = 28
_TAG_MASK = 0xF

# -- XOR encryption (same key as v50/rush) --
_KEY: Final[int] = 0xA5B3_C7D1


def _encrypt(val: int) -> int:
    return val ^ _KEY


def _decrypt(val: int) -> int:
    return val ^ _KEY


# -- Staleness --
CLAIM_TTL: Final[int] = 8
CHAIN_PLAN_TTL: Final[int] = 30


def is_stale(turn: int, current_turn: int) -> bool:
    age = current_turn - turn
    return age >= CLAIM_TTL or age < 0


def is_stale_chain(turn: int, current_turn: int) -> bool:
    age = current_turn - turn
    return age >= CHAIN_PLAN_TTL or age < 0


# -- Marker types --


class ClaimKind:
    NAV_ORE = 0
    FIX_EXCESS = 1
    SIEGE = 2


@dataclass(frozen=True, slots=True)
class MarkerClaim:
    """Task claim on a tile. TTL=8."""

    kind: int
    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (
            (0 << _TAG_SHIFT)
            | (self.kind << 23)
            | (self.tile_index << 11)
            | (self.turn & 0x7FF)
        )
        return _encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerClaim:
        return MarkerClaim(
            kind=(payload >> 23) & 0x1F,
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


@dataclass(frozen=True, slots=True)
class MarkerEureka:
    """Symmetry discovery broadcast."""

    symmetry: int

    def encode(self) -> int:
        val = (1 << _TAG_SHIFT) | self.symmetry
        return _encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerEureka:
        return MarkerEureka(symmetry=payload & 0x3)


@dataclass(frozen=True, slots=True)
class MarkerRole:
    """Role assignment from core to builder."""

    role: int  # 2 bits
    birthday: int  # 11 bits
    turn: int  # 11 bits

    def encode(self) -> int:
        val = (
            (2 << _TAG_SHIFT)
            | (self.role << 22)
            | (self.birthday << 11)
            | (self.turn & 0x7FF)
        )
        return _encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerRole:
        return MarkerRole(
            role=(payload >> 22) & 0x3,
            birthday=(payload >> 11) & 0x7FF,
            turn=payload & 0x7FF,
        )


@dataclass(frozen=True, slots=True)
class MarkerChainPlan:
    """Siege chain claim. TTL=30."""

    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (3 << _TAG_SHIFT) | (self.tile_index << 11) | (self.turn & 0x7FF)
        return _encrypt(val)

    @staticmethod
    def decode(payload: int) -> MarkerChainPlan:
        return MarkerChainPlan(
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


type Marker = MarkerClaim | MarkerEureka | MarkerRole | MarkerChainPlan


def decode(encrypted: int) -> Marker | None:
    raw = _decrypt(encrypted)
    tag = (raw >> _TAG_SHIFT) & _TAG_MASK
    payload = raw & 0x0FFF_FFFF
    match tag:
        case 0:
            return MarkerClaim.decode(payload)
        case 1:
            return MarkerEureka.decode(payload)
        case 2:
            return MarkerRole.decode(payload)
        case 3:
            return MarkerChainPlan.decode(payload)
        case _:
            return None
