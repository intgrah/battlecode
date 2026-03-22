"""Hijack Bot -- Parasitic gunner strategy.

Strategy:
  1. Derive enemy core position from map symmetry (no scouts needed).
  2. First 4 bots: eco — each builds harvester + bridge conveyor chains
     continuously until no more ore is found, then switches to hijack.
  3. All other bots: march toward enemy core, building roads.
  4. Drop a gunner on an empty tile next to the core fed by an enemy conveyor.
  5. Self-destruct on enemy conveyors feeding directly into the core.
"""

import contextlib
import random

from cambc import Controller, Direction, EntityType, Environment, Position

DIRS = [d for d in Direction if d != Direction.CENTRE]
CARDINAL = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]


class Player:
    def __init__(self) -> None:
        self.team = -1
        self.w = 0
        self.h = 0

        # Builder state
        self.core_pos = None
        self.enemy_core = None
        self.enemy_core_candidates = []  # symmetry candidates to try
        self.role = None  # 'eco' or 'hijack'
        self.target_ore = None
        self.prev_pos = None
        self.explore_dir = None
        self.stuck = 0
        self.path = []  # BFS path as list of Positions
        self.path_target = None  # target the path was computed for

        # Eco state -- build plan: bridge, conveyors bridge->outward, harvester last
        self.build_plan = None  # list of ('bridge', pos, target) / ('conveyor', pos, dir) / ('harvester', pos, None)
        self.plan_idx = 0
        self.plan_set = set()  # positions reserved for the plan (don't put roads here)
        self.eco_idx = 0  # index for distributing eco bots to different ore
        self.chains_built = 0  # number of harvester chains completed
        self.known_walls = set()  # wall positions discovered during chain execution

        # Core state
        self.builders_spawned = 0

    def run(self, ct: Controller) -> None:
        if self.team == -1:
            self.team = ct.get_team()
            self.w = ct.get_map_width()
            self.h = ct.get_map_height()

        t = ct.get_entity_type()
        if t == EntityType.CORE:
            self._core(ct)
        elif t == EntityType.BUILDER_BOT:
            self._builder(ct)
        elif t == EntityType.GUNNER:
            self._gunner(ct)

    # == Core ======================================================

    def _core(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()
        c = ct.get_position()

        # Ramp up builder production over time (aggressive: 4 initial for eco)
        want = min(4 + max(0, (rnd - 5) // 15), 14)
        if self.builders_spawned >= want:
            return
        if ti < cost + 20:
            return

        mid = Position(self.w // 2, self.h // 2)
        primary = c.direction_to(mid)
        for d in _dir_pri(primary):
            sp = c.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                self.builders_spawned += 1
                return

    # == Builder ===================================================

    def _builder(self, ct: Controller) -> None:
        if self.core_pos is None:
            self._init_builder(ct)

        if self.role == "eco":
            self._eco(ct)
        else:
            self._hijack(ct)

    def _init_builder(self, ct: Controller) -> None:
        pos = ct.get_position()
        # Find our core
        for eid in ct.get_nearby_entities():
            try:
                if (
                    ct.get_entity_type(eid) == EntityType.CORE
                    and ct.get_team(eid) == self.team
                ):
                    self.core_pos = ct.get_position(eid)
                    break
            except Exception:
                continue
        if self.core_pos is None:
            self.core_pos = pos

        # Derive enemy core candidates from all possible map symmetries
        cx, cy = self.core_pos.x, self.core_pos.y
        self.enemy_core_candidates = [
            Position(self.w - 1 - cx, self.h - 1 - cy),  # 180 deg rotation
            Position(self.w - 1 - cx, cy),  # horizontal reflection (left<->right)
            Position(cx, self.h - 1 - cy),  # vertical reflection (top<->bottom)
        ]
        # Deduplicate (e.g. on a square map with centered core, some coincide)
        seen = set()
        deduped = []
        for c in self.enemy_core_candidates:
            key = (c.x, c.y)
            if key not in seen and key != (cx, cy):
                seen.add(key)
                deduped.append(c)
        self.enemy_core_candidates = deduped
        self.enemy_core = self.enemy_core_candidates[0] if deduped else None

        # Assign first 4 bots to eco via marker counting
        eco_count = 0
        for tile in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(tile)
            if bid is not None:
                try:
                    if (
                        ct.get_team(bid) == self.team
                        and ct.get_entity_type(bid) == EntityType.MARKER
                        and ct.get_marker_value(bid) == 42
                    ):
                        eco_count += 1
                except Exception:
                    pass

        if eco_count < 4:
            self.role = "eco"
            self.eco_idx = eco_count
            for d in DIRS:
                p = pos.add(d)
                if ct.can_place_marker(p):
                    ct.place_marker(p, 42)
                    break
        else:
            self.role = "hijack"

        if self.enemy_core is not None:
            base_dir = pos.direction_to(self.enemy_core)
            # Spread 4 eco bots in 4 directions to find different ore deposits
            if self.eco_idx == 0:
                self.explore_dir = base_dir
            elif self.eco_idx == 1:
                self.explore_dir = base_dir.rotate_left().rotate_left()
            elif self.eco_idx == 2:
                self.explore_dir = base_dir.rotate_right().rotate_right()
            else:
                self.explore_dir = base_dir.opposite()
        else:
            self.explore_dir = pos.direction_to(Position(self.w // 2, self.h // 2))

    # == Eco ======================================================

    def _eco(self, ct: Controller) -> None:
        """Unified eco: find ore, plan chain, build conveyors core->outward, harvester last."""
        # Phase 0: Find ore and create the build plan
        if self.build_plan is None:
            self._eco_plan(ct)
            return

        # Phase 1: Execute build plan step by step
        if self.plan_idx >= len(self.build_plan):
            # Chain complete — try to build another
            self.chains_built += 1
            self.build_plan = None
            # Rotate explore direction to search new areas
            if self.explore_dir is not None:
                self.explore_dir = self.explore_dir.rotate_left().rotate_left()
            return

        btype, target_pos, target_dir = self.build_plan[self.plan_idx]

        # -- Handle blocked tiles --
        if ct.is_in_vision(target_pos):
            if ct.get_tile_env(target_pos) == Environment.WALL:
                # Chain hit a wall -- record it and re-plan around it
                self.known_walls.add((target_pos.x, target_pos.y))
                if ct.get_current_round() > 75:
                    self.role = "hijack"
                else:
                    self.build_plan = None
                return
            bid = ct.get_tile_building_id(target_pos)
            if bid is not None:
                try:
                    team = ct.get_team(bid)
                    etype = ct.get_entity_type(bid)
                    # Already the correct type here -- skip
                    if team == self.team and etype in (
                        EntityType.CONVEYOR,
                        EntityType.HARVESTER,
                        EntityType.BRIDGE,
                    ):
                        self.plan_idx += 1
                        return
                    # Any allied building blocking the plan tile -- destroy it
                    if team == self.team:
                        pos = ct.get_position()
                        if pos.distance_squared(target_pos) <= 2 and ct.can_destroy(
                            target_pos,
                        ):
                            ct.destroy(target_pos)
                        else:
                            # Move closer so we can destroy next round
                            self._move_toward(ct, target_pos, build_roads=True)
                        return
                    # Enemy building -- can't destroy, skip this step
                    self.plan_idx += 1
                    return
                except Exception:
                    self.plan_idx += 1
                    return

        # -- Try to build if in range --
        pos = ct.get_position()
        if pos.distance_squared(target_pos) <= 2:
            ti, _ = ct.get_global_resources()
            if btype == "harvester":
                cost, _ = ct.get_harvester_cost()
                if ti >= cost and ct.can_build_harvester(target_pos):
                    ct.build_harvester(target_pos)
                    self.plan_idx += 1
                    return
            elif btype == "bridge":
                cost, _ = ct.get_bridge_cost()
                if ti >= cost + 10 and ct.can_build_bridge(target_pos, target_dir):
                    ct.build_bridge(target_pos, target_dir)
                    self.plan_idx += 1
                    return
            else:  # conveyor
                cost, _ = ct.get_conveyor_cost()
                if ti >= cost + 10 and ct.can_build_conveyor(target_pos, target_dir):
                    ct.build_conveyor(target_pos, target_dir)
                    self.plan_idx += 1
                    return

        # -- Move toward build position --
        self._move_toward(ct, target_pos, build_roads=True)

    def _eco_plan(self, ct: Controller) -> None:
        """Find titanium ore and create a full build plan (conveyors + harvester)."""
        pos = ct.get_position()
        core = self.core_pos

        # Collect ALL valid titanium ore tiles, sorted by score
        ore_list = []
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) == Environment.ORE_TITANIUM:
                if ct.get_tile_building_id(tile) is None:
                    d_core = tile.distance_squared(core)
                    d_me = pos.distance_squared(tile)
                    score = d_core * 3 + d_me
                    ore_list.append((score, tile))

        ore_list.sort()

        # Pick ore: first chain uses eco_idx to distribute, subsequent pick best available
        best_ore = None
        if self.chains_built > 0:
            if ore_list:
                best_ore = ore_list[0][1]
        elif self.eco_idx < len(ore_list):
            best_ore = ore_list[self.eco_idx][1]
        elif self.eco_idx == 0 and ore_list:
            best_ore = ore_list[0][1]

        if best_ore is None:
            # No ore visible -- explore briefly, then switch to hijack
            if self.chains_built > 0 or ct.get_current_round() > 50:
                self.role = "hijack"
                return
            if self.explore_dir is None or self.explore_dir == Direction.CENTRE:
                self.explore_dir = core.direction_to(
                    Position(self.w // 2, self.h // 2),
                )
            explore_target = pos
            for _ in range(5):
                explore_target = explore_target.add(self.explore_dir)
            self._move_toward(ct, explore_target, build_roads=True)
            return

        # Gather known walls for chain planning
        walls = set(self.known_walls)
        for tile in ct.get_nearby_tiles():
            if ct.get_tile_env(tile) == Environment.WALL:
                walls.add((tile.x, tile.y))

        # Plan conveyor chain from ore toward a bridge position near core
        chain, bridge_pos, bridge_target = _plan_conveyor_chain(
            best_ore,
            core,
            self.w,
            self.h,
            walls,
        )
        if bridge_pos is None:
            self.role = "hijack"
            return

        # Build order: bridge first, then conveyors from bridge outward, harvester last.
        # Builder walks from core (via roads) to bridge, then along conveyors.
        self.build_plan = [("bridge", bridge_pos, bridge_target)]
        for cpos, cdir in reversed(chain):
            self.build_plan.append(("conveyor", cpos, cdir))
        self.build_plan.append(("harvester", best_ore, None))
        self.plan_idx = 0
        self.plan_set = {step[1] for step in self.build_plan}

    # == Hijack ===================================================

    def _update_enemy_core(self, ct: Controller) -> None:
        """Scan vision for the real enemy core; eliminate wrong candidates."""
        # Fast path: already confirmed (candidates list empty)
        if not self.enemy_core_candidates:
            return

        # Check all visible buildings for enemy core -- might spot it from any angle
        for eid in ct.get_nearby_buildings():
            try:
                if (
                    ct.get_entity_type(eid) == EntityType.CORE
                    and ct.get_team(eid) != self.team
                ):
                    self.enemy_core = ct.get_position(eid)
                    self.enemy_core_candidates = []  # confirmed
                    return
            except Exception:
                continue

        # If current candidate is in vision but no enemy core there, eliminate it
        ec = self.enemy_core
        if ec is not None and ct.is_in_vision(ec):
            bid = ct.get_tile_building_id(ec)
            is_core = False
            if bid is not None:
                with contextlib.suppress(Exception):
                    is_core = (
                        ct.get_entity_type(bid) == EntityType.CORE
                        and ct.get_team(bid) != self.team
                    )
            if not is_core:
                # Wrong -- remove and try next candidate
                self.enemy_core_candidates = [
                    c for c in self.enemy_core_candidates if (c.x, c.y) != (ec.x, ec.y)
                ]
                if self.enemy_core_candidates:
                    self.enemy_core = self.enemy_core_candidates[0]
                else:
                    self.enemy_core = None
                self.path = []  # clear stale path

    def _hijack(self, ct: Controller) -> None:
        self._update_enemy_core(ct)
        pos = ct.get_position()
        ec = self.enemy_core
        if ec is None:
            return

        w, h = self.w, self.h

        # -- Priority 1: Drop gunner on empty tile next to core fed by enemy conveyor --
        for eid in ct.get_nearby_buildings():
            try:
                if ct.get_team(eid) == self.team:
                    continue
                etype = ct.get_entity_type(eid)
                if etype not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                    continue
                cpos = ct.get_position(eid)
                cdir = ct.get_direction(eid)
                out = cpos.add(cdir)
                if not _in_bounds(out, w, h):
                    continue
                if not ct.is_in_vision(out) or not ct.is_tile_empty(out):
                    continue
                # Output tile must be adjacent to enemy core (Chebyshev distance 2 from center = touching the 3x3)
                if max(abs(out.x - ec.x), abs(out.y - ec.y)) != 2:
                    continue
                # Find the best facing direction: must actually hit enemy core
                gun_dir = _best_gunner_dir(ct, out, cpos, self.team)
                if gun_dir is None:
                    continue
                if pos.distance_squared(out) <= 2 and ct.can_build_gunner(out, gun_dir):
                    ct.build_gunner(out, gun_dir)
                    print(f"HIJACK: gunner at {out} facing {gun_dir}")
                    return
                # Walk to it
                self._move_toward(ct, out, build_roads=True)
                return
            except Exception:
                continue

        # -- Priority 2: Self-destruct on enemy conveyor adjacent to core --
        # Already standing on an enemy building next to the core? Blow up!
        bid = ct.get_tile_building_id(pos)
        if bid is not None:
            try:
                if ct.get_team(bid) != self.team:
                    if max(abs(pos.x - ec.x), abs(pos.y - ec.y)) <= 2:
                        ct.self_destruct()
                        print(f"HIJACK: self-destruct at {pos}")
                        return
            except Exception:
                pass

        # Look for enemy conveyors adjacent to core to walk onto and self-destruct
        best_sd = None
        best_sd_dist = 9999
        for eid in ct.get_nearby_buildings():
            try:
                if ct.get_team(eid) == self.team:
                    continue
                etype = ct.get_entity_type(eid)
                if etype not in (
                    EntityType.CONVEYOR,
                    EntityType.ARMOURED_CONVEYOR,
                    EntityType.SPLITTER,
                ):
                    continue
                bpos = ct.get_position(eid)
                bdir = ct.get_direction(eid)
                out_tile = bpos.add(bdir)
                # Check if this conveyor's output goes INTO the core (Chebyshev <= 1 from center)
                if max(abs(out_tile.x - ec.x), abs(out_tile.y - ec.y)) <= 1:
                    # This conveyor feeds directly into the core -- self-destruct target!
                    d = pos.distance_squared(bpos)
                    if d < best_sd_dist:
                        best_sd_dist = d
                        best_sd = bpos
            except Exception:
                continue

        if best_sd is not None:
            if pos == best_sd:
                ct.self_destruct()
                print(f"HIJACK: self-destruct at {pos}")
                return
            # Walk onto it
            if pos.distance_squared(best_sd) <= 2:
                d = pos.direction_to(best_sd)
                if ct.can_move(d):
                    ct.move(d)
                    return
            self._move_toward(ct, best_sd, build_roads=True)
            return

        # -- Priority 3: March toward the enemy core, building roads --
        self._move_toward(ct, ec, build_roads=True)

    # == Movement =================================================

    def _move_toward(self, ct: Controller, target: Position, build_roads: bool) -> None:
        if ct.get_move_cooldown() > 0:
            return

        pos = ct.get_position()
        if pos == target:
            return

        w, h = self.w, self.h

        # Invalidate cached path if target changed or we drifted off path
        if self.path and (self.path_target != target or pos not in self.path):
            self.path = []

        # Pop completed steps from the front of the cached path
        if self.path:
            while self.path and self.path[0] != pos:
                self.path.pop(0)
            if self.path:
                self.path.pop(0)  # remove current pos

        # Recompute path via BFS within vision if needed
        if not self.path:
            self.path = _bfs(ct, pos, target, w, h)
            self.path_target = target

        # Try to follow the BFS path
        if self.path:
            nxt = self.path[0]
            d = pos.direction_to(nxt)
            if d != Direction.CENTRE:
                if ct.is_in_vision(nxt):
                    env = ct.get_tile_env(nxt)
                    if env == Environment.WALL:
                        self.path = []  # path invalidated, will recompute next round
                    else:
                        if ct.is_tile_empty(nxt):
                            if build_roads and nxt not in self.plan_set:
                                ti, _ = ct.get_global_resources()
                                if ti > 20 and ct.can_build_road(nxt):
                                    ct.build_road(nxt)
                                # If can't afford road, fall through to greedy
                        if ct.can_move(d):
                            self.prev_pos = pos
                            self.stuck = 0
                            ct.move(d)
                            return
                # Next tile is outside vision -- move toward it greedily
                elif ct.can_move(d):
                    self.prev_pos = pos
                    self.stuck = 0
                    ct.move(d)
                    return

        # -- Greedy fallback (BFS didn't produce a usable step) --
        primary = pos.direction_to(target)
        if primary == Direction.CENTRE:
            return

        # Pass 1: Move forward, avoid prev_pos
        for d in _dir_pri(primary):
            nxt = pos.add(d)
            if not _in_bounds(nxt, w, h):
                continue
            if self.prev_pos and nxt == self.prev_pos:
                continue
            if not ct.is_in_vision(nxt):
                if ct.can_move(d):
                    self.prev_pos = pos
                    self.stuck = 0
                    ct.move(d)
                    return
                continue
            env = ct.get_tile_env(nxt)
            if env == Environment.WALL:
                continue

            if ct.is_tile_empty(nxt):
                if build_roads and nxt not in self.plan_set:
                    ti, _ = ct.get_global_resources()
                    if ti > 20 and ct.can_build_road(nxt):
                        ct.build_road(nxt)
                    else:
                        continue
                else:
                    continue

            if ct.can_move(d):
                self.prev_pos = pos
                self.stuck = 0
                ct.move(d)
                return

        # Pass 2: Allow backtracking
        for d in _dir_pri(primary):
            nxt = pos.add(d)
            if not _in_bounds(nxt, w, h):
                continue
            if ct.is_in_vision(nxt) and ct.get_tile_env(nxt) == Environment.WALL:
                continue
            if ct.can_move(d):
                self.prev_pos = pos
                ct.move(d)
                return

        # Stuck handling -- clear path to force recompute
        self.stuck += 1
        if self.stuck > 3:
            self.path = []
            self.prev_pos = None
            self.stuck = 0

    # == Gunner ==================================================

    def _gunner(self, ct: Controller) -> None:
        target = ct.get_gunner_target()
        if target is not None and ct.can_fire(target):
            ct.fire(target)


# -- Helpers ----------------------------------------------------------


def _in_bounds(p: Position, w: int, h: int) -> bool:
    return 0 <= p.x < w and 0 <= p.y < h


_DIR_PRI_CACHE = {
    d: [
        d,
        d.rotate_left(),
        d.rotate_right(),
        d.rotate_left().rotate_left(),
        d.rotate_right().rotate_right(),
        d.opposite().rotate_right(),
        d.opposite().rotate_left(),
        d.opposite(),
    ]
    for d in DIRS
}


def _dir_pri(primary: Direction) -> list[Direction]:
    if primary == Direction.CENTRE:
        return random.sample(DIRS, len(DIRS))
    return _DIR_PRI_CACHE[primary]


def _bfs(ct: Controller, start: Position, goal: Position, w: int, h: int) -> list:
    """BFS within vision to find a walkable path from start toward goal.

    Returns a list of Positions (excluding start) forming the path.
    If goal is outside vision, returns path to the visible tile closest to goal.
    """
    queue = [start]
    head = 0
    came_from = {start: None}
    best = start
    best_dist = start.distance_squared(goal)

    while head < len(queue):
        cur = queue[head]
        head += 1
        if cur == goal:
            best = cur
            break

        d = cur.distance_squared(goal)
        if d < best_dist:
            best_dist = d
            best = cur

        for direction in DIRS:
            nxt = cur.add(direction)
            if nxt in came_from:
                continue
            if not _in_bounds(nxt, w, h):
                continue
            if not ct.is_in_vision(nxt):
                # Treat out-of-vision tiles as potentially walkable if they get us closer
                d2 = nxt.distance_squared(goal)
                if d2 < best_dist:
                    came_from[nxt] = cur
                    best_dist = d2
                    best = nxt
                continue
            env = ct.get_tile_env(nxt)
            if env == Environment.WALL:
                continue
            came_from[nxt] = cur
            queue.append(nxt)

    if best == start:
        return []

    # Reconstruct path
    path = []
    node = best
    while node is not None and node != start:
        path.append(node)
        node = came_from[node]
    path.reverse()
    return path


def _plan_conveyor_chain(harv, core, w, h, walls=None):
    """Plan a conveyor chain from harvester to a bridge position near core.

    The bridge is placed at Chebyshev distance > 2 from core center but within
    Euclidean distance² ≤ 9 of a core tile, so it can teleport resources in
    without being adjacent (defeating hijack attacks on the conveyor output).

    Returns (conveyor_chain, bridge_pos, bridge_target) where:
    - conveyor_chain: list of (Position, Direction) for intermediate conveyors
    - bridge_pos: Position for the bridge (or None if no valid path)
    - bridge_target: Position of the core tile the bridge outputs to
    """
    if walls is None:
        walls = set()

    # BFS from harv toward a valid bridge position, cardinal only
    queue = [harv]
    head = 0
    came_from = {(harv.x, harv.y): None}
    goal = None
    goal_target = None

    while head < len(queue):
        cur = queue[head]
        head += 1

        for d in CARDINAL:
            nxt = cur.add(d)
            key = (nxt.x, nxt.y)
            if key in came_from:
                continue
            if not _in_bounds(nxt, w, h):
                continue
            if key in walls:
                continue
            # Don't route through core tiles
            if max(abs(nxt.x - core.x), abs(nxt.y - core.y)) <= 1:
                continue

            came_from[key] = cur

            # Valid bridge position: Chebyshev > 2 from core center
            # AND Euclidean distance² ≤ 9 from a core tile
            if max(abs(nxt.x - core.x), abs(nxt.y - core.y)) > 2:
                tx = max(core.x - 1, min(core.x + 1, nxt.x))
                ty = max(core.y - 1, min(core.y + 1, nxt.y))
                dist_sq = (nxt.x - tx) ** 2 + (nxt.y - ty) ** 2
                if dist_sq <= 9:
                    goal = nxt
                    goal_target = Position(tx, ty)
                    break

            queue.append(nxt)

        if goal is not None:
            break

    if goal is None:
        return [], None, None

    # Reconstruct full path: [harv, step1, step2, ..., bridge_pos]
    path = []
    node = goal
    while node is not None:
        path.append(node)
        node = came_from[(node.x, node.y)]
    path.reverse()

    # Conveyor positions = everything except harv (first) and bridge_pos (last)
    conv_positions = path[1:-1]

    # Assign facing directions: each conveyor points toward the next step
    plan = []
    for i, cpos in enumerate(conv_positions):
        nxt_pos = conv_positions[i + 1] if i + 1 < len(conv_positions) else goal
        dx = nxt_pos.x - cpos.x
        dy = nxt_pos.y - cpos.y
        if abs(dx) >= abs(dy):
            d = Direction.EAST if dx > 0 else Direction.WEST
        else:
            d = Direction.SOUTH if dy > 0 else Direction.NORTH
        plan.append((cpos, d))

    return plan, goal, goal_target


def _best_gunner_dir(ct, gunner_pos, conveyor_pos, team):
    """Find the best direction for a gunner so it actually hits the enemy core.

    Checks actual tile contents instead of computed positions.
    Accounts for diagonal-facing gunners accepting ammo from all sides.
    Returns a Direction, or None if no valid direction exists.
    """
    feed_side = gunner_pos.direction_to(conveyor_pos)

    # Try all 8 directions, prioritizing ones toward the conveyor's output direction
    # (which should point toward the core)
    primary = conveyor_pos.direction_to(gunner_pos)
    if primary == Direction.CENTRE:
        candidates = DIRS
    else:
        # The conveyor outputs toward the gunner, so the core is roughly
        # in the direction the conveyor was going -- use the conveyor->gunner direction
        # extended past the gunner
        candidates = _dir_pri(primary)

    for d in candidates:
        # Scan along the firing line for the first non-empty tile
        scan = gunner_pos
        hit_core = False
        for _ in range(6):  # gunner attack r2=13, max range ~3.6 tiles
            scan = scan.add(d)
            if not _in_bounds(scan, ct.get_map_width(), ct.get_map_height()):
                break
            if not ct.is_in_vision(scan):
                break
            bid = ct.get_tile_building_id(scan)
            uid = ct.get_tile_builder_bot_id(scan)
            if bid is not None:
                try:
                    if (
                        ct.get_entity_type(bid) == EntityType.CORE
                        and ct.get_team(bid) != team
                    ):
                        hit_core = True
                except Exception:
                    pass
                break  # Hit something (core or not), stop scanning
            if uid is not None:
                break  # Hit a unit, stop scanning

        if not hit_core:
            continue

        # Check ammo compatibility
        # Diagonal-facing gunners accept ammo from all four sides -- no restriction
        if d in (
            Direction.NORTHEAST,
            Direction.SOUTHEAST,
            Direction.SOUTHWEST,
            Direction.NORTHWEST,
        ):
            return d

        # Cardinal-facing gunners can't accept ammo from the facing direction
        if d != feed_side:
            return d

    return None
