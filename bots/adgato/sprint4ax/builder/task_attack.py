from __future__ import annotations

from typing import TYPE_CHECKING

from building import (
    BuildingArmouredConveyor,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingLauncher,
    BuildingSentinel,
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
from util import (
    DIR4,
    DIR8,
    chebyshev,
    closest,
    try_move,
)

from .helpers import (
    get_enemy_core_pos,
    make_move,
    make_multi_move,
    move_random,
    try_attack,
    try_place,
)
from .task_explore import explore

if TYPE_CHECKING:
    from builder import Builder


def open_tiles(
    self: Builder, ct: Controller, positions: list[Position]
) -> list[Position]:
    return [
        p
        for p in positions
        if self.is_passable(p)
        and p not in self.friendly_turret_ray_tiles
        and (not ct.is_in_vision(p) or ct.get_tile_builder_bot_id(p) is None)
    ]


def is_allied_transport(self: Builder, ct: Controller, position: Position) -> bool:
    match self.get_building(position):
        case (
            BuildingConveyor(team=t)
            | BuildingArmouredConveyor(team=t)
            | BuildingSplitter(team=t)
            | BuildingBridge(team=t)
        ) if t == self.my_team:
            return True
        case _:
            return False


def without_allied_transport(
    self: Builder, ct: Controller, positions: list[Position]
) -> list[Position]:
    return [pos for pos in positions if not is_allied_transport(self, ct, pos)]


def buildable(self: Builder, positions: list[Position]) -> list[Position]:
    return [
        p
        for p in positions
        if self.is_buildable(p) and not self.is_friendly_turret(p)
    ]


def _enemy_healer_near(ct: Controller, pos: Position) -> bool:
    """True if any enemy builder bot sits within r²≤2 of `pos` — they
    can heal it for 4 HP/turn which outpaces our 2 dmg/turn fire.
    Lone attackers in this range are wasting Ti.

    The bounds guards are load-bearing: the real cambc engine raises
    `Position out of bounds` on `ct.get_tile_builder_bot_id(n)` when
    `n` is off-map, even if `ct.is_in_vision(n)` didn't reject it
    first. cambcpypy happens to return False for OOB from
    is_in_vision, which is why the hetzner sweeps passed but the
    official-server test crashed on maps where an enemy harvester
    sits at the edge.
    """
    my_team = ct.get_team()
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR8:
        n = pos.add(d)
        if not (0 <= n.x < w and 0 <= n.y < h):
            continue
        if ct.is_in_vision(n):
            uid = ct.get_tile_builder_bot_id(n)
            if uid is not None and ct.get_team(uid) != my_team:
                return True
    if 0 <= pos.x < w and 0 <= pos.y < h and ct.is_in_vision(pos):
        uid = ct.get_tile_builder_bot_id(pos)
        if uid is not None and ct.get_team(uid) != my_team:
            return True
    return False


def _friendly_bot_adjacent(ct: Controller, pos: Position) -> bool:
    """True if any friendly builder bot (other than us) sits on a
    cardinal neighbour of `pos`. Used to skip harvesters already
    being attacked by another bot — spreads us across targets
    instead of dogpiling. Vision-only: if we can't see the tile
    we assume nobody is there.
    """
    my_team = ct.get_team()
    my_id = ct.get_id()
    w = ct.get_map_width()
    h = ct.get_map_height()
    for d in DIR4:
        n = pos.add(d)
        if not (0 <= n.x < w and 0 <= n.y < h):
            continue
        if not ct.is_in_vision(n):
            continue
        uid = ct.get_tile_builder_bot_id(n)
        if uid is not None and uid != my_id and ct.get_team(uid) == my_team:
            return True
    return False


def _min_friendly_chebyshev(ct: Controller, pos: Position) -> int:
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


def _pick_conveyor_target(
    self: Builder, ct: Controller, enemy_core: Position, my_pos: Position
) -> Position | None:
    """Pick an enemy conveyor/bridge/splitter tile to attack, falling
    back when no harvester is vulnerable. Preference in order:
      1. near enemy core (r²≤25)
      2. conveyor currently carrying a resource stack (visible flow)
    Spacing: prefer tiles far from our other attackers (cap at
    chebyshev 3 — past that point spacing gains are moot since one
    enemy healer already can't reach two of us).
    """
    my_team = self.my_team
    best: Position | None = None
    best_score: tuple[int, int, int] | None = None
    for pos in self.nearby_buildings:
        b = self.get_building(pos)
        if b is None or getattr(b, "team", None) == my_team:
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
        if ct.is_in_vision(pos):
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None and uid != self.my_id:
                continue
        if _enemy_healer_near(ct, pos):
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
        spacing = _min_friendly_chebyshev(ct, pos)
        my_dist = my_pos.distance_squared(pos)
        score = (tier, -min(spacing, 3), my_dist)
        if best_score is None or score < best_score:
            best = pos
            best_score = score
    return best


def _pick_attack_destination(
    self: Builder, ct: Controller, target: Position, *, avoid_healers: bool = True
) -> Position | None:
    """Pick a cardinal neighbour of `target` (an enemy harvester) for
    us to stand on and attack. Sort by:
      1. no enemy healer in range — lone attackers lose to healers
      2. lowest HP to destroy (road 5 < conveyor/splitter/bridge 20)
      3. closest to our current position

    When `avoid_healers=True` (default), destinations inside an enemy
    healer's r²≤2 are filtered out entirely — the caller can then try
    a different target harvester. When False, we fall back to any
    walkable candidate (useful when nothing else is viable).
    """
    my_pos = self.my_pos
    my_team = self.my_team
    candidates: list[tuple[int, int, int, Position]] = []
    for d in DIR4:
        pos = target.add(d)
        if not self.in_bounds(pos):
            continue
        if not self.is_passable(pos):
            continue
        if is_allied_transport(self, ct, pos):
            continue
        if ct.is_in_vision(pos):
            uid = ct.get_tile_builder_bot_id(pos)
            if uid is not None and uid != self.my_id:
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
        elif getattr(b, "team", None) == my_team:
            # Friendly road / allied core — fine to stand on. Friendly
            # conveyors/splitters/bridges were already filtered above
            # via `is_allied_transport`, so anything reaching here is
            # safe to land on without breaking our own chain.
            cost = 0
        elif isinstance(b, (BuildingConveyor, BuildingSplitter, BuildingBridge)):
            cost = 20  # enemy transport — can destroy by firing
        else:
            cost = 5  # enemy road, 5 HP
        if avoid_healers and _enemy_healer_near(ct, pos):
            continue
        # Soft-deprioritise tiles that sit in an enemy gunner/sentinel
        # firing ray. We don't filter them out — sometimes the only
        # way to hit the harvester is to cross a ray — but we'd rather
        # stand somewhere safer if equivalent on cost and distance.
        in_ray = 1 if pos in self.enemy_turret_ray_tiles else 0
        dist = my_pos.distance_squared(pos)
        candidates.append((in_ray, cost, dist, pos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _gunner_chain_facing(
    self: Builder, ct: Controller, pos: Position
) -> Direction | None:
    """Return a direction (any of DIR8) such that a gunner placed at
    `pos` facing that way has an enemy conveyor/splitter/bridge as
    the first building in its forward ray. Used to position gunners
    next to enemy harvesters so they eat the harvester's output
    chain tile-by-tile.

    Ray semantics: walk the direction out to r²=13, stop at the
    first wall or building. Only success case is "first building is
    enemy transport"; friendly buildings or non-transport enemies
    (including the harvester itself) block the shot and disqualify
    this direction — so the "don't face into the harvester" constraint
    is enforced implicitly by the isinstance check.
    """
    team = self.my_team
    r_sq = GameConstants.GUNNER_VISION_RADIUS_SQ
    for d in DIR8:
        current = pos
        for _ in range(4):
            current = current.add(d)
            if not self.in_bounds(current):
                break
            if pos.distance_squared(current) > r_sq:
                break
            if self.get_env(current) == Environment.WALL:
                break
            b = self.get_building(current)
            if b is None:
                continue
            if getattr(b, "team", None) == team:
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


def run_attack(self: Builder, ct: Controller) -> None:
    team = self.my_team
    if self.attack_tile_blacklist:
        self.attack_tile_blacklist = {
            p: n - 1 for p, n in self.attack_tile_blacklist.items() if n > 1
        }
    enemy_buildings = [
        p
        for p in self.nearby_buildings
        if (b := self.get_building(p)) is not None and b.team != team
    ]
    enemy_harvesters = [
        p
        for p in enemy_buildings
        if isinstance(self.get_building(p), BuildingHarvester)
    ]

    def has_open_side(position: Position) -> bool:
        for direction in DIR4:
            new_position = position.add(direction)
            occupant = 1
            if not self.in_bounds(new_position):
                continue
            if ct.is_in_vision(new_position):
                occupant = ct.get_tile_builder_bot_id(new_position)
            occupied = occupant is not None and occupant != self.my_id
            if (
                self.is_passable(position.add(direction))
                and not occupied
                and not is_allied_transport(self, ct, position.add(direction))
            ):
                return True
        return False

    vulnerable_harvesters = [p for p in enemy_harvesters if has_open_side(p)]
    enemy_core = get_enemy_core_pos(self)

    # If we've moved off the tile we last fired at, drop the stale
    # expected-HP tracking — otherwise a future visit to the same
    # tile could misread its pre-heal HP as "healed by enemy".
    if self.last_fire_pos is not None and self.my_pos != self.last_fire_pos:
        self.last_fire_pos = None

    if (self.offense_turns > 25) or (
        self.offense_target
        and ct.is_in_vision(self.offense_target)
        and (
            not self.is_enemy_building(self.offense_target)
            or (not self.is_passable(self.offense_target))
            or (
                ct.get_tile_builder_bot_id(self.offense_target) is not None
                and ct.get_tile_builder_bot_id(self.offense_target) != self.my_id
            )
        )
    ):
        self.offense_target = None
        self.offense_launcher = None
        self.offense_turns = 0
    else:
        self.offense_turns += 1

    if vulnerable_harvesters:
        # Target preference, in order:
        #   1. closest harvester with no enemy healer in range AND
        #      no friendly bot already attacking it — spreads us
        #      across lightly-contested targets.
        #   2. closest with no enemy healer in range (dogpiles if we
        #      have to, but avoids healers).
        #   3. closest of all (last resort).
        my_pos = self.my_pos
        dist_to_me = my_pos.distance_squared

        targets = [
            h
            for h in vulnerable_harvesters
            if not _enemy_healer_near(ct, h) and not _friendly_bot_adjacent(ct, h)
        ]
        if not targets:
            targets = [
                h for h in vulnerable_harvesters if not _enemy_healer_near(ct, h)
            ]
        if not targets:
            targets = vulnerable_harvesters

        adj_harvesters = [h for h in targets if dist_to_me(h) == 1]

        on_friendly_conveyor = is_allied_transport(self, ct, my_pos)
        if adj_harvesters and not on_friendly_conveyor:
            target = adj_harvesters[0]
            if self.is_enemy_building(my_pos):
                # Check for actual healing: if we stood here last turn
                # and fired, we know what HP we LEFT the tile at. If
                # the current HP is strictly higher, an enemy builder
                # must have healed. Only give up the tile when we have
                # that concrete evidence.
                being_healed = False
                if self.last_fire_pos == my_pos:
                    bid_here = ct.get_tile_building_id(my_pos)
                    if bid_here is not None:
                        current_hp = ct.get_hp(bid_here)
                        if current_hp > self.last_fire_expected_hp:
                            being_healed = True
                if being_healed:
                    # Don't come back to this tile for 5 turns — the
                    # enemy healer in range will just out-heal us
                    # again. Let the picker try a different neighbour
                    # (or a different harvester entirely once this
                    # tile is off the table).
                    self.attack_tile_blacklist[my_pos] = 5
                    alt = _pick_attack_destination(self, ct, target)
                    if alt is not None and alt != my_pos:
                        self.last_fire_pos = None
                        make_move(self, ct, alt)
                        return
                # Always fire — maintain pressure even if an enemy
                # healer is nearby. being_healed detection (above)
                # handles rotation when we're truly outpaced.
                bid_here = ct.get_tile_building_id(my_pos)
                if bid_here is not None:
                    pre_hp = ct.get_hp(bid_here)
                    self.last_fire_pos = my_pos
                    self.last_fire_expected_hp = max(0, pre_hp - 2)
                try_attack(ct)
                self.offense_target = my_pos
                self.offense_turns = 0

            else:
                build_position = self.my_pos
                move_random(self, ct)
                direction = build_position.direction_to(enemy_core)
                if direction == build_position.direction_to(target):
                    direction = direction.rotate_right()

                # Cap turrets adjacent to the target harvester at
                # 2 gunners + 1 sentinel. Gunners eat the enemy
                # conveyor chain tile-by-tile along their ray; stacking
                # a second gunner on the opposite side roughly doubles
                # chain pressure. Sentinel applies harvester pressure.
                n_gunner = 0
                n_sentinel = 0
                for d in DIR4:
                    nb = self.get_building(target.add(d))
                    if nb is None or nb.team != self.my_team:
                        continue
                    if isinstance(nb, BuildingGunner):
                        n_gunner += 1
                    elif isinstance(nb, BuildingSentinel):
                        n_sentinel += 1

                if n_gunner < 2:
                    gdir = _gunner_chain_facing(self, ct, build_position)
                    if gdir is not None:
                        try_place(ct, EntityType.GUNNER, build_position, gdir)

                if (
                    n_sentinel == 0
                    and self.get_env(target) == Environment.ORE_TITANIUM
                ):
                    try_place(ct, EntityType.SENTINEL, build_position, direction)

                if ct.can_build_road(build_position) and not self.get_building(
                    build_position
                ):
                    ct.build_road(build_position)
                scout_toward_enemy(self, ct)

        else:
            # Pick any walkable cardinal neighbour of the target. We
            # don't pre-filter by healer range here — bots that show
            # up and start attacking might get out-healed, but giving
            # up on approach over every possible enemy bot nearby is
            # worse: enemy bots are common around enemy harvesters
            # (building them), and we'd reject almost every target.
            destinations = [
                dest
                for h in targets
                if (dest := _pick_attack_destination(self, ct, h, avoid_healers=False))
            ]
            if not destinations:
                # Original fallback: allow any walkable non-friendly-
                # transport cardinal. This covers cases where
                # _pick_attack_destination is too strict.
                destinations = [
                    pos
                    for h in targets
                    for pos in without_allied_transport(
                        self, ct, open_tiles(self, ct, [h.add(d) for d in DIR4])
                    )
                ]
                if not destinations:
                    scout_toward_enemy(self, ct)
                    return

            nearest_dest = min(dist_to_me(d) for d in destinations)
            nearest_target = min(dist_to_me(h) for h in targets)

            if nearest_dest <= 2 or nearest_target < 9:
                make_multi_move(self, ct, destinations)
            else:
                my_pos_adj = [my_pos.add(d) for d in DIR8]
                adjacent_launchers = [
                    p
                    for p in my_pos_adj
                    if isinstance(self.get_building(p), BuildingLauncher)
                ]

                nearest_destination = min(destinations, key=dist_to_me)
                best_new_launcher = closest(
                    nearest_destination, buildable(self, my_pos_adj)
                )

                if (
                    adjacent_launchers
                    and self.is_walkable(nearest_destination)
                    and min(
                        nearest_destination.distance_squared(p)
                        for p in adjacent_launchers
                    )
                    <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                ):
                    pass
                elif (
                    best_new_launcher
                    and not adjacent_launchers
                    and self.is_walkable(nearest_destination)
                    and best_new_launcher.distance_squared(nearest_destination)
                    <= GameConstants.LAUNCHER_VISION_RADIUS_SQ
                    and try_place(ct, EntityType.LAUNCHER, best_new_launcher)
                ):
                    self.offense_launcher = best_new_launcher
                elif self.offense_launcher and dist_to_me(self.offense_launcher) < 25:
                    make_move(self, ct, self.offense_launcher)
                elif self.offense_target and dist_to_me(self.offense_target) < 20:
                    make_move(self, ct, self.offense_target)
                else:
                    make_multi_move(self, ct, targets)

        # refresh position after move
        my_pos = self.my_pos
        dist_to_me = my_pos.distance_squared

        if any(dist_to_me(h) == 1 for h in targets) and self.is_enemy_building(my_pos):
            try_attack(ct)

    elif (
        self.offense_target
        and self.offense_launcher
        and isinstance(
            rl := self.get_building(self.offense_launcher), BuildingLauncher
        )
        and rl.team == self.my_team
        and self.my_pos.distance_squared(self.offense_target) > 8
    ):
        make_move(self, ct, self.offense_launcher)
    elif self.offense_target:
        make_move(self, ct, self.offense_target)
        if self.my_pos == self.offense_target and try_attack(ct):
            self.offense_turns = 0
    else:
        # No vulnerable harvester and no cached offense target —
        # spread out to an enemy conveyor target instead. Prefer
        # core-proximal flow tiles, then visible-flow tiles. Spacing
        # score keeps us away from our other attackers so a single
        # enemy healer can't cover two of us.
        conveyor_target = _pick_conveyor_target(
            self, ct, enemy_core, self.my_pos
        )
        if conveyor_target is not None:
            if self.my_pos == conveyor_target:
                if try_attack(ct):
                    self.offense_target = conveyor_target
                    self.offense_turns = 0
            else:
                make_move(self, ct, conveyor_target)
        else:
            scout_toward_enemy(self, ct)


def scout_toward_enemy(self: Builder, ct: Controller) -> None:
    en_core = get_enemy_core_pos(self)
    if self.my_pos.distance_squared(en_core) <= 20:
        self.enemy_core_seen = True

    if not self.enemy_core_seen:
        make_move(self, ct, en_core)
    elif self.my_pos.distance_squared(en_core) <= 20 or ct.get_global_resources()[
        0
    ] >= (GameConstants.HARVESTER_BASE_COST[0] + 50) * (
        1 + ct.get_scale_percent() / 100
    ):
        explore(self, ct)
    else:
        dir8 = DIR8[:]
        self.rng.shuffle(dir8)
        my_pos = self.my_pos
        for d in dir8:
            if try_move(self, ct, my_pos.add(d)):
                break
