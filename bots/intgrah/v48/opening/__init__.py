"""Opening book — scripted openers for known maps.

The DSL:
  CoreScript: list of spawn positions (relative to core centre), one per turn.
    None = don't spawn this turn.
  BuilderScript: list of actions per turn after spawn.
    Each action is one of:
      Move(direction)
      Build(action)  — any Action from build.py
      Wait()         — do nothing this turn

A builder follows its script until:
  - The script runs out of steps
  - An action fails (can't move, can't build)
Then it enters the normal policy.

Usage:
  book = get_opening(known_map_key)
  if book is not None:
      core_script, builder_scripts = book
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builder.build import Action
    from cambc import Direction
    from hardcode.known import KnownMap


@dataclass(frozen=True, slots=True)
class Move:
    direction: Direction


@dataclass(frozen=True, slots=True)
class Build:
    action: Action


@dataclass(frozen=True, slots=True)
class Wait:
    pass


type Step = Move | Build | Wait


@dataclass(frozen=True, slots=True)
class Opening:
    core_spawns: list[tuple[int, int] | None]
    builder_scripts: list[list[Step]]


_OPENINGS: dict[KnownMap, Opening] = {}


def get_opening(key: KnownMap) -> Opening | None:
    return _OPENINGS.get(key)


def register(key: KnownMap, opening: Opening) -> None:
    _OPENINGS[key] = opening
