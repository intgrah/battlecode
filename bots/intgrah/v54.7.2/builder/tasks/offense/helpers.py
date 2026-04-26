"""Shared helpers for the offense task family. Hosts target-selection
predicates (`vulnerable_harvesters`, `pick_harvester_target`,
`pick_attack_destination`, `pick_conveyor_target`), gating predicates
(`should_attack`, `enemy_healer_near`, etc.), turret-facing math
(`gunner_chain_facing`), the `scout_toward_enemy` movement helper, and
`begin_turn_offense` — the once-per-turn state-decay prelude that runs
before any offense task fires (decays `attack_tile_blacklist`, clears
stale `last_fire`, decays `offense_target` / `offense_launcher` /
`offense_turns` and increments `offense_turns` when the target survives).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingHarvester,
    BuildingSplitter,
)
from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)
from util.directions import DIR4, DIR8
from util.metrics import chebyshev, closest

from builder.explore import explore
from builder.helpers import (
    can_afford,
    get_enemy_core_pos,
    make_move,
    try_move_dir,
)

if TYPE_CHECKING:
    from builder import Builder


def open_tiles(
    self: Builder,
    positions: list[Position],
) -> list[Position]:
    return [p for p in positions if self.is_passable(p) and p not in self.all_bots]


def is_allied_transport(self: Builder, position: Position) -> bool:
    match self.get_building(position):
        case (
            BuildingConveyor(team=self.my_team)
            | BuildingArmouredConveyor(team=self.my_team)
            | BuildingSplitter(team=self.my_team)
            | BuildingBridge(team=self.my_team)
        ):
            return True
        case _:
            return False


def without_allied_transport(
    self: Builder,
    positions: list[Position],
) -> list[Position]:
    return [pos for pos in positions if not is_allied_transport(self, pos)]


def buildable(self: Builder, positions: list[Position]) -> list[Position]:
    return [
        p for p in positions if self.is_buildable(p) and not self.is_friendly_turret(p)
    ]


def nearest_enemy_bot(self: Builder) -> Position | None:
    if not self.enemy_bots:
        return None
    return closest(self.my_pos, self.enemy_bots)


def should_attack(self: Builder, pos: Position) -> bool:
    enemy_builder = nearest_enemy_bot(self)
    i = self.idx(pos)
    return (
        (enemy_builder is None)
        or chebyshev(self.my_pos, enemy_builder) > 2
        or self.hp[i] <= self.max_hp[i] - 4
        or self.hp[i] <= 4
        or can_afford(self, EntityType.HARVESTER)
    )


def enemy_healer_near(self: Builder, pos: Position) -> bool:
    return any(p.distance_squared(pos) <= 2 for p in self.enemy_bots)


def friendly_bot_adjacent(self: Builder, pos: Position) -> bool:
    return any(p.distance_squared(pos) <= 1 for p in self.friendly_bots)


def min_friendly_chebyshev(ct: Controller, pos: Position) -> int:
    """Chebyshev distance from `pos` to the nearest OTHER friendly
    builder bot. Used to score attack spacing: an enemy healer
    (heal radius r²≤2 ≈ 1 king-move) can cover at most one of us
    when we're ≥3 chebyshev apart, so we prefer targets that are
    well away from our other attackers.
    """
    my_team = ct.get_team()
    my_id = ct.get_id()
    best = 999
    for uid in ct.get_nearby_units():
        if uid == my_id:
            continue
        if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
            continue
        if ct.get_team(uid) != my_team:
            continue
        d = chebyshev(pos, ct.get_position(uid))
        best = min(best, d)
    return best


def pick_conveyor_target(
    self: Builder,
    ct: Controller,
    enemy_core: Position,
    my_pos: Position,
) -> Position | None:
    """Pick an enemy conveyor/bridge/splitter tile to attack, falling
    back when no harvester is vulnerable. Preference in order:
      1. near enemy core (r²≤25)
      2. conveyor currently carrying a Ti stack (visible flow)
    Spacing: prefer tiles far from our other attackers (cap at
    chebyshev 3 — past that point spacing gains are moot since one
    enemy healer already can't reach two of us).
    """
    best: Position | None = None
    best_score: tuple[int, int, int] | None = None
    for pos in self.nearby_buildings:
        b = self.get_building(pos)
        if b is None or b.team == self.my_team:
            continue
        if not isinstance(
            b,
            (
                BuildingConveyor,
                BuildingArmouredConveyor,
                BuildingSplitter,
                BuildingBridge,
            ),
        ):
            continue
        if not self.is_passable(pos):
            continue
        if pos in self.attack_tile_blacklist:
            continue
        if pos in self.friendly_turret_ray_tiles:
            continue
        if pos in self.all_bots and self.all_bots[pos] != self.my_id:
            continue
        if enemy_healer_near(self, pos):
            continue
        near_core = pos.distance_squared(enemy_core) <= 25
        has_flow = False
        if ct.is_in_vision(pos):
            bid = ct.get_tile_building_id(pos)
            if bid is not None and ct.get_stored_resource(bid) is not None:
                has_flow = True
        if near_core:
            tier = 0
        elif has_flow:
            tier = 1
        else:
            continue
        spacing = min_friendly_chebyshev(ct, pos)
        my_dist = my_pos.distance_squared(pos)
        score = (tier, -min(spacing, 3), my_dist)
        if best_score is None or score < best_score:
            best = pos
            best_score = score
    return best


def pick_attack_destination(
    self: Builder,
    target: Position,
    *,
    avoid_healers: bool = True,
) -> Position | None:
    """Pick a cardinal neighbour of `target` (an enemy harvester) for
    us to stand on and attack. Sort by:
      1. no enemy healer in range — lone attackers lose to healers
      2. lowest HP to destroy (road 5 < conveyor/splitter/bridge 20)
      3. closest to our current position.

    When `avoid_healers=True` (default), destinations inside an enemy
    healer's r²≤2 are filtered out entirely — the caller can then try
    a different target harvester. When False, we fall back to any
    walkable candidate (useful when nothing else is viable).
    """
    candidates: list[tuple[int, int, int, Position]] = []
    for d in DIR4:
        pos = target.add(d)
        if not self.in_bounds(pos):
            continue
        if not self.is_passable(pos):
            continue
        if is_allied_transport(self, pos):
            continue
        if pos in self.all_bots and self.all_bots[pos] != self.my_id:
            continue
        if pos in self.attack_tile_blacklist:
            continue
        # Standing here would block our own gunner/sentinel shot —
        # the engine treats friendly bots as LoS obstacles. Don't
        # attack from inside one of our turrets' kill lanes.
        if pos in self.friendly_turret_ray_tiles:
            continue
        b = self.get_building(pos)
        if b is None:
            # Empty terrain — a bot can walk here (building a road
            # on the way) and then place sentinels from it.
            cost = 0
        elif b.team == self.my_team:
            # Friendly road / allied core — fine to stand on. Friendly
            # conveyors/splitters/bridges were already filtered above
            # via `is_allied_transport`, so anything reaching here is
            # safe to land on without breaking our own chain.
            cost = 0
        elif isinstance(b, BuildingConveyor | BuildingSplitter | BuildingBridge):
            cost = 20  # enemy transport — can destroy by firing
        else:
            cost = 5  # enemy road, 5 HP
        if avoid_healers and enemy_healer_near(self, pos):
            continue
        # Soft-deprioritise tiles that sit in an enemy gunner/sentinel
        # firing ray. We don't filter them out — sometimes the only
        # way to hit the harvester is to cross a ray — but we'd rather
        # stand somewhere safer if equivalent on cost and distance.
        in_ray = 1 if pos in self.enemy_turret_ray_tiles else 0
        dist = self.my_pos.distance_squared(pos)
        candidates.append((in_ray, cost, dist, pos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def gunner_chain_facing(self: Builder, pos: Position) -> Direction | None:
    """Return a direction (any of DIR8) such that a gunner placed at
    `pos` facing that way has an enemy conveyor/splitter/bridge as
    the first building in its forward ray. Used to position gunners
    next to enemy harvesters so they eat the harvester's output
    chain tile-by-tile.
    """
    for d in DIR8:
        current = pos
        for _ in range(4):
            current = current.add(d)
            if not self.in_bounds(current):
                break
            if pos.distance_squared(current) > GameConstants.GUNNER_VISION_RADIUS_SQ:
                break
            if self.get_env(current) == Environment.WALL:
                break
            b = self.get_building(current)
            if b is None:
                continue
            if b.team == self.my_team:
                break
            if isinstance(
                b,
                (
                    BuildingConveyor,
                    BuildingArmouredConveyor,
                    BuildingSplitter,
                    BuildingBridge,
                ),
            ):
                return d
            break
    return None


def vulnerable_harvesters(self: Builder) -> list[Position]:
    """Enemy harvesters with at least one passable, unoccupied,
    non-allied-transport cardinal. An encircled harvester isn't a
    useful target.
    """

    def has_open_side(position: Position) -> bool:
        for direction in DIR4:
            new_position = position.add(direction)
            if not self.in_bounds(new_position):
                continue
            occupied = (
                new_position in self.all_bots
                and self.all_bots[new_position] != self.my_id
            )
            if (
                self.is_passable(position.add(direction))
                and not occupied
                and not is_allied_transport(self, position.add(direction))
            ):
                return True
        return False

    result: list[Position] = []
    for p in self.nearby_buildings:
        b = self.get_building(p)
        if b is None or b.team == self.my_team:
            continue
        if not isinstance(b, BuildingHarvester):
            continue
        if has_open_side(p):
            result.append(p)
    return result


def pick_harvester_target(
    self: Builder,
    vulnerable: list[Position],
) -> Position:
    """3-tier preference over vulnerable harvesters:
    1. no enemy healer in range AND no friendly bot already attacking
       it — spreads us across lightly-contested targets.
    2. no enemy healer in range (dogpiles if forced, but avoids healers).
    3. closest of all (last resort).
    """
    sorted_harvesters = sorted(vulnerable, key=self.my_pos.distance_squared)
    for h in sorted_harvesters:
        if not enemy_healer_near(self, h) and not friendly_bot_adjacent(self, h):
            return h
    for h in sorted_harvesters:
        if not enemy_healer_near(self, h):
            return h
    result = closest(self.my_pos, vulnerable)
    assert result is not None  # vulnerable is non-empty by caller contract
    return result


def scout_toward_enemy(self: Builder, ct: Controller) -> None:
    en_core = get_enemy_core_pos(self)

    if en_core in self.nearby_tiles:
        self.en_core_seen = True

    if not self.en_core_seen:
        make_move(self, ct, en_core)
    elif en_core in self.nearby_tiles or self.ti >= (
        GameConstants.HARVESTER_BASE_COST[0] + 50
    ) * (1 + self.scale):
        explore(self, ct)
    else:
        dir8 = DIR8.copy()
        self.rng.shuffle(dir8)
        for d in dir8:
            if try_move_dir(ct, d):
                break


def begin_turn_offense(self: Builder, ct: Controller) -> None:
    """Per-turn offense bookkeeping. Must run exactly once per turn,
    regardless of which offense sub-task ends up firing. Decays TTL
    counters on `attack_tile_blacklist`, clears stale `last_fire` when
    we've moved off the tile, and decays `offense_target` /
    `offense_launcher` / `offense_turns` when the cached target has
    expired or is visibly invalid. Also increments `offense_turns` on
    turns where the target survives the decay.
    """
    if self.attack_tile_blacklist:
        self.attack_tile_blacklist = {
            p: n - 1 for p, n in self.attack_tile_blacklist.items() if n > 1
        }
    # If we've moved off the tile we last fired at, drop the stale
    # expected-HP tracking — otherwise a future visit to the same
    # tile could misread its pre-heal HP as "healed by enemy".
    if self.last_fire is not None and self.my_pos != self.last_fire:
        self.last_fire = None

    if (self.offense_turns > 25) or (
        self.offense_target
        and ct.is_in_vision(self.offense_target)
        and (
            not self.is_enemy_building(self.offense_target)
            or (not self.is_passable(self.offense_target))
            or (
                self.offense_target in self.all_bots
                and self.all_bots[self.offense_target] != self.my_id
            )
        )
    ):
        self.offense_target = None
        self.offense_launcher = None
        self.offense_turns = 0
    else:
        self.offense_turns += 1
