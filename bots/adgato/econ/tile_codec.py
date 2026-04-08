"""Shared encoding for cached tile state.

Bit layout (per tile, one byte):
    bits 0-1 : Environment ordinal
    bits 2-5 : building ordinal + 1, or 0 if none
    bit  6   : allied building flag

A value of 0xFF indicates "unseen" (matches the initial cache fill).
"""

from __future__ import annotations

from cambc import EntityType, Environment

_ENV_INT: dict[Environment, int] = {e: i for i, e in enumerate(Environment)}
_ET_INT: dict[EntityType, int] = {e: i + 1 for i, e in enumerate(EntityType)}

UNSEEN = 0xFF

ENV_WALL = _ENV_INT[Environment.WALL]
ENV_TI_ORE = _ENV_INT[Environment.ORE_TITANIUM]
ENV_AX_ORE = _ENV_INT[Environment.ORE_AXIONITE]


def encode_tile(
    env: Environment, building_type: EntityType | None, is_allied: bool
) -> int:
    bt = _ET_INT[building_type] if building_type is not None else 0
    return _ENV_INT[env] | (bt << 2) | (int(is_allied) << 6)


def tile_env(byte: int) -> int:
    return byte & 0b11


def tile_has_building(byte: int) -> bool:
    return (byte >> 2) & 0b1111 != 0


_INT_ET: tuple[EntityType | None, ...] = (None, *EntityType)


def tile_building_type(byte: int) -> EntityType | None:
    return _INT_ET[(byte >> 2) & 0b1111]


def tile_is_allied(byte: int) -> bool:
    return bool((byte >> 6) & 1)
