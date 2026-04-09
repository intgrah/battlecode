"""Marker value encoding for foundry_rush.

Markers are u32. We pack two map tile indices and a unitID:

    bits  0..11  → first_offset tile index   (12 bits, max 4095)
    bits 12..23  → foundry_offset tile index (12 bits, max 4095)
    bits 24..29  → unitID                    (6 bits, max 63)

Max map size is 50x50 = 2500 < 4096, so 12 bits per index is enough.
"""

from __future__ import annotations

_INDEX_BITS = 12
_INDEX_MASK = (1 << _INDEX_BITS) - 1
_UID_BITS = 6
_UID_MASK = (1 << _UID_BITS) - 1


def encode_offsets(first_idx: int, foundry_idx: int, unit_id: int) -> int:
    """Pack two tile indices and a unitID into a u32 marker value."""
    return (
        (first_idx & _INDEX_MASK)
        | ((foundry_idx & _INDEX_MASK) << _INDEX_BITS)
        | ((unit_id & _UID_MASK) << (2 * _INDEX_BITS))
    )


def decode_offsets(value: int) -> tuple[int, int, int]:
    """Unpack a marker value into ``(first_idx, foundry_idx, unit_id)``."""
    first_idx = value & _INDEX_MASK
    foundry_idx = (value >> _INDEX_BITS) & _INDEX_MASK
    unit_id = (value >> (2 * _INDEX_BITS)) & _UID_MASK
    return first_idx, foundry_idx, unit_id
