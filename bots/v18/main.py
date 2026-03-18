import random
from collections.abc import Callable

from cambc import (
    Controller,
    Direction,
    EntityType,
    Environment,
    GameConstants,
    Position,
)

DIRS = [d for d in Direction if d != Direction.CENTRE]

INITIAL_BUILDERS = 4
MAX_BUILDERS = 50
RESPAWN_INTERVAL = 20

SPOKES = [
    Direction.NORTH,
    Direction.NORTHEAST,
    Direction.EAST,
    Direction.SOUTHEAST,
    Direction.SOUTH,
    Direction.SOUTHWEST,
    Direction.WEST,
    Direction.NORTHWEST,
]

TAG_ID = 0 << 30
TAG_MASK = 0xC000_0000


def mk_id(n: int) -> int:
    return TAG_ID | (n & 0xFF)


def toward(a: Position, b: Position) -> Direction:
    return a.direction_to(b)


def ib(ct: Controller, p: Position) -> bool:
    return 0 <= p.x < ct.get_map_width() and 0 <= p.y < ct.get_map_height()


def wall(ct: Controller, p: Position) -> bool:
    return not ib(ct, p) or ct.get_tile_env(p) == Environment.WALL


def ore_env(ct: Controller, p: Position) -> bool:
    return ib(ct, p) and ct.get_tile_env(p) in (
        Environment.ORE_TITANIUM,
        Environment.ORE_AXIONITE,
    )


# --- Perception ---


class Percept:
    def __init__(self, ct: Controller, core: Position, enemy_core: Position) -> None:
        self.ct = ct
        self.pos = ct.get_position()
        self.core = core
        self.enemy_core = enemy_core
        self.my_team = ct.get_team()
        self.ti, self.ax = ct.get_global_resources()
        self.rnd = ct.get_current_round()
        self.dist_to_core = self.pos.distance_squared(core) if core else 999999
        self.dist_to_enemy = (
            self.pos.distance_squared(enemy_core) if enemy_core else 999999
        )

        self.adj_ore: Position | None = None
        self.nearest_ore: Position | None = None
        self.enemy_builder: Position | None = None
        self.enemy_infra: Position | None = None
        self.broken_chain: Position | None = None
        self.allied_conv_density = 0
        self.unexplored_dir: Direction | None = None
        self.nearby_harvesters = 0
        self.nearby_gunners = 0
        self.frontline_conveyor: Position | None = None
        self.has_defense_nearby = False

        self._scan(ct)

    def _scan(self, ct: Controller) -> None:
        pos = self.pos
        best_ore_d = 999999
        dir_density = {}

        for d in Direction:
            t = pos.add(d)
            if not ib(ct, t):
                continue
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None:
                self.adj_ore = t

        for t in ct.get_nearby_tiles():
            if ore_env(ct, t) and ct.get_tile_building_id(t) is None:
                d = pos.distance_squared(t)
                if d < best_ore_d:
                    best_ore_d = d
                    self.nearest_ore = t

            bid = ct.get_tile_building_id(t)
            if bid is not None and ct.get_team(bid) == self.my_team:
                et = ct.get_entity_type(bid)
                if et in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                    self.allied_conv_density += 1

                    d = ct.get_direction(bid)
                    dx, dy = d.delta()
                    out = Position(t.x + dx, t.y + dy)
                    if ib(ct, out) and ct.is_in_vision(out):
                        out_bid = ct.get_tile_building_id(out)
                        out_env = ct.get_tile_env(out)
                        if out_bid is None and out_env != Environment.WALL:
                            core_near = (
                                self.core
                                and abs(out.x - self.core.x) <= 1
                                and abs(out.y - self.core.y) <= 1
                            )
                            if not core_near:
                                self.broken_chain = out

                elif et == EntityType.HARVESTER:
                    self.nearby_harvesters += 1
                elif et == EntityType.GUNNER:
                    self.nearby_gunners += 1
                    self.has_defense_nearby = True

        if self.core and self.enemy_core and not self.has_defense_nearby:
            mid_x = (self.core.x + self.enemy_core.x) // 2
            mid_y = (self.core.y + self.enemy_core.y) // 2
            best_front_dist = 999999
            for t in ct.get_nearby_tiles():
                bid = ct.get_tile_building_id(t)
                if bid is None:
                    continue
                if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                    continue
                if ct.get_team(bid) != self.my_team:
                    continue
                dist_to_mid = (t.x - mid_x) ** 2 + (t.y - mid_y) ** 2
                dist_to_core = t.distance_squared(self.core)
                if dist_to_core > 25 and dist_to_mid < best_front_dist:
                    best_front_dist = dist_to_mid
                    self.frontline_conveyor = t

        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == self.my_team:
                continue
            et = ct.get_entity_type(eid)
            ep = ct.get_position(eid)
            d = pos.distance_squared(ep)

            if et == EntityType.BUILDER_BOT:
                if self.enemy_builder is None or d < pos.distance_squared(
                    self.enemy_builder,
                ):
                    self.enemy_builder = ep
            elif et in (
                EntityType.CONVEYOR,
                EntityType.HARVESTER,
                EntityType.ARMOURED_CONVEYOR,
            ) and (
                self.enemy_infra is None
                or d
                < pos.distance_squared(
                    self.enemy_infra,
                )
            ):
                self.enemy_infra = ep

        for d in DIRS:
            count = 0
            for r in range(1, 5):
                dx, dy = d.delta()
                check = Position(pos.x + dx * r, pos.y + dy * r)
                if not ib(ct, check) or not ct.is_in_vision(check):
                    continue
                bid = ct.get_tile_building_id(check)
                if bid is not None and ct.get_team(bid) == self.my_team:
                    count += 1
            dir_density[d] = count

        least_dense = sorted(DIRS, key=lambda d: dir_density.get(d, 0))
        self.unexplored_dir = least_dense[0]


