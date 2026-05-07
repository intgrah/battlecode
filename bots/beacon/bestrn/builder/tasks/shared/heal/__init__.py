"""
Translation of `bots/intgrah/v54.7.9/builder/tasks/shared/heal/`.

Heal tasks. Three flat leaves under one group:
  `heal_buildings`        — pick a damaged friendly building (deconflicted),
                          walk to it, heal in-range tiles before/after
                          the move.
  `heal_adjacent_builder` — heal a damaged friendly bot within action
                          range. No movement.
  `heal_self`             — heal own tile, with step-off when standing on
                          an enemy structure.
"""

from __future__ import annotations

from typing import Final

from builder.tasks._policy import Policy, PolicyGroup, PolicyLeaf, TaskGroup

from . import heal_adjacent_builder, heal_buildings, heal_self

HEAL_CHILDREN: Final[list[Policy]] = [
    PolicyLeaf(name="heal_buildings", fn_=heal_buildings.heal_buildings),
    PolicyLeaf(
        name="heal_adjacent_builder", fn_=heal_adjacent_builder.heal_adjacent_builder
    ),
    PolicyLeaf(name="heal_self", fn_=heal_self.heal_self),
]
HEAL_GROUP_INNER: TaskGroup = TaskGroup(name="heal", children=HEAL_CHILDREN, gate=None)
HEAL_GROUP: Policy = PolicyGroup(_0=HEAL_GROUP_INNER)
