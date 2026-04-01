"""Marker encoding/decoding for inter-unit coordination.

Marker values are u32. The top 4 bits encode an opcode, the rest is
opcode-specific payload.
"""

from __future__ import annotations

OPCODE_CLAIM = 1


def encode_claim(round_no: int, owner_id: int, ore_x: int, ore_y: int) -> int:
    """Encode an ore claim marker.

    Layout (32 bits):
      [31:28] opcode (4 bits)
      [27:16] round_no (12 bits, mod 4096)
      [15:8]  owner_id (8 bits, low byte of entity id)
      [7:0]   unused / reserved
    """
    return (
        ((OPCODE_CLAIM & 0xF) << 28)
        | ((round_no & 0xFFF) << 16)
        | ((owner_id & 0xFF) << 8)
    )


def decode_claim(value: int) -> tuple[int, int, int]:
    """Decode a claim marker -> (opcode, round_no, owner_id)."""
    opcode = (value >> 28) & 0xF
    round_no = (value >> 16) & 0xFFF
    owner_id = (value >> 8) & 0xFF
    return opcode, round_no, owner_id


OPCODE_SECTOR = 2
OPCODE_HEALER = 3

HEALER_MARKER_VALUE = (OPCODE_HEALER & 0xF) << 28


def encode_sector(round_no: int, owner_id: int, sector: int) -> int:
    """Encode a sector claim marker.

    Layout (32 bits):
      [31:28] opcode    (4 bits)
      [27:17] round_no  (11 bits, 0-2047)
      [16:2]  owner_id  (15 bits, 0-32767)
      [1:0]   sector    (2 bits, 0-3)
    """
    return (
        ((OPCODE_SECTOR & 0xF) << 28)
        | ((round_no & 0x7FF) << 17)
        | ((owner_id & 0x7FFF) << 2)
        | (sector & 0x3)
    )


def decode_sector(value: int) -> tuple[int, int, int, int]:
    """Decode -> (opcode, round_no, owner_id, sector)."""
    opcode = (value >> 28) & 0xF
    round_no = (value >> 17) & 0x7FF
    owner_id = (value >> 2) & 0x7FFF
    sector = value & 0x3
    return opcode, round_no, owner_id, sector


