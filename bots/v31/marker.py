from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from params import CIPHER

_TAG_SHIFT = 28
_TAG_MASK = 0xF


class ClaimState(IntEnum):
    CLAIMED = 0
    BUILDING = 1
    CONNECTED = 2
    ABANDONED = 3


class Urgency(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class OreClaim:
    ore_x: int
    ore_y: int
    state: ClaimState
    claimer_hash: int
    freshness: int
    ore_type: int

    def encode(self) -> int:
        val = (
            (0 << _TAG_SHIFT)
            | (self.ore_x << 22)
            | (self.ore_y << 16)
            | (self.state << 14)
            | (self.claimer_hash << 8)
            | (self.freshness << 2)
            | (self.ore_type << 1)
        )
        return val ^ CIPHER

    @staticmethod
    def decode(payload: int) -> OreClaim:
        return OreClaim(
            ore_x=(payload >> 22) & 0x3F,
            ore_y=(payload >> 16) & 0x3F,
            state=ClaimState((payload >> 14) & 0x3),
            claimer_hash=(payload >> 8) & 0x3F,
            freshness=(payload >> 2) & 0x3F,
            ore_type=(payload >> 1) & 0x1,
        )


@dataclass
class Threat:
    enemy_x: int
    enemy_y: int
    enemy_composition: int
    enemy_count: int
    freshness: int
    urgency: Urgency

    def encode(self) -> int:
        val = (
            (1 << _TAG_SHIFT)
            | (self.enemy_x << 22)
            | (self.enemy_y << 16)
            | (self.enemy_composition << 12)
            | (self.enemy_count << 8)
            | (self.freshness << 2)
            | self.urgency
        )
        return val ^ CIPHER

    @staticmethod
    def decode(payload: int) -> Threat:
        return Threat(
            enemy_x=(payload >> 22) & 0x3F,
            enemy_y=(payload >> 16) & 0x3F,
            enemy_composition=(payload >> 12) & 0xF,
            enemy_count=(payload >> 8) & 0xF,
            freshness=(payload >> 2) & 0x3F,
            urgency=Urgency(payload & 0x3),
        )


@dataclass
class PressureSummary:
    pos_x: int
    pos_y: int
    pressure_level: int
    upstream_harvesters: int
    freshness: int
    chain_direction: int

    def encode(self) -> int:
        val = (
            (2 << _TAG_SHIFT)
            | (self.pos_x << 22)
            | (self.pos_y << 16)
            | (self.pressure_level << 12)
            | (self.upstream_harvesters << 8)
            | (self.freshness << 2)
            | self.chain_direction
        )
        return val ^ CIPHER

    @staticmethod
    def decode(payload: int) -> PressureSummary:
        return PressureSummary(
            pos_x=(payload >> 22) & 0x3F,
            pos_y=(payload >> 16) & 0x3F,
            pressure_level=(payload >> 12) & 0xF,
            upstream_harvesters=(payload >> 8) & 0xF,
            freshness=(payload >> 2) & 0x3F,
            chain_direction=payload & 0x3,
        )


@dataclass
class BreakAlert:
    break_x: int
    break_y: int
    repair_direction: int
    chain_importance: int
    freshness: int
    break_type: int

    def encode(self) -> int:
        val = (
            (3 << _TAG_SHIFT)
            | (self.break_x << 22)
            | (self.break_y << 16)
            | (self.repair_direction << 13)
            | (self.chain_importance << 10)
            | (self.freshness << 4)
            | self.break_type
        )
        return val ^ CIPHER

    @staticmethod
    def decode(payload: int) -> BreakAlert:
        return BreakAlert(
            break_x=(payload >> 22) & 0x3F,
            break_y=(payload >> 16) & 0x3F,
            repair_direction=(payload >> 13) & 0x7,
            chain_importance=(payload >> 10) & 0x7,
            freshness=(payload >> 4) & 0x3F,
            break_type=payload & 0xF,
        )


Marker = OreClaim | Threat | PressureSummary | BreakAlert


def decode(encrypted: int) -> Marker:
    raw = encrypted ^ CIPHER
    tag = (raw >> _TAG_SHIFT) & _TAG_MASK
    payload = raw & 0x0FFFFFFF
    match tag:
        case 0:
            return OreClaim.decode(payload)
        case 1:
            return Threat.decode(payload)
        case 2:
            return PressureSummary.decode(payload)
        case 3:
            return BreakAlert.decode(payload)
        case _:
            raise AssertionError


def is_stale(freshness: int, current_round: int, ttl: int) -> bool:
    age = (current_round - freshness) & 0x3F
    return age > ttl
