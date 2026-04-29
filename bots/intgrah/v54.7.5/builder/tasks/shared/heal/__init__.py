"""Heal tasks. Three flat leaves under one group:
  heal_buildings        — pick a damaged friendly building (deconflicted),
                          walk to it, heal in-range tiles before/after
                          the move.
  heal_adjacent_builder — heal a damaged friendly bot within action
                          range. No movement.
  heal_self             — heal own tile, with step-off when standing on
                          an enemy structure.

Order matters: buildings first (highest impact, walks toward target),
then adjacent bots (no movement), then self (last resort). The fight-
to-death gate (low-HP self on enemy tile) blocks both bot-heal leaves
but NOT the building-heal leaf, since walking toward a building leaves
the enemy tile.
"""

from builder.tasks._policy import TaskGroup
from builder.tasks.shared.heal.heal_adjacent_builder import heal_adjacent_builder
from builder.tasks.shared.heal.heal_buildings import heal_buildings
from builder.tasks.shared.heal.heal_self import heal_self

HEAL_GROUP = TaskGroup(
    name="heal",
    children=(heal_buildings, heal_adjacent_builder, heal_self),
)
