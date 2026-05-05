from __future__ import annotations

from typing import ClassVar, Final

from cambc import Team

from rust.base import RustStruct, enum_u8, i32, position, u32


class EntityBase(RustStruct):
    """
    EntityBase (24 B, align 4):

      +0   4  id        i32
      +4   8  position  Pos
      +12  4  hp        i32
      +16  4  max_hp    i32
      +20  1  team      Team
    """

    _ID_OFF: Final = 0
    _POSITION_OFF: Final = 4
    _HP_OFF: Final = 12
    _MAX_HP_OFF: Final = 16
    _TEAM_OFF: Final = 20

    id = u32(_ID_OFF)
    position = position(_POSITION_OFF)
    hp = i32(_HP_OFF)
    max_hp = i32(_MAX_HP_OFF)
    team = enum_u8(_TEAM_OFF, tuple(Team))


class Variant(RustStruct):
    """
    Common base for all 15 Entity variants.

    Each variant subclass sets `_BASE_OFF` — the bucket offset where the
    variant's `EntityBase` starts. Subclasses inherit `.base` from here
    and override `__repr__` to add their own fields.
    """

    _BASE_OFF: ClassVar[int]

    @property
    def base(self) -> EntityBase:
        return EntityBase(self._raw, self._addr + self._BASE_OFF)

    def _base_repr(self) -> str:
        b = self.base
        return f"id={b.id} pos={b.position} hp={b.hp}/{b.max_hp} team={b.team.name}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._base_repr()})"
