import random

from cambc import Direction, Position

CARDINALS = [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
DIRS = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]
NUM_EXPLORERS = 8


class Player:
    def __init__(self) -> None:
        self.num_spawned = 0
        self.scout_dir = None
        self.stuck_turns = 0
        self.role = None
        self.core_pos = None
        self.turns_alive = 0
        # Chaining state
        self.chain_waypoints = None
        self.chain_index = 0
        self.chain_stuck = 0
        self.chain_turns = 0
        # Patrol state
        self.my_harvester = None
        self.chain_complete = False  # True once a chain has been fully built to core
        self.patrol_waypoints = None
        self.patrol_index = 0
        self.patrol_forward = True
        self.guard_pos = None  # bridge tile to park on
        # Repair state
        self.repair_pos = None
        self.repair_from = None
        self.repair_turns = 0

    def run(self, c) -> None:
        etype = str(c.get_entity_type())
        if "CORE" in etype:
            self.run_core(c)
        elif "BUILDER" in etype:
            self.run_builder(c)

    # ---- CORE ----
    def run_core(self, c) -> None:
        ti, _ = c.get_global_resources()
        cost, _ = c.get_builder_bot_cost()

        if self.num_spawned < NUM_EXPLORERS:
            if ti >= cost + 80:
                self._spawn(c)
            return

        rnd = c.get_current_round()
        if rnd >= 200 and ti >= cost + 200:
            self._spawn(c)

    def _spawn(self, c) -> None:
        cp = c.get_position()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                sp = Position(cp.x + dx, cp.y + dy)
                if c.can_spawn(sp):
                    c.spawn_builder(sp)
                    self.num_spawned += 1
                    return

    # ---- BUILDER ----
    def run_builder(self, c) -> None:
        self.turns_alive += 1

        if self.role is None:
            self.core_pos = self._find_core(c)
            rnd = c.get_current_round()
            if rnd <= 200:
                self.role = "explorer"
            else:
                self.role = "raider"

        if self.role == "explorer":
            self._run_explorer(c)
        elif self.role == "chaining":
            self._run_chainer(c)
        elif self.role == "patrolling":
            self._run_patroller(c)
        elif self.role == "repairing":
            self._run_repairer(c)
        elif self.role == "raider":
            self._run_raider(c)

    # ---- EXPLORER ----
    def _run_explorer(self, c) -> None:
        if c.get_current_round() >= 200:
            self.role = "raider"
            self._run_raider(c)
            return

        pos = c.get_position()
        ti, _ = c.get_global_resources()
        c.get_team()

        # Check for disconnected harvesters nearby and reconnect
        disconnected = self._find_disconnected_harvester(c)
        if disconnected is not None:
            harv_pos, build_pos = disconnected
            self.repair_pos = build_pos
            self.repair_from = harv_pos
            self.repair_turns = 0
            self.role = "repairing"
            self._run_repairer(c)
            return

        # Check for hanging bridges (broken chains) and repair
        hanging = self._find_hanging_bridge(c)
        if hanging is not None:
            bridge_pos, gap_pos = hanging
            self.repair_pos = gap_pos
            self.repair_from = bridge_pos
            self.repair_turns = 0
            self.role = "repairing"
            self._run_repairer(c)
            return

        # Build harvester on any adjacent unclaimed ore
        for d in DIRS:
            adj = pos.add(d)
            try:
                if not self._is_ore(c, adj):
                    continue
                if c.get_tile_building_id(adj) is not None:
                    continue
                h_cost, _ = c.get_harvester_cost()
                if ti >= h_cost and c.can_build_harvester(adj):
                    c.build_harvester(adj)
                    self.my_harvester = adj
                    bridge_start = self._find_bridge_start(c, adj, pos)
                    self._start_chain(c, bridge_start)
                    return
                return
            except Exception:
                pass

        # Scan vision for unclaimed ore
        best_ore = None
        best_dist = 999
        for tile in c.get_nearby_tiles():
            try:
                if not self._is_ore(c, tile):
                    continue
                if c.get_tile_building_id(tile) is not None:
                    continue
                dist = pos.distance_squared(tile)
                if dist < best_dist:
                    best_dist = dist
                    best_ore = tile
            except Exception:
                pass

        if best_ore is not None:
            self.scout_dir = pos.direction_to(best_ore)

        self._explore(c)

    def _explore(self, c) -> None:
        """Walk outward laying roads, navigating around walls."""
        pos = c.get_position()
        ti, _ = c.get_global_resources()

        if self.scout_dir is None:
            self.scout_dir = DIRS[c.get_id() % 8]

        next_pos = pos.add(self.scout_dir)

        try:
            if self._is_ore(c, next_pos):
                return

            bid = c.get_tile_building_id(next_pos)
            road_cost, _ = c.get_road_cost()

            if bid is None:
                if ti >= road_cost and c.can_build_road(next_pos):
                    c.build_road(next_pos)
                elif not c.can_build_road(next_pos):
                    self.stuck_turns += 1
                    if self.stuck_turns > 4:
                        self._redirect()
                    else:
                        self._try_move(c, self.scout_dir, ti)
                    return
                else:
                    return

            if c.can_move(self.scout_dir):
                c.move(self.scout_dir)
                self.stuck_turns = 0
            else:
                self.stuck_turns += 1
                if self.stuck_turns > 4:
                    self._redirect()
                else:
                    self._try_move(c, self.scout_dir, ti)
        except Exception:
            self._redirect()

    # ---- PATROLLER (guard a bridge) ----
    def _run_patroller(self, c) -> None:
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        my_team = c.get_team()

        if self.patrol_waypoints is None or len(self.patrol_waypoints) < 2:
            if c.get_current_round() >= 200 and not self.chain_complete:
                self.role = "raider"
                self._run_raider(c)
                return
            self.role = "explorer"
            return

        # Check if my harvester is dead
        if self.my_harvester is not None:
            try:
                if c.is_in_vision(self.my_harvester):
                    if c.get_tile_building_id(self.my_harvester) is None:
                        self.role = "explorer"
                        self.my_harvester = None
                        self.patrol_waypoints = None
                        self.guard_pos = None
                        return
            except Exception:
                pass

        # Scan for broken chain — fix immediately
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 20:
                    continue
                target = c.get_bridge_target(bid)
                if not c.is_in_vision(target):
                    continue
                if self._is_wall(c, target) or self._is_ore(c, target):
                    continue
                if c.get_tile_building_id(target) is None:
                    self.repair_pos = target
                    self.repair_from = c.get_position(bid)
                    self.repair_turns = 0
                    self.role = "repairing"
                    self._run_repairer(c)
                    return
            except Exception:
                continue

        # Check if harvester is disconnected — rebuild entire chain
        if self.my_harvester is not None:
            try:
                if c.is_in_vision(self.my_harvester):
                    harv_bid = c.get_tile_building_id(self.my_harvester)
                    if harv_bid is not None:
                        has_transport = False
                        for d in CARDINALS:
                            adj = self.my_harvester.add(d)
                            adj_bid = c.get_tile_building_id(adj)
                            if adj_bid is not None:
                                try:
                                    if (
                                        c.get_team(adj_bid) == my_team
                                        and c.get_hp(adj_bid) == 20
                                    ):
                                        has_transport = True
                                        break
                                except Exception:
                                    pass
                        if not has_transport:
                            if c.get_current_round() >= 200 and not self.chain_complete:
                                self.role = "raider"
                                self._run_raider(c)
                                return
                            bridge_start = self._find_bridge_start(
                                c,
                                self.my_harvester,
                                pos,
                            )
                            self._start_chain(c, bridge_start)
                            return
            except Exception:
                pass

        # Pick a bridge to guard — first bridge in chain (closest to harvester, most critical)
        if self.guard_pos is None and self.patrol_waypoints:
            # waypoints[0] is the first bridge (adjacent to harvester), skip last (conveyor)
            self.guard_pos = self.patrol_waypoints[0]

        # If guard bridge is gone, pick next available one from chain
        if self.guard_pos is not None:
            try:
                gbid = c.get_tile_building_id(self.guard_pos)
                if gbid is None and c.is_in_vision(self.guard_pos):
                    # Bridge destroyed — pick another from chain
                    for wp in self.patrol_waypoints[:-1]:
                        try:
                            wbid = c.get_tile_building_id(wp)
                            if (
                                wbid is not None
                                and c.get_team(wbid) == my_team
                                and c.get_hp(wbid) == 20
                            ):
                                self.guard_pos = wp
                                break
                        except Exception:
                            continue
            except Exception:
                pass

        # Park on the guard bridge
        if self.guard_pos is not None:
            if pos.x == self.guard_pos.x and pos.y == self.guard_pos.y:
                return  # Already parked — do nothing
            preferred = pos.direction_to(self.guard_pos)
            self._try_move(c, preferred, ti)

    # ---- BRIDGE CHAIN BUILDING ----
    def _start_chain(self, c, bridge_start) -> None:
        if self.core_pos is None:
            return
        core_adj = self._nearest_core_adj(bridge_start)
        self.chain_waypoints = self._calc_chain(c, bridge_start, core_adj)
        self.chain_index = 0
        self.chain_stuck = 0
        self.chain_turns = 0
        self.role = "chaining"

    def _nearest_core_adj(self, pos):
        best_adj = self.core_pos.add(CARDINALS[0])
        best_dist = 999999
        for d in CARDINALS:
            adj = self.core_pos.add(d)
            dist = (pos.x - adj.x) ** 2 + (pos.y - adj.y) ** 2
            if dist < best_dist:
                best_dist = dist
                best_adj = adj
        return best_adj

    def _calc_chain(self, c, start, core_adj):
        waypoints = [Position(start.x, start.y)]
        cx, cy = start.x, start.y
        max_iter = 50
        while max_iter > 0:
            max_iter -= 1
            dx = core_adj.x - cx
            dy = core_adj.y - cy
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 9:
                break
            chebyshev = max(abs(dx), abs(dy), 1)
            for step in (3, 2, 1):
                sx = round(dx / chebyshev * step)
                sy = round(dy / chebyshev * step)
                if sx * sx + sy * sy <= 9 and (sx != 0 or sy != 0):
                    break
            else:
                sx = 1 if dx > 0 else (-1 if dx < 0 else 0)
                sy = 1 if dy > 0 else (-1 if dy < 0 else 0)
            nx, ny = cx + sx, cy + sy
            candidate = Position(nx, ny)
            if self._is_wall(c, candidate) or self._is_ore(c, candidate):
                found = False
                prev = Position(cx, cy)
                for d in DIRS:
                    alt = candidate.add(d)
                    if self._is_wall(c, alt) or self._is_ore(c, alt):
                        continue
                    if prev.distance_squared(alt) > 9:
                        continue
                    nx, ny = alt.x, alt.y
                    found = True
                    break
                if not found:
                    cx += 1 if dx > 0 else -1 if dx < 0 else 0
                    cy += 1 if dy > 0 else -1 if dy < 0 else 0
                    continue
            cx, cy = nx, ny
            waypoints.append(Position(cx, cy))
        waypoints.append(core_adj)
        return waypoints

    def _run_chainer(self, c) -> None:
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        self.chain_turns += 1

        if c.get_current_round() >= 200 and not self.chain_complete:
            self.role = "raider"
            self.chain_waypoints = None
            self._run_raider(c)
            return

        if (
            self.chain_waypoints is None
            or self.chain_index >= len(self.chain_waypoints)
            or self.chain_turns > 80
        ):
            # Chain complete (or timed out) — start patrolling
            if self.chain_waypoints and self.my_harvester:
                self.patrol_waypoints = list(self.chain_waypoints)
                self.patrol_index = len(self.patrol_waypoints) - 1
                self.patrol_forward = False
                self.role = "patrolling"
            else:
                self.role = "explorer"
            self.chain_waypoints = None
            return

        idx = self.chain_index
        waypoints = self.chain_waypoints
        target = waypoints[idx]

        # Last waypoint: build conveyor pointing into core
        if idx == len(waypoints) - 1:
            dist_sq = pos.distance_squared(target)
            if dist_sq <= 2:
                self._build_core_conveyor(c, target)
                self.chain_complete = True
                self.patrol_waypoints = list(waypoints)
                self.patrol_index = len(self.patrol_waypoints) - 1
                self.patrol_forward = False
                self.role = "patrolling"
                self.chain_waypoints = None
                return
            self.chain_stuck += 1
            if self.chain_stuck > 15:
                if self.my_harvester and waypoints:
                    self.patrol_waypoints = list(waypoints)
                    self.patrol_index = 0
                    self.patrol_forward = True
                    self.role = "patrolling"
                else:
                    self.role = "explorer"
                self.chain_waypoints = None
                return
            preferred = pos.direction_to(target)
            road_cost, _ = c.get_road_cost()
            if ti >= road_cost:
                pref_idx = DIRS.index(preferred) if preferred in DIRS else 0
                for offset in (0, 1, -1):
                    d = DIRS[(pref_idx + offset) % 8]
                    try:
                        nxt = pos.add(d)
                        if self._is_ore(c, nxt) or self._is_wall(c, nxt):
                            continue
                        bid = c.get_tile_building_id(nxt)
                        if bid is None:
                            if c.can_build_road(nxt):
                                c.build_road(nxt)
                                if c.can_move(d):
                                    c.move(d)
                                    self.chain_stuck = 0
                                return
                    except Exception:
                        continue
            self._try_move(c, preferred, ti)
            return

        next_target = waypoints[idx + 1]

        if self.chain_stuck > 3:
            bridge_cost, _ = c.get_bridge_cost()
            if ti >= bridge_cost:
                if self._try_bridge_from_here(c, pos, waypoints, idx):
                    return
            if self.chain_stuck > 6:
                core_adj = waypoints[-1]
                new_chain = self._calc_chain(c, pos, core_adj)
                self.chain_waypoints = new_chain
                self.chain_index = 0
                self.chain_stuck = 0
                return

        if self._is_wall(c, target) or self._is_ore(c, target):
            self.chain_index += 1
            self.chain_stuck = 0
            return
        if self._is_wall(c, next_target) or self._is_ore(c, next_target):
            nudged = self._nudge_off_wall(c, next_target, target)
            if nudged is not None:
                waypoints[idx + 1] = nudged
                next_target = nudged
            else:
                self.chain_index += 1
                return

        dist_sq = pos.distance_squared(target)

        if dist_sq <= 2:
            bridge_cost, _ = c.get_bridge_cost()
            if ti < bridge_cost:
                return

            existing = c.get_tile_building_id(target)
            if existing is not None:
                try:
                    if c.get_team(existing) == c.get_team():
                        c.destroy(target)
                except Exception:
                    pass

            if c.can_build_bridge(target, next_target):
                c.build_bridge(target, next_target)
                self.chain_index += 1
                self.chain_stuck = 0
                return

            for d in DIRS:
                alt = target.add(d)
                if (
                    alt.distance_squared(next_target) <= 9
                    and alt.distance_squared(pos) <= 2
                ):
                    ex2 = c.get_tile_building_id(alt)
                    if ex2 is not None:
                        try:
                            if c.get_team(ex2) == c.get_team():
                                c.destroy(alt)
                            else:
                                continue
                        except Exception:
                            continue
                    if c.can_build_bridge(alt, next_target):
                        c.build_bridge(alt, next_target)
                        self.chain_index += 1
                        self.chain_stuck = 0
                        return

            self.chain_index += 1
            self.chain_stuck = 0
            return

        self.chain_stuck += 1
        preferred = pos.direction_to(target)
        road_cost, _ = c.get_road_cost()
        if ti >= road_cost:
            pref_idx = DIRS.index(preferred) if preferred in DIRS else 0
            for offset in (0, 1, -1):
                d = DIRS[(pref_idx + offset) % 8]
                try:
                    nxt = pos.add(d)
                    if self._is_ore(c, nxt) or self._is_wall(c, nxt):
                        continue
                    bid = c.get_tile_building_id(nxt)
                    if bid is None and c.can_build_road(nxt):
                        c.build_road(nxt)
                        if c.can_move(d):
                            c.move(d)
                            self.chain_stuck = 0
                        return
                except Exception:
                    continue
        moved = self._try_move(c, preferred, ti)
        if moved is not None:
            self.chain_stuck = 0

    def _build_core_conveyor(self, c, conv_pos) -> None:
        if self.core_pos is None:
            return
        existing = c.get_tile_building_id(conv_pos)
        if existing is not None:
            try:
                team = c.get_team(existing)
                if team == c.get_team():
                    hp = c.get_hp(existing)
                    if hp == 20:
                        return
                    c.destroy(conv_pos)
                else:
                    return
            except Exception:
                return
        direction = conv_pos.direction_to(self.core_pos)
        conv_cost, _ = c.get_conveyor_cost()
        ti, _ = c.get_global_resources()
        if ti >= conv_cost:
            try:
                if c.can_build_conveyor(conv_pos, direction):
                    c.build_conveyor(conv_pos, direction)
            except Exception:
                pass

    # ---- BRIDGE REPAIR ----
    def _find_disconnected_harvester(self, c):
        """Find a friendly harvester with no adjacent bridge/conveyor."""
        my_team = c.get_team()
        pos = c.get_position()
        if self.core_pos is None:
            return None
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 30:
                    continue
                harv_pos = c.get_position(bid)
                if pos.distance_squared(harv_pos) > 25:
                    continue
                has_transport = False
                for d in CARDINALS:
                    adj = harv_pos.add(d)
                    adj_bid = c.get_tile_building_id(adj)
                    if adj_bid is not None:
                        try:
                            if (
                                c.get_team(adj_bid) == my_team
                                and c.get_hp(adj_bid) == 20
                            ):
                                has_transport = True
                                break
                        except Exception:
                            pass
                if has_transport:
                    continue
                best_adj = None
                best_dist = 999999
                for d in CARDINALS:
                    adj = harv_pos.add(d)
                    if self._is_wall(c, adj) or self._is_ore(c, adj):
                        continue
                    if c.get_tile_building_id(adj) is not None:
                        continue
                    dist = adj.distance_squared(self.core_pos)
                    if dist < best_dist:
                        best_dist = dist
                        best_adj = adj
                if best_adj is not None:
                    return (harv_pos, best_adj)
            except Exception:
                continue
        return None

    def _find_hanging_bridge(self, c):
        """Find a nearby friendly bridge whose target tile has no building."""
        my_team = c.get_team()
        pos = c.get_position()
        best = None
        best_dist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 20:
                    continue
                target = c.get_bridge_target(bid)
                if not c.is_in_vision(target):
                    continue
                if self._is_wall(c, target) or self._is_ore(c, target):
                    continue
                target_bid = c.get_tile_building_id(target)
                if target_bid is None:
                    gap_dist = pos.distance_squared(target)
                    if gap_dist <= 36 and gap_dist < best_dist:
                        best_dist = gap_dist
                        best = (c.get_position(bid), target)
            except Exception:
                continue
        return best

    def _find_repair_target(self, c, gap_pos):
        if self.core_pos is None:
            return None
        my_team = c.get_team()
        gap_to_core = gap_pos.distance_squared(self.core_pos)
        best_bid_pos = None
        best_dist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 20:
                    continue
                bpos = c.get_position(bid)
                if bpos.distance_squared(self.core_pos) >= gap_to_core:
                    continue
                if gap_pos.distance_squared(bpos) > 9:
                    continue
                dist = gap_pos.distance_squared(bpos)
                if dist < best_dist:
                    best_dist = dist
                    best_bid_pos = bpos
            except Exception:
                continue
        if best_bid_pos is not None:
            return best_bid_pos
        dx = self.core_pos.x - gap_pos.x
        dy = self.core_pos.y - gap_pos.y
        chebyshev = max(abs(dx), abs(dy), 1)
        for step in (3, 2, 1):
            sx = round(dx / chebyshev * step)
            sy = round(dy / chebyshev * step)
            if sx * sx + sy * sy <= 9 and (sx != 0 or sy != 0):
                candidate = Position(gap_pos.x + sx, gap_pos.y + sy)
                if not self._is_wall(c, candidate) and not self._is_ore(c, candidate):
                    return candidate
        for d in DIRS:
            candidate = gap_pos.add(d)
            if candidate.distance_squared(self.core_pos) < gap_pos.distance_squared(
                self.core_pos,
            ):
                if not self._is_wall(c, candidate) and not self._is_ore(c, candidate):
                    return candidate
        return None

    def _run_repairer(self, c) -> None:
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        self.repair_turns += 1
        prev_role = "patrolling" if self.my_harvester else "explorer"

        if self.repair_pos is None or self.repair_turns > 40:
            self.role = prev_role
            self.repair_pos = None
            self.repair_turns = 0
            return

        if self._is_wall(c, self.repair_pos) or self._is_ore(c, self.repair_pos):
            self.role = prev_role
            self.repair_pos = None
            return

        dist_sq = pos.distance_squared(self.repair_pos)

        if dist_sq <= 2:
            bridge_target = self._find_repair_target(c, self.repair_pos)
            if bridge_target is None:
                self.role = prev_role
                self.repair_pos = None
                return

            bridge_cost, _ = c.get_bridge_cost()
            if ti < bridge_cost:
                return

            existing = c.get_tile_building_id(self.repair_pos)
            if existing is not None:
                try:
                    if c.get_team(existing) == c.get_team():
                        c.destroy(self.repair_pos)
                    else:
                        self.role = prev_role
                        self.repair_pos = None
                        return
                except Exception:
                    pass

            if c.can_build_bridge(self.repair_pos, bridge_target):
                c.build_bridge(self.repair_pos, bridge_target)
                target_bid = c.get_tile_building_id(bridge_target)
                if (
                    target_bid is None
                    and bridge_target.distance_squared(self.core_pos) > 4
                ):
                    self.repair_from = self.repair_pos
                    self.repair_pos = bridge_target
                    return
                self.role = prev_role
                self.repair_pos = None
                return
            self.role = prev_role
            self.repair_pos = None
            return

        preferred = pos.direction_to(self.repair_pos)
        self._try_move(c, preferred, ti)

    # ---- RAIDER ----
    def _run_raider(self, c) -> None:
        pos = c.get_position()
        my_team = c.get_team()
        ti, _ = c.get_global_resources()

        # Priority 1: if standing on a friendly bridge, park here
        my_bid = c.get_tile_building_id(pos)
        if my_bid is not None:
            try:
                if c.get_team(my_bid) == my_team and c.get_hp(my_bid) == 20:
                    return  # Parked on friendly bridge — stay put
            except Exception:
                pass

        # Priority 2: find an unguarded friendly bridge and go sit on it
        best_bridge = None
        best_bdist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 20:
                    continue
                bpos = c.get_position(bid)
                # Check if any friendly unit is already on this bridge
                occupied = False
                for uid in c.get_nearby_units():
                    try:
                        if c.get_team(uid) == my_team and uid != c.get_id():
                            upos = c.get_position(uid)
                            if upos.x == bpos.x and upos.y == bpos.y:
                                occupied = True
                                break
                    except Exception:
                        pass
                if occupied:
                    continue
                dist = pos.distance_squared(bpos)
                if dist < best_bdist:
                    best_bdist = dist
                    best_bridge = bpos
            except Exception:
                continue

        if best_bridge is not None:
            preferred = pos.direction_to(best_bridge)
            self._try_move(c, preferred, ti)
            return

        # Priority 3: if on enemy building, self-destruct
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    bpos = c.get_position(bid)
                    if pos.x == bpos.x and pos.y == bpos.y:
                        c.self_destruct()
                        return
            except Exception:
                pass

        # Priority 4: wander randomly, always pave forward aggressively
        if self.scout_dir is None:
            self.scout_dir = random.choice(DIRS)

        if random.random() < 0.05:
            self.scout_dir = random.choice(DIRS)

        moved = self._raider_move(c, self.scout_dir, ti)
        if moved is not None:
            self.stuck_turns = 0
        else:
            self.stuck_turns += 1
            if self.stuck_turns > 2:
                self.scout_dir = random.choice(DIRS)
                self.stuck_turns = 0

    def _find_blocked_bridge_target(self, c):
        my_team = c.get_team()
        pos = c.get_position()
        best_pos = None
        best_dist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                target = c.get_bridge_target(bid)
                if not c.is_in_vision(target):
                    continue
                target_bid = c.get_tile_building_id(target)
                if target_bid is None:
                    continue
                if c.get_team(target_bid) != my_team:
                    dist = pos.distance_squared(target)
                    if dist < best_dist:
                        best_dist = dist
                        best_pos = target
            except Exception:
                continue
        return best_pos

    def _raider_move(self, c, preferred, ti):
        """Move preferring forward direction — pave road immediately rather than detour."""
        idx = DIRS.index(preferred) if preferred in DIRS else 0
        # Only try preferred + 1 neighbor each side
        order = [DIRS[(idx + o) % 8] for o in [0, 1, -1]]
        road_cost, _ = c.get_road_cost()

        for d in order:
            try:
                if c.can_move(d):
                    c.move(d)
                    return d
            except Exception:
                continue

        # Pave forward immediately
        if ti >= road_cost:
            for d in order:
                try:
                    next_pos = c.get_position().add(d)
                    if self._is_ore(c, next_pos):
                        continue
                    if c.can_build_road(next_pos):
                        c.build_road(next_pos)
                        if c.can_move(d):
                            c.move(d)
                            return d
                        return None
                except Exception:
                    continue
        return None

    def _try_move(self, c, preferred, ti):
        idx = DIRS.index(preferred) if preferred in DIRS else 0
        order = [DIRS[(idx + o) % 8] for o in [0, 1, -1, 2, -2, 3, -3, 4]]
        road_cost, _ = c.get_road_cost()

        for d in order:
            try:
                if c.can_move(d):
                    c.move(d)
                    return d
            except Exception:
                continue

        if ti >= road_cost:
            for d in order:
                try:
                    next_pos = c.get_position().add(d)
                    if self._is_ore(c, next_pos):
                        continue
                    if c.can_build_road(next_pos):
                        c.build_road(next_pos)
                        if c.can_move(d):
                            c.move(d)
                            return d
                        return None
                except Exception:
                    continue
        return None

    # ---- HELPERS ----
    def _redirect(self) -> None:
        if self.scout_dir is not None and self.scout_dir in DIRS:
            opp = self.scout_dir.opposite()
            options = [d for d in DIRS if d not in (self.scout_dir, opp)]
        else:
            options = list(DIRS)
        self.scout_dir = random.choice(options)
        self.stuck_turns = 0

    def _find_core(self, c):
        my_team = c.get_team()
        for eid in c.get_nearby_buildings():
            try:
                if c.get_team(eid) == my_team and c.get_hp(eid) == 500:
                    return c.get_position(eid)
            except Exception:
                continue
        return None

    def _try_bridge_from_here(self, c, pos, waypoints, current_idx) -> bool:
        my_team = c.get_team()
        for future_idx in range(current_idx + 1, len(waypoints) - 1):
            future_pos = waypoints[future_idx]
            for build_pos in [pos] + [pos.add(d) for d in DIRS]:
                if build_pos.distance_squared(pos) > 2:
                    continue
                if build_pos.distance_squared(future_pos) > 9:
                    continue
                if self._is_wall(c, build_pos) or self._is_ore(c, build_pos):
                    continue
                existing = c.get_tile_building_id(build_pos)
                if existing is not None:
                    try:
                        if c.get_team(existing) == my_team:
                            c.destroy(build_pos)
                        else:
                            continue
                    except Exception:
                        continue
                if c.can_build_bridge(build_pos, future_pos):
                    c.build_bridge(build_pos, future_pos)
                    self.chain_index = future_idx
                    self.chain_stuck = 0
                    return True
        return False

    def _find_bridge_start(self, c, harvester_pos, explorer_pos):
        if self.core_pos is None:
            return explorer_pos
        best = explorer_pos
        best_dist = 999999
        for d in CARDINALS:
            adj = harvester_pos.add(d)
            if self._is_wall(c, adj) or self._is_ore(c, adj):
                continue
            if explorer_pos.distance_squared(adj) > 2:
                continue
            dist = adj.distance_squared(self.core_pos)
            if dist < best_dist:
                best_dist = dist
                best = adj
        return best

    def _nudge_off_wall(self, c, wall_pos, from_pos):
        for d in DIRS:
            alt = wall_pos.add(d)
            if self._is_wall(c, alt) or self._is_ore(c, alt):
                continue
            if from_pos.distance_squared(alt) <= 9:
                return alt
        return None

    def _is_ore(self, c, p):
        try:
            return "ORE" in str(c.get_tile_env(p))
        except Exception:
            return False

    def _is_wall(self, c, p):
        try:
            return "WALL" in str(c.get_tile_env(p))
        except Exception:
            return False
