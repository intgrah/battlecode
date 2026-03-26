"""Marker encoding/decoding protocol.

Markers are u32 values placed on tiles for inter-builder communication.
The raw value is encrypted with a Feistel cipher to prevent enemy bots
from reading our markers.

Marker types (4-bit tag):
  0 = TaskClaim — a builder claims a task (ore, excess, explore target)
  1 = Eureka    — broadcasts confirmed map symmetry
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, auto

from feistel_symmetric_encryption import decrypt, encrypt

CLAIM_TTL = 8

_TAG_SHIFT = 28
_TAG_MASK = 0xF


class TaskKind(IntEnum):
    NAV_ORE = auto()
    FIX_EXCESS = auto()
    EXPLORE = auto()


@dataclass(frozen=True)
class TaskClaim:
    kind: TaskKind
    tile_index: int
    turn: int

    def encode(self) -> int:
        val = (0 << _TAG_SHIFT) | (self.kind << 23) | (self.tile_index << 11) | self.turn
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> TaskClaim:
        return TaskClaim(
            kind=TaskKind((payload >> 23) & 0x1F),
            tile_index=(payload >> 11) & 0xFFF,
            turn=payload & 0x7FF,
        )


@dataclass(frozen=True)
class Eureka:
    symmetry: int

    def encode(self) -> int:
        val = (1 << _TAG_SHIFT) | self.symmetry
        return encrypt(val)

    @staticmethod
    def decode(payload: int) -> Eureka:
        return Eureka(symmetry=payload & 0x3)


Marker = TaskClaim | Eureka


def decode(encrypted: int) -> Marker | None:
    raw = decrypt(encrypted)
    tag = (raw >> _TAG_SHIFT) & _TAG_MASK
    payload = raw & 0x0FFFFFFF
    match tag:
        case 0:
            return TaskClaim.decode(payload)
        case 1:
            return Eureka.decode(payload)
        case _:
            return None


def is_stale(claim: TaskClaim, current_turn: int) -> bool:
    age = current_turn - claim.turn
    return age >= CLAIM_TTL or age < 0