# --- Movement ---


class BugNav:
    def __init__(self) -> None:
        self.lp = None
        self.stuck = 0
        self.wf = False
        self.ws = 1
        self.cl = 999999

    def reset(self) -> None:
        self.__init__()

    def go(
        self,
        ct: Controller,
        target: Position,
        step_fn: Callable[[Direction], bool],
    ) -> bool:
        pos = ct.get_position()
        d = toward(pos, target)
        dist = pos.distance_squared(target)

        if self.lp == (pos.x, pos.y):
            self.stuck += 1
        else:
            self.stuck = 0
        self.lp = (pos.x, pos.y)

        if self.stuck > 10:
            self.wf = False
            self.ws = -self.ws
            self.stuck = 0

        if not self.wf:
            if step_fn(d):
                self.cl = min(self.cl, dist)
                return True
            self.wf = True
            self.cl = dist

        scan = d
        for _ in range(8):
            if step_fn(scan):
                nd = ct.get_position().distance_squared(target)
                if nd < self.cl:
                    self.wf = False
                    self.cl = nd
                return True
            scan = scan.rotate_right() if self.ws == 1 else scan.rotate_left()
        return False


def step_conv(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if not ore_env(ct, nxt) and ct.can_build_conveyor(nxt, d.opposite()):
        ct.build_conveyor(nxt, d.opposite())
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


def step_road(ct: Controller, d: Direction) -> bool:
    nxt = ct.get_position().add(d)
    if wall(ct, nxt):
        return False
    if ct.can_build_road(nxt):
        ct.build_road(nxt)
    if ct.can_move(d):
        ct.move(d)
        return True
    return False


# --- Core ---


class CoreBot:
    def __init__(self) -> None:
        self.spawned = 0

    def run(self, ct: Controller) -> None:
        ti, _ = ct.get_global_resources()
        cost = ct.get_builder_bot_cost()[0]
        rnd = ct.get_current_round()
        core_pos = ct.get_position()

        if self.spawned >= MAX_BUILDERS:
            return

        harvester_cost = ct.get_harvester_cost()[0]

        if self.spawned < INITIAL_BUILDERS:
            if ti < cost + harvester_cost:
                return
        elif self.spawned < 8:
            if ti < cost + harvester_cost + 200:
                return
        elif ti < 1500 or rnd % RESPAWN_INTERVAL != 0:
            return

        spoke = self.spawned % len(SPOKES)
        sd = SPOKES[spoke]
        for d in [sd, sd.rotate_left(), sd.rotate_right(), *DIRS]:
            sp = core_pos.add(d)
            if ct.can_spawn(sp):
                ct.spawn_builder(sp)
                if ct.can_place_marker(sp):
                    ct.place_marker(sp, mk_id(self.spawned))
                self.spawned += 1
                return


# --- Builder: utility-based agent ---


class BuilderAgent:
    def __init__(self) -> None:
        self.core: Position | None = None
        self.enemy_core: Position | None = None
        self.nav = BugNav()
        self.target: Position | None = None
        self.target_type = ""
        self.visited_ore: set[tuple[int, int]] = set()
        self.last_action = ""
        self.init_done = False
        self.spoke_dir: Direction | None = None
        self.idle_turns = 0
        self.commitment = 0
        self.has_income = False
        self.last_ti = 0
        self.last_pos: Position | None = None
        self.stuck_turns = 0
        self.fortify_state = 0  # 0=not fortifying, 1=go to target, 2=destroy conv, 3=build splitter, 4=build sentinel
        self.fortify_conv_pos: Position | None = None
        self.fortify_conv_dir: Direction | None = None
        self.defenses_built = 0

    def _setup(self, ct: Controller) -> None:
        pos = ct.get_position()
        for eid in ct.get_nearby_entities():
            if (
                ct.get_entity_type(eid) == EntityType.CORE
                and ct.get_team(eid) == ct.get_team()
            ):
                self.core = ct.get_position(eid)
                break

        bid = ct.get_tile_building_id(pos)
        if (
            bid is not None
            and ct.get_entity_type(bid) == EntityType.MARKER
            and ct.get_team(bid) == ct.get_team()
        ):
            val = ct.get_marker_value(bid)
            if val & TAG_MASK == TAG_ID:
                sid = val & 0xFF
                if sid < len(SPOKES):
                    self.spoke_dir = SPOKES[sid]

        if self.spoke_dir is None:
            self.spoke_dir = random.choice(DIRS)

        if self.core:
            w, h = ct.get_map_width(), ct.get_map_height()
            self.enemy_core = Position(w - 1 - self.core.x, h - 1 - self.core.y)

        self.init_done = True

    def run(self, ct: Controller) -> None:
        if not self.init_done:
            self._setup(ct)

        if not self.core:
            return

        ti, _ = ct.get_global_resources()
        if not self.has_income and ti > self.last_ti:
            self.has_income = True
        self.last_ti = ti

        pos = ct.get_position()
        if self.last_pos and pos.x == self.last_pos.x and pos.y == self.last_pos.y:
            self.stuck_turns += 1
        else:
            self.stuck_turns = 0
        self.last_pos = pos

        if self.stuck_turns >= 5 and self.core:
            self.commitment = 0
            self.target = self.core
            self.target_type = "explore"
            self.nav.reset()
            self.stuck_turns = 0

        p = Percept(ct, self.core, self.enemy_core)

        # Always harvest if possible -- interrupt anything
        if p.adj_ore and (p.adj_ore.x, p.adj_ore.y) not in self.visited_ore:
            if p.ct.can_build_harvester(p.adj_ore):
                p.ct.build_harvester(p.adj_ore)
                self.visited_ore.add((p.adj_ore.x, p.adj_ore.y))
                self.idle_turns = 0
                self.commitment = 0
                self.target = None
                self.target_type = ""
            return  # wait here even if can't afford -- don't wander and waste scale

        # Fortify interrupt: if near frontline and conditions met, break commitment
        if (
            self.target_type != "fortify"
            and p.frontline_conveyor
            and not p.has_defense_nearby
            and self.defenses_built < 1
            and self.has_income
            and p.ti > 500
            and p.rnd > 200
            and p.pos.distance_squared(p.frontline_conveyor)
            <= GameConstants.ACTION_RADIUS_SQ
        ):
            self.commitment = 0

        # Recalculate only when not committed
        if self.commitment <= 0 or self.target is None:
            action, target = self._choose(p)
            if target != self.target or action != self.target_type:
                self.nav.reset()
                self.target = target
                self.target_type = action
                self.commitment = 15

        self.commitment -= 1
        self._execute(ct, p, self.target_type, self.target)

    def _prune_nearby(self, ct: Controller) -> None:
        my = ct.get_team()
        pos = ct.get_position()

        for tile in ct.get_nearby_tiles():
            if pos.distance_squared(tile) > GameConstants.ACTION_RADIUS_SQ:
                continue
            bid = ct.get_tile_building_id(tile)
            if bid is None:
                continue
            if ct.get_entity_type(bid) != EntityType.CONVEYOR:
                continue
            if ct.get_team(bid) != my:
                continue

            has_input = False
            adj_harvester = False
            not_fully_visible = False

            for d2 in DIRS:
                adj = tile.add(d2)
                if not ib(ct, adj):
                    continue
                if not ct.is_in_vision(adj):
                    not_fully_visible = True
                    continue
                abid = ct.get_tile_building_id(adj)
                if abid is None:
                    continue
                at = ct.get_entity_type(abid)
                if at == EntityType.HARVESTER and ct.get_team(abid) == my:
                    adj_harvester = True
                    break
                if (
                    at
                    in (
                        EntityType.CONVEYOR,
                        EntityType.SPLITTER,
                        EntityType.ARMOURED_CONVEYOR,
                    )
                    and ct.get_team(abid) == my
                ):
                    ad = ct.get_direction(abid)
                    adx, ady = ad.delta()
                    if adj.x + adx == tile.x and adj.y + ady == tile.y:
                        has_input = True
                        break

            if not_fully_visible or has_input or adj_harvester:
                continue

            if ct.can_destroy(tile):
                ct.destroy(tile)
                return

    def _choose(self, p: Percept) -> tuple[str, Position | None]:
        scores: list[tuple[float, str, Position | None]] = []

        # Ti trend: compare current Ti to 50 turns ago
        ti_falling = self.has_income and p.ti < self.last_ti - 50
        ti_healthy = p.ti > 500

        # Seek ore: always valuable
        if p.nearest_ore and (p.nearest_ore.x, p.nearest_ore.y) not in self.visited_ore:
            ore_dist = p.pos.distance_squared(p.nearest_ore)
            scores.append((800 - ore_dist * 0.1, "seek_ore", p.nearest_ore))

        # Explore: builds the network
        if p.unexplored_dir and self.core:
            w = p.ct.get_map_width()
            h = p.ct.get_map_height()
            dx, dy = p.unexplored_dir.delta()
            dist = random.randint(8, max(w, h) // 2)
            tx = max(1, min(w - 2, p.pos.x + dx * dist))
            ty = max(1, min(h - 2, p.pos.y + dy * dist))
            explore_target = Position(tx, ty)
            explore_score = 600 - p.allied_conv_density * 3
            scores.append((explore_score, "explore", explore_target))

        # Repair: urgent when income is falling, visible broken chain
        if p.broken_chain:
            repair_dist = p.pos.distance_squared(p.broken_chain)
            if repair_dist <= GameConstants.ACTION_RADIUS_SQ:
                scores.append((950, "repair", p.broken_chain))
            elif ti_falling:
                scores.append((700 - repair_dist * 0.3, "repair", p.broken_chain))
            elif ti_healthy:
                scores.append((300 - repair_dist * 0.5, "repair", p.broken_chain))

        # Fortify: build sentinel defense when economy is established
        if (
            p.frontline_conveyor
            and ti_healthy
            and p.ti > 500
            and not p.has_defense_nearby
            and self.defenses_built < 1
            and p.rnd > 200
        ):
            fort_dist = p.pos.distance_squared(p.frontline_conveyor)
            if fort_dist <= GameConstants.ACTION_RADIUS_SQ:
                scores.append((550, "fortify", p.frontline_conveyor))
            else:
                scores.append((350 - fort_dist * 0.1, "fortify", p.frontline_conveyor))

        # Raid: when we see enemy infra and we have income
        if p.enemy_infra and ti_healthy:
            infra_dist = p.pos.distance_squared(p.enemy_infra)
            if infra_dist == 0:
                scores.append((1000, "raid", p.enemy_infra))
            else:
                raid_score = 400 - infra_dist * 0.2
                scores.append((raid_score, "raid", p.enemy_infra))

        # Raid toward enemy core when no ore left to find
        if self.enemy_core and self.idle_turns > 30 and ti_healthy:
            scores.append((350, "raid_core", self.enemy_core))

        if not scores:
            return ("idle", None)

        scores.sort(key=lambda x: -x[0])
        return (scores[0][1], scores[0][2])

    def _execute(
        self,
        ct: Controller,
        p: Percept,
        action: str,
        target: Position | None,
    ) -> None:
        if action == "seek_ore" and target and self.core:
            self.idle_turns = 0
            self.nav.go(ct, target, lambda d: step_conv(ct, d))
            return

        if action == "repair" and target and self.core:
            self.idle_turns = 0
            pos = p.pos
            if pos.distance_squared(target) <= GameConstants.ACTION_RADIUS_SQ:
                best_dir = toward(target, self.core)
                if ct.can_build_conveyor(target, best_dir):
                    ct.build_conveyor(target, best_dir)
                    self.target = None
                    return
            self.nav.go(ct, target, lambda d: step_conv(ct, d))
            return

        if action == "fortify" and target and self.core and self.enemy_core:
            self.idle_turns = 0
            self._do_fortify(ct, p, target)
            return

        if action == "raid" and target:
            self.idle_turns = 0
            if p.pos.distance_squared(target) == 0:
                ct.self_destruct()
                return
            self.nav.go(ct, target, lambda d: step_road(ct, d))
            return

        if action == "raid_core" and target:
            self.idle_turns = 0
            if p.pos.distance_squared(target) <= 2:
                ct.self_destruct()
                return
            self.nav.go(ct, target, lambda d: step_road(ct, d))
            return

        if action == "explore" and target and self.core:
            moved = self.nav.go(ct, target, lambda d: step_conv(ct, d))
            if not moved:
                self.idle_turns += 1
            else:
                self.idle_turns = 0
            return

        self.idle_turns += 1

    def _do_fortify(self, ct: Controller, p: Percept, target: Position) -> None:
        pos = p.pos

        if self.fortify_state == 0:
            if pos.distance_squared(target) > GameConstants.ACTION_RADIUS_SQ:
                self.nav.go(ct, target, lambda d: step_conv(ct, d))
                return
            bid = ct.get_tile_building_id(target)
            if bid is None or ct.get_entity_type(bid) != EntityType.CONVEYOR:
                self.commitment = 0
                self.target = None
                return
            # Pre-check: is there space for a sentinel adjacent?
            has_space = False
            enemy_dir = (
                toward(target, self.enemy_core) if self.enemy_core else Direction.NORTH
            )
            for d in Direction:
                sp = target.add(d)
                if (
                    ib(ct, sp)
                    and ct.get_tile_building_id(sp) is None
                    and not wall(ct, sp)
                ):
                    has_space = True
                    break
            if not has_space:
                self.commitment = 0
                self.target = None
                return
            self.fortify_conv_pos = target
            self.fortify_conv_dir = ct.get_direction(bid)
            if ct.can_destroy(target):
                ct.destroy(target)
            self.fortify_state = 1
            self.commitment = 5
            return

        if self.fortify_state == 1:
            if (
                self.fortify_conv_pos
                and self.fortify_conv_dir
                and ct.can_build_splitter(self.fortify_conv_pos, self.fortify_conv_dir)
            ):
                ct.build_splitter(self.fortify_conv_pos, self.fortify_conv_dir)
                self.fortify_state = 2
                return
            # Failed -- rebuild conveyor
            if self.fortify_conv_pos and self.fortify_conv_dir:
                ct.can_build_conveyor(
                    self.fortify_conv_pos,
                    self.fortify_conv_dir,
                ) and ct.build_conveyor(self.fortify_conv_pos, self.fortify_conv_dir)
            self.fortify_state = 0
            self.commitment = 0
            self.target = None
            return

        if self.fortify_state == 2:
            if not self.fortify_conv_pos or not self.enemy_core:
                self.fortify_state = 0
                self.commitment = 0
                return
            enemy_dir = toward(self.fortify_conv_pos, self.enemy_core)
            for d in Direction:
                sentinel_pos = self.fortify_conv_pos.add(d)
                if ct.can_build_sentinel(sentinel_pos, enemy_dir):
                    ct.build_sentinel(sentinel_pos, enemy_dir)
                    self.fortify_state = 0
                    self.commitment = 0
                    self.target = None
                    return
            # Failed -- leave splitter in place (still routes resources)
            self.fortify_state = 0
            self.commitment = 0
            self.target = None


# --- Turret ---


class TurretUnit:
    def run(self, ct: Controller) -> None:
        my = ct.get_team()
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) != my:
                epos = ct.get_position(eid)
                if ct.can_fire(epos):
                    ct.fire(epos)
                    return


# --- Player ---


class Player:
    def __init__(self) -> None:
        self.core_bot = CoreBot()
        self.builder = BuilderAgent()
        self.turret = TurretUnit()

    def run(self, ct: Controller) -> None:
        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core_bot.run(ct)
        elif etype == EntityType.BUILDER_BOT:
            self.builder.run(ct)
        elif etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            self.turret.run(ct)
