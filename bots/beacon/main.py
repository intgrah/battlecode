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
    def __init__(self):
        self.num_spawned = 0
        self.scout_dir = None
        self.stuck_turns = 0
        self.role = None
        self.core_pos = None
        self.turns_alive = 0
        # Chaining state
        self.chain_waypoints = None
        self.chain_index = 0
        self.chain_stuck = 0  # turns stuck on current waypoint
        self.chain_turns = 0  # total turns spent chaining
        # Repair state
        self.repair_pos = None  # where to build the patch bridge
        self.repair_from = None  # the hanging bridge's position (for context)
        self.repair_turns = 0  # timeout counter

    def run(self, c):
        etype = str(c.get_entity_type())
        if "CORE" in etype:
            self.run_core(c)
        elif "BUILDER" in etype:
            self.run_builder(c)

    # ---- CORE ----
    def run_core(self, c):
        ti, _ = c.get_global_resources()
        cost, _ = c.get_builder_bot_cost()
        rnd = c.get_current_round()

        if rnd <= 300:
            if self.num_spawned >= NUM_EXPLORERS:
                return
            if ti >= cost + 80:
                self._spawn(c)
        elif ti >= cost + 50:
            self._spawn(c)

    def _spawn(self, c):
        cp = c.get_position()
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                sp = Position(cp.x + dx, cp.y + dy)
                if c.can_spawn(sp):
                    c.spawn_builder(sp)
                    self.num_spawned += 1
                    return

    # ---- BUILDER ----
    def run_builder(self, c):
        self.turns_alive += 1

        if self.role is None:
            if c.get_current_round() <= 300:
                self.role = "explorer"
            else:
                self.role = "raider"
            self.core_pos = self._find_core(c)

        if self.role == "explorer":
            self._run_explorer(c)
        elif self.role == "chaining":
            self._run_chainer(c)
        elif self.role == "repairing":
            self._run_repairer(c)
        else:
            self._run_raider(c)

    # ---- EXPLORER ----
    def _run_explorer(self, c):
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        rnd = c.get_current_round()

        # Check for disconnected harvesters (no adjacent bridge) and reconnect them
        disconnected = self._find_disconnected_harvester(c)
        if disconnected is not None:
            harv_pos, build_pos = disconnected
            self.repair_pos = build_pos
            self.repair_from = harv_pos
            self.repair_turns = 0
            self.role = "repairing"
            self._run_repairer(c)
            return

        # Check for hanging bridges (broken chains) and repair them
        hanging = self._find_hanging_bridge(c)
        if hanging is not None:
            bridge_pos, gap_pos = hanging
            self.repair_pos = gap_pos
            self.repair_from = bridge_pos
            self.repair_turns = 0
            self.role = "repairing"
            self._run_repairer(c)
            return

        # Build harvester on any adjacent ore (all 8 directions)
        for d in DIRS:
            adj = pos.add(d)
            try:
                if self._is_ore(c, adj) and c.get_tile_building_id(adj) is None:
                    h_cost, _ = c.get_harvester_cost()
                    if ti >= h_cost and c.can_build_harvester(adj):
                        c.build_harvester(adj)
                        # First bridge must be cardinal-adjacent to harvester for resource pickup
                        bridge_start = self._find_bridge_start(c, adj, pos)
                        self._start_chain(c, bridge_start)
                        return
                    return
            except Exception:
                pass

        # Scan vision for unharvested ore — beeline toward it
        best_ore = None
        best_dist = 999
        for tile in c.get_nearby_tiles():
            try:
                if self._is_ore(c, tile) and c.get_tile_building_id(tile) is None:
                    dist = (pos.x - tile.x) ** 2 + (pos.y - tile.y) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best_ore = tile
            except Exception:
                pass

        if best_ore is not None:
            self.scout_dir = pos.direction_to(best_ore)

        self._explore(c)

    def _explore(self, c):
        """Walk outward laying roads, navigating around walls."""
        pos = c.get_position()
        ti, _ = c.get_global_resources()

        if self.scout_dir is None:
            self.scout_dir = DIRS[c.get_id() % 8]

        next_pos = pos.add(self.scout_dir)

        try:
            # Don't walk onto ore — stop so _run_explorer can build harvester next turn
            if self._is_ore(c, next_pos):
                return

            bid = c.get_tile_building_id(next_pos)
            road_cost, _ = c.get_road_cost()

            # Try to build road and move in scout_dir
            if bid is None:
                if ti >= road_cost and c.can_build_road(next_pos):
                    c.build_road(next_pos)
                elif not c.can_build_road(next_pos):
                    # Wall or obstacle — navigate around it
                    self.stuck_turns += 1
                    if self.stuck_turns > 4:
                        self._redirect()
                    else:
                        self._try_move(c, self.scout_dir, ti)
                    return
                else:
                    return  # No titanium

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

    # ---- BRIDGE CHAIN BUILDING ----
    def _start_chain(self, c, builder_pos):
        """Initialize bridge chain from builder_pos back to core."""
        if self.core_pos is None:
            return
        core_adj = self._nearest_core_adj(builder_pos)
        self.chain_waypoints = self._calc_chain(c, builder_pos, core_adj)
        self.chain_index = 0
        self.chain_stuck = 0
        self.chain_turns = 0
        self.role = "chaining"

    def _nearest_core_adj(self, pos):
        """Return the cardinal-adjacent tile to core closest to pos."""
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
        """Return waypoints from start toward core_adj, each within bridge range (dist_sq<=9).
        Bridges at waypoints[0..n-2], conveyor at waypoints[-1] (core_adj).
        Skips wall tiles by nudging waypoints to adjacent non-wall positions."""
        waypoints = [Position(start.x, start.y)]
        cx, cy = start.x, start.y
        max_iter = 50  # safety limit
        while max_iter > 0:
            max_iter -= 1
            dx = core_adj.x - cx
            dy = core_adj.y - cy
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 9:
                break
            chebyshev = max(abs(dx), abs(dy), 1)
            # Try step=3 first (gives dist_sq<=9 for cardinal), fallback to 2
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
            # If candidate is a wall or ore, try nudging to adjacent non-wall tiles
            if self._is_wall(c, candidate) or self._is_ore(c, candidate):
                found = False
                prev = Position(cx, cy)
                for d in DIRS:
                    alt = candidate.add(d)
                    if self._is_wall(c, alt) or self._is_ore(c, alt):
                        continue
                    # Must still be within bridge range of previous waypoint
                    if prev.distance_squared(alt) > 9:
                        continue
                    nx, ny = alt.x, alt.y
                    found = True
                    break
                if not found:
                    # Skip this step, try smaller step
                    cx += 1 if dx > 0 else -1 if dx < 0 else 0
                    cy += 1 if dy > 0 else -1 if dy < 0 else 0
                    continue
            cx, cy = nx, ny
            waypoints.append(Position(cx, cy))
        waypoints.append(core_adj)
        return waypoints

    def _run_chainer(self, c):
        """Walk toward core building bridges at each waypoint."""
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        self.chain_turns += 1

        if (
            self.chain_waypoints is None
            or self.chain_index >= len(self.chain_waypoints)
            or self.chain_turns > 80
        ):
            self.role = "explorer"
            self.chain_waypoints = None
            self.scout_dir = random.choice(CARDINALS)
            return

        idx = self.chain_index
        waypoints = self.chain_waypoints
        target = waypoints[idx]

        # Last waypoint: build conveyor pointing into core
        if idx == len(waypoints) - 1:
            dist_sq = pos.distance_squared(target)
            if dist_sq <= 2:
                self._build_core_conveyor(c, target)
                self.role = "explorer"
                self.chain_waypoints = None
                return
            self.chain_stuck += 1
            if self.chain_stuck > 15:
                self.role = "explorer"
                self.chain_waypoints = None
                self.scout_dir = random.choice(CARDINALS)
                return
            preferred = pos.direction_to(target)
            # Pave directly toward core
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

        # Bridge waypoint: build bridge targeting next waypoint
        next_target = waypoints[idx + 1]

        # If stuck, try to bridge from CURRENT position to any reachable future waypoint
        if self.chain_stuck > 3:
            bridge_cost, _ = c.get_bridge_cost()
            if ti >= bridge_cost:
                if self._try_bridge_from_here(c, pos, waypoints, idx):
                    return
            # If bridging failed, recalculate remaining chain from current position
            if self.chain_stuck > 6:
                core_adj = waypoints[-1]  # preserve the core-adjacent target
                new_chain = self._calc_chain(c, pos, core_adj)
                self.chain_waypoints = new_chain
                self.chain_index = 0
                self.chain_stuck = 0
                return

        # Check if target or next_target is a wall — nudge if needed
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

            # Clear existing allied building at target
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

            # Fallback: try adjacent tiles within bridge range of next target
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

            # Can't build here, skip
            self.chain_index += 1
            self.chain_stuck = 0
            return

        # Walk toward waypoint — pave road directly toward target
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
                    if bid is None:
                        if c.can_build_road(nxt):
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

    def _build_core_conveyor(self, c, conv_pos):
        """Build a conveyor at conv_pos pointing into core."""
        if self.core_pos is None:
            return

        existing = c.get_tile_building_id(conv_pos)
        if existing is not None:
            try:
                team = c.get_team(existing)
                if team == c.get_team():
                    hp = c.get_hp(existing)
                    if hp == 20:  # Already a conveyor or bridge — good enough
                        return
                    c.destroy(conv_pos)
                else:
                    return  # Enemy building, can't do anything
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
        """Find a friendly harvester with no adjacent bridge/conveyor.
        Returns (harvester_pos, best_build_pos) or None."""
        my_team = c.get_team()
        pos = c.get_position()
        if self.core_pos is None:
            return None
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                if c.get_hp(bid) != 30:  # harvester HP
                    continue
                harv_pos = c.get_position(bid)
                # Only bother if we're nearby (within ~5 tiles)
                if pos.distance_squared(harv_pos) > 25:
                    continue
                # Check if any cardinal-adjacent tile has a bridge or conveyor
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
                # Found a disconnected harvester — pick the best adjacent tile to build on
                # Prefer the tile closest to core that isn't a wall/ore
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
        """Find a nearby friendly bridge whose target tile has no building (broken chain).
        Only returns gaps that are non-wall and close to this unit.
        Returns (bridge_pos, gap_pos) or None."""
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
                # Skip if gap is a wall or ore — can't build there
                if self._is_wall(c, target) or self._is_ore(c, target):
                    continue
                target_bid = c.get_tile_building_id(target)
                if target_bid is None:
                    gap_dist = pos.distance_squared(target)
                    # Only repair if we're reasonably close (within ~6 tiles)
                    if gap_dist <= 36 and gap_dist < best_dist:
                        best_dist = gap_dist
                        best = (c.get_position(bid), target)
            except Exception:
                continue
        return best

    def _find_repair_target(self, c, gap_pos):
        """Find the best target for a patch bridge at gap_pos.
        Prefers an existing friendly bridge/conveyor closer to core within bridge range.
        Falls back to a position ~2 tiles closer to core."""
        if self.core_pos is None:
            return None
        my_team = c.get_team()
        gap_to_core = gap_pos.distance_squared(self.core_pos)

        # Look for existing friendly bridge/conveyor closer to core within bridge range
        best_bid_pos = None
        best_dist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                hp = c.get_hp(bid)
                if hp != 20:  # bridge or conveyor
                    continue
                bpos = c.get_position(bid)
                # Must be closer to core than the gap
                if bpos.distance_squared(self.core_pos) >= gap_to_core:
                    continue
                # Must be within bridge range of gap_pos
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

        # Fallback: step ~2 tiles toward core, avoiding walls
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
        # Try all directions within bridge range
        for d in DIRS:
            candidate = gap_pos.add(d)
            if candidate.distance_squared(self.core_pos) < gap_pos.distance_squared(
                self.core_pos,
            ):
                if not self._is_wall(c, candidate) and not self._is_ore(c, candidate):
                    return candidate
        return None

    def _run_repairer(self, c):
        """Walk to the gap position and build a patch bridge."""
        pos = c.get_position()
        ti, _ = c.get_global_resources()
        self.repair_turns += 1

        if self.repair_pos is None or self.repair_turns > 20:
            self.role = "explorer"
            self.repair_pos = None
            self.repair_turns = 0
            return

        # Bail if gap is a wall or ore — can't build there
        if self._is_wall(c, self.repair_pos) or self._is_ore(c, self.repair_pos):
            self.role = "explorer"
            self.repair_pos = None
            return

        dist_sq = pos.distance_squared(self.repair_pos)

        if dist_sq <= 2:
            # We're adjacent — find target and build bridge
            bridge_target = self._find_repair_target(c, self.repair_pos)
            if bridge_target is None:
                self.role = "explorer"
                self.repair_pos = None
                return

            bridge_cost, _ = c.get_bridge_cost()
            if ti < bridge_cost:
                return  # Wait for resources

            # Clear existing allied building at repair_pos
            existing = c.get_tile_building_id(self.repair_pos)
            if existing is not None:
                try:
                    if c.get_team(existing) == c.get_team():
                        c.destroy(self.repair_pos)
                    else:
                        # Enemy building in the gap — can't repair here
                        self.role = "explorer"
                        self.repair_pos = None
                        return
                except Exception:
                    pass

            if c.can_build_bridge(self.repair_pos, bridge_target):
                c.build_bridge(self.repair_pos, bridge_target)
                # Check if the new bridge's target is also a gap (chain still broken)
                target_bid = c.get_tile_building_id(bridge_target)
                if (
                    target_bid is None
                    and bridge_target.distance_squared(self.core_pos) > 4
                ):
                    # Chain still broken further down — continue repairing
                    self.repair_from = self.repair_pos
                    self.repair_pos = bridge_target
                    return
                self.role = "explorer"
                self.repair_pos = None
                return
            # Can't build here, give up
            self.role = "explorer"
            self.repair_pos = None
            return

        # Walk toward gap
        preferred = pos.direction_to(self.repair_pos)
        self._try_move(c, preferred, ti)

    # ---- RAIDER (mid game) ----
    def _run_raider(self, c):
        pos = c.get_position()
        my_team = c.get_team()
        ti, _ = c.get_global_resources()

        # TOP PRIORITY: clear enemy buildings blocking friendly bridge targets
        blocked_target = self._find_blocked_bridge_target(c)
        if blocked_target is not None:
            if pos.x == blocked_target.x and pos.y == blocked_target.y:
                c.self_destruct()
                return
            preferred = pos.direction_to(blocked_target)
            self._try_move(c, preferred, ti)
            return

        enemy_harvesters = []
        enemy_transport = {}  # conveyors and bridges (both HP 20)
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    hp = c.get_hp(bid)
                    bpos = c.get_position(bid)
                    if hp == 30:  # harvester
                        enemy_harvesters.append(bpos)
                    elif hp == 20:  # conveyor or bridge
                        enemy_transport[bid] = bpos
            except Exception:
                pass

        best_pos = None
        best_dist = 999
        if self.turns_alive <= 150:
            for conv_id, conv_pos in enemy_transport.items():
                for h_pos in enemy_harvesters:
                    dx = abs(conv_pos.x - h_pos.x)
                    dy = abs(conv_pos.y - h_pos.y)
                    if dx <= 1 and dy <= 1 and dx + dy == 1:
                        dist = (pos.x - conv_pos.x) ** 2 + (pos.y - conv_pos.y) ** 2
                        if dist < best_dist:
                            best_dist = dist
                            best_pos = conv_pos
        else:
            for conv_id, conv_pos in enemy_transport.items():
                dist = (pos.x - conv_pos.x) ** 2 + (pos.y - conv_pos.y) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_pos = conv_pos

        if best_pos is not None:
            if pos.x == best_pos.x and pos.y == best_pos.y:
                c.self_destruct()
                return
            preferred = pos.direction_to(best_pos)
            self._try_move(c, preferred, ti)
            return

        # No target found — disperse randomly to search
        if self.scout_dir is None:
            self.scout_dir = random.choice(DIRS)

        if random.random() < 0.1:
            self.scout_dir = random.choice(DIRS)

        moved_dir = self._try_move(c, self.scout_dir, ti)
        if moved_dir is not None:
            self.scout_dir = moved_dir
            self.stuck_turns = 0
        else:
            self.stuck_turns += 1
            self.scout_dir = DIRS[(DIRS.index(self.scout_dir) + 1) % 8]

    def _find_blocked_bridge_target(self, c):
        """Find a friendly bridge whose target has an enemy building on it.
        Returns the blocked position to suicide onto, or None."""
        my_team = c.get_team()
        pos = c.get_position()
        best_pos = None
        best_dist = 999999
        for bid in c.get_nearby_buildings():
            try:
                if c.get_team(bid) != my_team:
                    continue
                # Check if it's a bridge
                target = c.get_bridge_target(bid)
                if not c.is_in_vision(target):
                    continue
                target_bid = c.get_tile_building_id(target)
                if target_bid is None:
                    continue
                # There's a building at the target — is it enemy?
                if c.get_team(target_bid) != my_team:
                    dist = pos.distance_squared(target)
                    if dist < best_dist:
                        best_dist = dist
                        best_pos = target
            except Exception:
                continue
        return best_pos

    def _try_move(self, c, preferred, ti):
        """Try preferred direction first, then adjacent, then rest.
        Returns the direction moved, or None if stuck."""
        idx = DIRS.index(preferred) if preferred in DIRS else 0
        order = [DIRS[(idx + o) % 8] for o in [0, 1, -1, 2, -2, 3, -3, 4]]
        road_cost, _ = c.get_road_cost()

        # Pass 1: use existing walkable surfaces
        for d in order:
            try:
                if c.can_move(d):
                    c.move(d)
                    return d
            except Exception:
                continue

        # Pass 2: pave one road
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
    def _redirect(self):
        if self.scout_dir is not None and self.scout_dir in DIRS:
            opp = self.scout_dir.opposite()
            options = [d for d in DIRS if d != self.scout_dir and d != opp]
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

    def _try_bridge_from_here(self, c, pos, waypoints, current_idx):
        """When stuck, try to build a bridge from current position to any future waypoint.
        Bridges teleport over walls so the chainer doesn't need to walk there.
        Returns True if a bridge was built."""
        my_team = c.get_team()
        # Try each future waypoint (skip the last one which is a conveyor)
        for future_idx in range(current_idx + 1, len(waypoints) - 1):
            future_pos = waypoints[future_idx]
            # Check if we can build a bridge from pos (or adjacent) targeting future_pos
            # Bridge target must be within BRIDGE_TARGET_RADIUS_SQ=9
            # Also check the target after future_pos to chain properly
            if future_idx + 1 < len(waypoints):
                chain_target = waypoints[future_idx + 1]
            else:
                chain_target = waypoints[-1]  # core adj

            # Try building at pos targeting future_pos
            for build_pos in [pos] + [pos.add(d) for d in DIRS]:
                if build_pos.distance_squared(pos) > 2:
                    continue
                if build_pos.distance_squared(future_pos) > 9:
                    continue
                if self._is_wall(c, build_pos) or self._is_ore(c, build_pos):
                    continue
                # Clear allied building if needed
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
        """Find the best cardinal-adjacent tile to the harvester for the first bridge.
        Prefers the tile closest to core. Falls back to explorer's position."""
        if self.core_pos is None:
            return explorer_pos
        best = explorer_pos
        best_dist = 999999
        for d in CARDINALS:
            adj = harvester_pos.add(d)
            if self._is_wall(c, adj) or self._is_ore(c, adj):
                continue
            # Must be within action range of explorer to build
            if explorer_pos.distance_squared(adj) > 2:
                continue
            dist = adj.distance_squared(self.core_pos)
            if dist < best_dist:
                best_dist = dist
                best = adj
        return best

    def _nudge_off_wall(self, c, wall_pos, from_pos):
        """Find a non-wall tile adjacent to wall_pos that's within bridge range of from_pos."""
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
            return False  # Out of vision — assume not a wall, handle at build time
