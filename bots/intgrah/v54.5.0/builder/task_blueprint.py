"""Execute the per-map blueprint.

Each turn, scan the blueprint for the first entry that:
  * isn't already built correctly (build target), OR
  * is built but damaged (repair target).

Pick the closest actionable target, walk to it if we're not adjacent,
otherwise build/repair.

Returns False when there's nothing blueprint-related to do — the normal
task policy then runs as usual.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blueprint import BlueprintEntry, Entity
from building import (
    BuildingArmouredConveyor,
    BuildingBarrier,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingFoundry,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Controller, Direction, EntityType, Position
from util import chebyshev

from builder.helpers import make_move, move_random

if TYPE_CHECKING:
    from building import Building

    from builder import Builder


__all__ = ["run_blueprint"]


_ENTITY_TO_CT: dict[Entity, EntityType] = {
    Entity.CONVEYOR: EntityType.CONVEYOR,
    Entity.SPLITTER: EntityType.SPLITTER,
    Entity.ARMOURED_CONVEYOR: EntityType.ARMOURED_CONVEYOR,
    Entity.BRIDGE: EntityType.BRIDGE,
    Entity.HARVESTER: EntityType.HARVESTER,
    Entity.FOUNDRY: EntityType.FOUNDRY,
    Entity.GUNNER: EntityType.GUNNER,
    Entity.SENTINEL: EntityType.SENTINEL,
    Entity.BREACH: EntityType.BREACH,
    Entity.LAUNCHER: EntityType.LAUNCHER,
    Entity.BARRIER: EntityType.BARRIER,
    Entity.ROAD: EntityType.ROAD,
}


def _matches(bld: Building | None, entry: BlueprintEntry, team: object) -> bool:
    """Whether an actually-placed building matches the blueprint entry."""
    if bld is None or bld.team != team:
        return False
    match entry.kind:
        case Entity.CONVEYOR:
            return (
                isinstance(bld, BuildingConveyor)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.ARMOURED_CONVEYOR:
            return (
                isinstance(bld, BuildingArmouredConveyor)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.SPLITTER:
            return (
                isinstance(bld, BuildingSplitter)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.BRIDGE:
            return (
                isinstance(bld, BuildingBridge)
                and bld.target.x == entry.bridge_target[0]  # type: ignore[index]
                and bld.target.y == entry.bridge_target[1]  # type: ignore[index]
            )
        case Entity.HARVESTER:
            return isinstance(bld, BuildingHarvester)
        case Entity.FOUNDRY:
            return isinstance(bld, BuildingFoundry)
        case Entity.GUNNER:
            return (
                isinstance(bld, BuildingGunner)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.SENTINEL:
            return (
                isinstance(bld, BuildingSentinel)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.BREACH:
            return (
                isinstance(bld, BuildingBreach)
                and bld.direction.name == entry.direction.name  # type: ignore[union-attr]
            )
        case Entity.LAUNCHER:
            return isinstance(bld, BuildingLauncher)
        case Entity.BARRIER:
            return isinstance(bld, BuildingBarrier)
        case Entity.ROAD:
            return isinstance(bld, BuildingRoad)
    return False


def _pick_target(
    self: Builder,
    ct: Controller,
) -> tuple[BlueprintEntry, str] | None:
    """Closest actionable blueprint target. Return (entry, 'build'|'heal')."""
    best: tuple[int, BlueprintEntry, str] | None = None
    for entry in self.blueprint:
        pos = Position(*entry.pos)
        i = self.idx(pos)
        in_vision = ct.is_in_vision(pos)
        bld = self.buildings[i]
        matches = _matches(bld, entry, self.my_team)
        if in_vision and matches:
            if self.hp[i] < self.max_hp[i] - 3:
                d = chebyshev(self.my_pos, pos)
                if best is None or d < best[0]:
                    best = (d, entry, "heal")
            continue
        d = chebyshev(self.my_pos, pos)
        if best is None or d < best[0] or (d == best[0] and best[2] == "heal"):
            best = (d, entry, "build")
    if best is None:
        return None
    return (best[1], best[2])


def _place_entry(self: Builder, ct: Controller, entry: BlueprintEntry) -> bool:
    """Place the blueprint entry. Clears any friendly non-matching building
    (e.g. a road laid during movement) before building."""
    pos = Position(*entry.pos)
    etype = _ENTITY_TO_CT[entry.kind]
    extra: Direction | Position | None = None
    if entry.direction is not None:
        extra = Direction[entry.direction.name]
    elif entry.bridge_target is not None:
        extra = Position(*entry.bridge_target)
    bld = self.buildings[self.idx(pos)]
    if bld is not None and _matches(bld, entry, self.my_team):
        return False
    if ct.can_destroy(pos):
        ct.destroy(pos)
    if ct.can_build(etype, pos, extra):
        ct.build(etype, pos, extra)
        return True
    return False


def _try_heal(self: Builder, ct: Controller, pos: Position) -> bool:
    if ct.can_heal(pos):
        ct.heal(pos)
        return True
    return False


def blueprint_progress(self: Builder, ct: Controller) -> tuple[int, int]:
    """Return (done, total) count of blueprint entries. An entry is done
    iff the actual building at that tile matches the blueprint kind and
    direction/target.
    """
    done = 0
    for entry in self.blueprint:
        pos = Position(*entry.pos)
        if not ct.is_in_vision(pos):
            continue
        bld = self.buildings[self.idx(pos)]
        if _matches(bld, entry, self.my_team):
            done += 1
    return done, len(self.blueprint)


def run_blueprint(self: Builder, ct: Controller) -> bool:
    if not self.blueprint:
        return False
    target = _pick_target(self, ct)
    if target is None:
        return False
    entry, action = target
    pos = Position(*entry.pos)

    if action == "heal":
        if chebyshev(self.my_pos, pos) <= 1:
            _try_heal(self, ct, pos)
            return True
        make_move(self, ct, pos)
        self.my_pos = ct.get_position()
        if chebyshev(self.my_pos, pos) <= 1:
            _try_heal(self, ct, pos)
        return True

    # build action
    if self.my_pos == pos:
        move_random(self, ct)
        self.my_pos = ct.get_position()
        if self.my_pos != pos and chebyshev(self.my_pos, pos) <= 1:
            _place_entry(self, ct, entry)
        return True
    if chebyshev(self.my_pos, pos) <= 1:
        _place_entry(self, ct, entry)
        return True
    make_move(self, ct, pos)
    self.my_pos = ct.get_position()
    if self.my_pos != pos and chebyshev(self.my_pos, pos) <= 1:
        _place_entry(self, ct, entry)
    return True
