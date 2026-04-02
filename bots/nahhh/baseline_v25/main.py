"""Titanium economy bot.

Every unit (core and builders) runs the same Player instance. The core
spawns builders; builders find ore, build harvesters, and connect them back
to core via bridge/conveyor chains.  Connect-back routes around bare ore
tiles so future harvesters aren't blocked.

Econ builder state machine (role="ti"):
  1. SEEK_ORE        — pick nearest unclaimed Ti ore and walk to it
  2. BUILD_HARVESTER — adjacent to ore, build harvester
  3. CONNECT_BACK    — lay conveyor chain from harvester back to core/tree
  4. EXPLORE         — no visible ore, wander to discover new deposits

Aggro builder state machine (role="aggro", spawned first):
  1. ADVANCE         — walk toward enemy core (map centre until inferred)
  2. BUILD_HARVESTER — build harvester on Ti ore found in enemy territory
  3. BUILD_SENTINEL  — place sentinel adjacent to harvester
  4. (repeat)
"""

from __future__ import annotations

import random

from astar import astar_chain, astar_walk
from cambc import Controller, Direction, EntityType, Environment, Position
from constants import (
    ALL_DIRECTIONS,
    BRIDGE_MAX_DIST_SQ,
    CARDINALS,
    DELTA_TO_DIRECTION,
    DIRECTION_DELTA,
    SECTOR_CLAIM_TTL,
    SECTOR_OFFSETS,
    WALKABLE_BUILDINGS,
    dbg,
)
from markers import (
    OPCODE_SECTOR,
    decode_sector,
    encode_sector,
)

MAX_BUILDERS = 5
CONNECT_STALL_LIMIT = 40
MAX_HARVESTERS_PER_TREE = 4

# Aggro builder is spawned first at this offset from core centre.
# Spawn offsets per role (relative to core centre).
AGGRO_SPAWN_OFFSET = (0, -1)  # north
HEALER_SPAWN_OFFSET = (0, 1)  # south

# Max squared connection distance from nearest tree node / core when picking ore.
# Prevents claiming ores that would require extremely long chains.
MAX_ORE_CONNECT_DIST_SQ = 900  # 30 tiles

# Peripheral ore slippage: econ builders push past midline for ores far from
# both cores. Tolerance = min(d_own, d_enemy) * SLIPPAGE.  0.3 ≈ allows ~17%
# past midline for equidistant ores, blocks deep enemy territory.
OWN_SIDE_SLIPPAGE = 0.3

# Aggro scout orbit radius around enemy core (tiles).
AGGRO_ORBIT_RADIUS = 8


class Player:
    def __init__(self) -> None:
        self.round_no = 0
        self.my_pos: Position | None = None
        self.my_id: int | None = None
        self.my_team = None

        # Core state
        self.core_pos: Position | None = None
        self.core_tiles: set[Position] = set()
        self.enemy_core_pos: Position | None = None
        # Map symmetry: three candidate enemy core positions (x-flip, y-flip, 180).
        self.enemy_core_candidates: list[Position] = []
        self.symmetry_eliminated: list[bool] = [False, False, False]
        self.num_spawned = 0
        self.aggro_spawned: bool = False  # whether the aggro builder has been spawned
        self.healers_spawned: int = 0
        self.last_healer_spawn_round: int = -999

        # Map (persists across rounds)
        self.map_w: int | None = None
        self.map_h: int | None = None
        self.tile_env: dict[Position, Environment] = {}
        self.known_ores: set[Position] = set()  # Ti ore positions
        self.claimed_ores: set[Position] = set()
        # Persistent building memory — updated from vision, never cleared.
        # Used by _build_chain_cache so A* doesn't route through other builders' chains.
        self.known_buildings: dict[Position, tuple[int, EntityType, object]] = {}

        # Vision (rebuilt each turn)
        self.visible_buildings: dict[Position, tuple[int, EntityType, object]] = {}
        self.visible_allies: dict[int, Position] = {}
        self.visible_ally_positions: set[Position] = set()
        self.visible_unit_positions: set[Position] = set()  # all units excl. self

        # Builder role (set once on first _run_builder call via spawn-tile check)
        self.role: str = "ti"  # "ti" or "aggro"
        self.role_set: bool = False

        # Builder state (shared by both roles)
        self.target_ore: Position | None = None
        self.explore_target: Position | None = None
        # Walk cache (rebuilt once per turn for A* walk)
        self._walk_cache_round: int = -1
        self._wc_walls: set[tuple[int, int]] = set()
        self._wc_blocked: set[tuple[int, int]] = set()
        self._wc_known: set[tuple[int, int]] = set()
        self._wc_units: set[tuple[int, int]] = set()
        self._wc_enemy_core: set[tuple[int, int]] = set()

        # Tree state (persists across connect-backs)
        self.my_tree: set[Position] = set()
        self.tree_ids: dict[Position, int] = {}  # node → tree index
        self.tree_harvester_counts: list[int] = []  # harvester count per tree

        # Healing state
        self.healing = False
        self.heal_target: Position | None = None
        self.damaged_turns: dict[
            Position,
            int,
        ] = {}  # pos → turns seen with 1-3 HP missing

        # Connect-back state
        self.connecting = False
        self.connect_turns = 0
        self.connect_harvester_pos: Position | None = None
        self.chain_end: Position | None = None
        self.connect_target: Position | None = None
        self.connect_last_build_round: int = 0
        self.connect_stall_recoverable: bool = False
        self.current_chain: list[Position] = []
        # A* chain plan
        self.connect_plan: list[tuple[str, int, int, int, int]] | None = None
        self.connect_plan_idx: int = 0
        # Attack sub-state: enemy building we're walking to and firing at.
        self.connect_attack_pos: Position | None = None

        # Aggro builder state
        self.aggro_sentinel_pos: Position | None = None  # pending sentinel placement
        self.aggro_harvester_pos: Position | None = (
            None  # harvester this sentinel feeds
        )
        self.aggro_sentinel_turns: int = 0  # timeout for sentinel placement
        self.aggro_failed_targets: set[Position] = (
            set()
        )  # harvesters we failed to sentinel
        self.aggro_orbit_step: int = 0  # scout orbit angle index
        self._rng_seeded: bool = False

        # Sector-based exploration (Ti builders)
        self.sector_index: int = -1  # -1 = unclaimed
        self.explore_radius_step: int = 0
        self.sector_claims: dict[
            int,
            tuple[int, int],
        ] = {}  # sector → (owner_id, round)

    def run(self, ct: Controller) -> None:
        self._init_round(ct)
        if ct.get_entity_type() == EntityType.CORE and self.my_pos is not None:
            self.core_pos = self.my_pos
        self._scan(ct)

        etype = ct.get_entity_type()
        if etype == EntityType.CORE:
            self.core_pos = self.my_pos
            if not self.core_tiles:
                cx, cy = self.my_pos.x, self.my_pos.y
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        self.core_tiles.add(Position(cx + dx, cy + dy))
            self._run_core(ct)
        elif etype == EntityType.SENTINEL:
            self._run_sentinel(ct)
        elif etype == EntityType.BUILDER_BOT:
            self._detect_role(ct)
            if self.role == "aggro":
                self._run_aggro_builder(ct)
            elif self.role == "healer":
                self._run_healer(ct)
            else:
                self._run_builder(ct)

    # ------------------------------------------------------------------
    # Per-round init
    # ------------------------------------------------------------------

    def _init_round(self, ct: Controller) -> None:
        self.round_no = ct.get_current_round()
        self.my_pos = ct.get_position()
        self.my_id = ct.get_id()
        self.my_team = ct.get_team()
        if not self._rng_seeded:
            random.seed(self.my_id)
            self._rng_seeded = True

        if self.map_w is None:
            self.map_w = ct.get_map_width()
            self.map_h = ct.get_map_height()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def _scan(self, ct: Controller) -> None:
        self.visible_buildings.clear()
        self.visible_allies.clear()
        self.visible_ally_positions.clear()
        self.visible_unit_positions.clear()

        for pos in ct.get_nearby_tiles():
            env = self.tile_env.get(pos)
            if env is None:
                env = ct.get_tile_env(pos)
                self.tile_env[pos] = env
            self._check_symmetry(pos, env)
            if env == Environment.ORE_TITANIUM:
                self.known_ores.add(pos)

        for eid in ct.get_nearby_units():
            pos = ct.get_position(eid)
            team = ct.get_team(eid)
            if eid != self.my_id:
                self.visible_unit_positions.add(pos)
            if team == self.my_team and eid != self.my_id:
                self.visible_allies[eid] = pos
                self.visible_ally_positions.add(pos)

        visible_building_positions: set[Position] = set()
        for eid in ct.get_nearby_buildings():
            pos = ct.get_position(eid)
            etype = ct.get_entity_type(eid)
            team = ct.get_team(eid)
            entry = (eid, etype, team)
            self.visible_buildings[pos] = entry
            self.known_buildings[pos] = entry
            visible_building_positions.add(pos)
            if etype == EntityType.CORE:
                if team == self.my_team:
                    self.core_pos = pos
                else:
                    self.enemy_core_pos = pos

        # Clear stale known_buildings for visible tiles that no longer have buildings.
        for pos in ct.get_nearby_tiles():
            if pos not in visible_building_positions:
                self.known_buildings.pop(pos, None)

        self._init_symmetry()
        self._maybe_finalize_symmetry()

    def _init_symmetry(self) -> None:
        """Once core_pos and map size are known, seed the three mirrored core candidates."""
        if self.enemy_core_candidates or self.core_pos is None:
            return
        if self.map_w is None or self.map_h is None:
            return
        cx, cy = self.core_pos.x, self.core_pos.y
        w, h = self.map_w, self.map_h
        self.enemy_core_candidates = [
            Position(cx, h - 1 - cy),  # y-flip
            Position(w - 1 - cx, cy),  # x-flip
            Position(w - 1 - cx, h - 1 - cy),  # 180°
        ]
        # Immediately eliminate candidates that overlap our own core.
        for i, cand in enumerate(self.enemy_core_candidates):
            if cand.distance_squared(self.core_pos) <= 2:
                self.symmetry_eliminated[i] = True
                dbg(
                    f"r={self.round_no} id={self.my_id} symmetry {i} eliminated: overlaps own core at {cand}",
                )
        for p, e in list(self.tile_env.items()):
            self._check_symmetry(p, e)

    def _check_symmetry(self, pos: Position, env: Environment) -> None:
        """Eliminate symmetries when this tile and its mirror disagree on terrain."""
        if not self.enemy_core_candidates or self.map_w is None or self.map_h is None:
            return
        w, h = self.map_w, self.map_h
        sym_positions = [
            Position(pos.x, h - 1 - pos.y),
            Position(w - 1 - pos.x, pos.y),
            Position(w - 1 - pos.x, h - 1 - pos.y),
        ]
        for i, sym_pos in enumerate(sym_positions):
            if self.symmetry_eliminated[i]:
                continue
            sym_env = self.tile_env.get(sym_pos)
            if sym_env is not None and sym_env != env:
                self.symmetry_eliminated[i] = True

    def _maybe_finalize_symmetry(self) -> None:
        """Set enemy_core_pos from inference when one symmetry remains (vision still overrides in _scan)."""
        if not self.enemy_core_candidates:
            return
        if self.enemy_core_pos is not None:
            return
        remaining = [i for i in range(3) if not self.symmetry_eliminated[i]]
        if len(remaining) == 1:
            idx = remaining[0]
            self.enemy_core_pos = self.enemy_core_candidates[idx]
            dbg(
                f"r={self.round_no} id={self.my_id} inferred enemy core at {self.enemy_core_pos} "
                f"(symmetry idx {idx})",
            )
        elif len(remaining) == 0:
            self.enemy_core_pos = self.enemy_core_candidates[2]
            dbg(
                f"r={self.round_no} id={self.my_id} symmetry exhausted; "
                f"fallback enemy core at {self.enemy_core_pos}",
            )

    # ------------------------------------------------------------------
    # Sentinel
    # ------------------------------------------------------------------

    def _run_sentinel(self, ct: Controller) -> None:
        """Fire at best visible enemy target.

        Priority: turrets > unprotected transport > unprotected core > bots > roads.
        Never shoot harvesters — they feed us ammo.
        Deprioritize targets with enemy bot on tile (bot shields building).
        """
        if ct.get_action_cooldown() != 0:
            return
        best: Position | None = None
        best_key: tuple[int, int, int] | None = None
        my_pos = ct.get_position()
        my_team = ct.get_team()
        for eid in ct.get_nearby_entities():
            if ct.get_team(eid) == my_team:
                continue
            etype = ct.get_entity_type(eid)
            if etype in (
                EntityType.SENTINEL,
                EntityType.GUNNER,
                EntityType.BREACH,
                EntityType.LAUNCHER,
            ):
                priority = 0
            elif etype in (
                EntityType.CONVEYOR,
                EntityType.BRIDGE,
                EntityType.SPLITTER,
                EntityType.ARMOURED_CONVEYOR,
            ):
                priority = 1
            elif etype == EntityType.CORE:
                priority = 2
            elif etype == EntityType.BUILDER_BOT:
                priority = 3
            elif etype == EntityType.ROAD:
                priority = 4
            else:
                continue  # harvesters, barriers, markers, etc.
            # Core is 3x3 — try all tiles, not just center.
            pos = ct.get_position(eid)
            targets = [pos]
            if etype == EntityType.CORE:
                targets = [
                    Position(pos.x + dx, pos.y + dy)
                    for dx in range(-1, 2)
                    for dy in range(-1, 2)
                ]
            for t in targets:
                if not ct.can_fire(t):
                    continue
                # Don't fire at tiles with friendly bots — turrets hit bots first.
                bot_id = ct.get_tile_builder_bot_id(t)
                if bot_id is not None:
                    bot_team = ct.get_team(bot_id)
                    if bot_team == my_team:
                        continue  # friendly fire
                    # Enemy bot on building tile — bot shields building, deprioritize.
                    protected = 1 if etype != EntityType.BUILDER_BOT else 0
                else:
                    protected = 0
                key = (priority, protected, my_pos.distance_squared(t))
                if best_key is None or key < best_key:
                    best = t
                    best_key = key
                break  # one fireable tile per entity is enough
        if best is not None:
            ct.fire(best)
            dbg(
                f"r={self.round_no} id={self.my_id} sentinel fire at {best} pri={best_key[0]}",
            )

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        # Count enemy bots visible near core.
        enemy_bots_nearby = 0
        for eid in ct.get_nearby_units():
            if ct.get_team(eid) != self.my_team:
                enemy_bots_nearby += 1

        # Spawn healers based on enemy bot presence: 1 healer per 2 enemy bots.
        # Max 3 healers. Minimum 10 turns between spawns.
        healers_needed = min(3, (enemy_bots_nearby + 1) // 2)
        need_healer = (
            self.num_spawned >= MAX_BUILDERS
            and self.healers_spawned < healers_needed
            and self.round_no - self.last_healer_spawn_round >= 10
        )

        if self.num_spawned >= MAX_BUILDERS and not need_healer:
            return

        titanium, _ = ct.get_global_resources()
        builder_cost = ct.get_builder_bot_cost()[0]
        harvester_cost = ct.get_harvester_cost()[0]
        conveyor_cost = ct.get_conveyor_cost()[0]

        if need_healer:
            # Healers just need to be affordable — no reserve needed.
            if titanium < builder_cost:
                return
        else:
            # Reserve enough for existing builders to keep building.
            per_builder_reserve = harvester_cost + conveyor_cost * 3
            reserve = per_builder_reserve * max(1, self.num_spawned)
            if titanium < builder_cost + reserve:
                return

        # Spawn aggro builder first at preferred north tile.
        if not self.aggro_spawned and self.core_pos is not None:
            dx, dy = AGGRO_SPAWN_OFFSET
            preferred = Position(self.core_pos.x + dx, self.core_pos.y + dy)
            if ct.can_spawn(preferred):
                ct.spawn_builder(preferred)
                self.num_spawned += 1
                self.aggro_spawned = True
                dbg(f"r={self.round_no} core spawn aggro #1 at {preferred}")
                return
            for direction in ALL_DIRECTIONS:
                spawn_pos = self.my_pos.add(direction)
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    self.num_spawned += 1
                    self.aggro_spawned = True
                    dbg(
                        f"r={self.round_no} core spawn aggro #1 (fallback) at {spawn_pos}",
                    )
                    return

        # Spawn healer at designated tile, or econ at any available tile.
        if need_healer and self.core_pos is not None:
            dx, dy = HEALER_SPAWN_OFFSET
            healer_tile = Position(self.core_pos.x + dx, self.core_pos.y + dy)
            if ct.can_spawn(healer_tile):
                ct.spawn_builder(healer_tile)
                self.num_spawned += 1
                self.healers_spawned += 1
                self.last_healer_spawn_round = self.round_no
                dbg(
                    f"r={self.round_no} core spawn healer #{self.healers_spawned} at {healer_tile}",
                )
                return

        for direction in ALL_DIRECTIONS:
            spawn_pos = self.my_pos.add(direction)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
                dbg(f"r={self.round_no} core spawn #{self.num_spawned} at {spawn_pos}")
                return

    # ------------------------------------------------------------------
    # Role detection
    # ------------------------------------------------------------------

    def _detect_role(self, ct: Controller) -> None:
        """Called once per builder on its first turn to set self.role.

        Role is determined by spawn position relative to core centre.
        """
        if self.role_set or self.core_pos is None or self.my_pos is None:
            return
        dx = self.my_pos.x - self.core_pos.x
        dy = self.my_pos.y - self.core_pos.y
        if (dx, dy) == AGGRO_SPAWN_OFFSET and self.round_no <= 1:
            self.role = "aggro"
        elif (dx, dy) == HEALER_SPAWN_OFFSET and self.round_no > 1:
            self.role = "healer"
        self.role_set = True
        dbg(f"r={self.round_no} id={self.my_id} role={self.role} spawn={self.my_pos}")

    # ------------------------------------------------------------------
    # Healer builder state machine
    # ------------------------------------------------------------------

    _HEALER_ORBIT_DIRS = [
        (0, -2),
        (2, -2),
        (2, 0),
        (2, 2),
        (0, 2),
        (-2, 2),
        (-2, 0),
        (-2, -2),
    ]

    def _run_healer(self, ct: Controller) -> None:
        """Healer builder: orbit near core, heal damaged buildings + self."""
        if self.my_pos is None or self.core_pos is None:
            return

        # Self-heal if damaged.
        if ct.get_action_cooldown() == 0:
            my_missing = ct.get_max_hp() - ct.get_hp()
            if my_missing >= 4 and ct.can_heal(self.my_pos):
                ct.heal(self.my_pos)
                dbg(
                    f"r={self.round_no} id={self.my_id} healer self-heal missing={my_missing}",
                )
                return

        # Heal adjacent damaged friendly buildings.
        if ct.get_action_cooldown() == 0 and self._try_heal(ct):
            return

        # Walk toward damaged buildings in vision.
        heal_target = self._find_heal_target(ct)
        if heal_target is not None:
            self._walk_toward(ct, heal_target)
            return

        # Orbit core at radius 2 to stay close for healing.
        if not hasattr(self, "_healer_orbit_step"):
            self._healer_orbit_step = 0
        dx, dy = self._HEALER_ORBIT_DIRS[self._healer_orbit_step % 8]
        target = Position(self.core_pos.x + dx, self.core_pos.y + dy)
        if self.my_pos.distance_squared(target) <= 2:
            self._healer_orbit_step += 1
            dx, dy = self._HEALER_ORBIT_DIRS[self._healer_orbit_step % 8]
            target = Position(self.core_pos.x + dx, self.core_pos.y + dy)
        self._walk_toward(ct, target, best_effort=True)

    # ------------------------------------------------------------------
    # Ti builder state machine
    # ------------------------------------------------------------------

    def _run_builder(self, ct: Controller) -> None:
        if self.my_pos is None:
            return

        # Maintain sector ownership every turn.
        self._update_sector_claims(ct)
        self._claim_sector(ct)

        # Track persistent minor damage for trickle-attack detection.
        self._update_damaged_turns(ct)

        # Opportunistic healing: heal adjacent damaged friendly buildings.
        # Only heal if _needs_heal (>= 4 HP missing, or persistent minor damage).
        if ct.get_action_cooldown() == 0 and self._try_heal(ct):
            return

        # If connecting back, continue that
        if self.connecting:
            self._run_connect_back(ct)
            return

        # Check for damaged buildings in vision to walk toward.
        heal_target = self._find_heal_target(ct)
        if heal_target is not None:
            self._walk_toward(ct, heal_target)
            return

        # Refresh target each turn
        self.target_ore = self._pick_ore()

        if self.target_ore is not None:
            self.healing = False
            dist_sq = self.my_pos.distance_squared(self.target_ore)
            if dist_sq == 0:
                self._step_off_ore(ct)
                return
            if dist_sq <= 2:
                self._try_build_harvester(ct)
                return
            self.explore_target = None
            if not self._walk_toward(ct, self.target_ore):
                self.target_ore = None
            return

        # No ore — explore to find more
        self._explore(ct)

    # ------------------------------------------------------------------
    # Aggro builder state machine
    # ------------------------------------------------------------------

    def _run_aggro_builder(self, ct: Controller) -> None:
        """Aggro builder: find exposed enemy harvesters and place sentinels next to them."""
        if self.my_pos is None:
            return

        # Attack sub-state: fire at enemy building we're standing on.
        if self.connect_attack_pos is not None:
            self._aggro_attack(ct)
            if self.connect_attack_pos is not None:
                return  # still attacking
            # Attack done — fall through to continue sentinel placement

        # Phase 0: wait for enemy core inference before committing direction.
        if self.enemy_core_pos is None:
            self._aggro_advance_blind(ct)
            return

        # If placing a sentinel for an outpost, finish that first.
        if self.aggro_sentinel_pos is not None:
            self._try_build_outpost_sentinel(ct)
            return

        # Check for enemy harvesters to place sentinels near.
        placement = self._find_best_sentinel_placement(ct)
        if placement is not None:
            enemy_harv, sentinel_pos = placement
            self.aggro_sentinel_pos = sentinel_pos
            self.aggro_harvester_pos = enemy_harv
            self.aggro_sentinel_turns = 0
            dbg(
                f"r={self.round_no} id={self.my_id} aggro targeting enemy harvester at {enemy_harv}, sentinel at {sentinel_pos}",
            )
            return

        # No enemy harvesters — scout for enemy infrastructure.
        self._aggro_scout(ct)

    def _find_best_sentinel_placement(
        self,
        ct: Controller,
    ) -> tuple[Position, Position] | None:
        """Score all (harvester, sentinel_pos) candidates and return the best.

        Returns (harvester_pos, sentinel_pos) or None.
        """
        if self.my_pos is None or self.enemy_core_pos is None:
            return None

        # Collect visible enemy launcher positions for range checks.
        enemy_launchers: list[Position] = []
        for lpos, (_, lt, lteam) in self.visible_buildings.items():
            if lteam != self.my_team and lt == EntityType.LAUNCHER:
                enemy_launchers.append(lpos)

        # Check for nearby enemy turrets (sentinel scoring).
        enemy_turrets: list[Position] = []
        for tpos, (_, tt, tteam) in self.visible_buildings.items():
            if tteam != self.my_team and tt in (
                EntityType.SENTINEL,
                EntityType.GUNNER,
                EntityType.BREACH,
                EntityType.LAUNCHER,
            ):
                enemy_turrets.append(tpos)

        best: tuple[Position, Position] | None = None
        best_score = -1

        for hpos, (_, etype, team) in self.visible_buildings.items():
            if team == self.my_team or etype != EntityType.HARVESTER:
                continue
            if hpos in self.aggro_failed_targets:
                continue
            env = self.tile_env.get(hpos)
            if env != Environment.ORE_TITANIUM:
                continue
            # Check if already covered by our sentinel.
            already_covered = False
            for d in ALL_DIRECTIONS:
                ddx, ddy = DIRECTION_DELTA[d]
                adj = Position(hpos.x + ddx, hpos.y + ddy)
                adj_info = self.visible_buildings.get(adj)
                if adj_info is not None:
                    _, adj_etype, adj_team = adj_info
                    if adj_team == self.my_team and adj_etype == EntityType.SENTINEL:
                        already_covered = True
                        break
            if already_covered:
                continue

            # Evaluate each cardinal-adjacent tile.
            for d in CARDINALS:
                ddx, ddy = DIRECTION_DELTA[d]
                spos = Position(hpos.x + ddx, hpos.y + ddy)
                if not self._in_bounds(spos):
                    continue
                senv = self.tile_env.get(spos)
                if senv is None or senv == Environment.WALL:
                    continue
                if senv in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
                    continue

                # Tile tier.
                tier = 0
                info = self.visible_buildings.get(spos)
                if info is not None:
                    _, setype, steam = info
                    if setype == EntityType.MARKER:
                        pass
                    elif steam != self.my_team and setype in self.CLEARABLE_BUILDINGS:
                        tier = self.CLEARABLE_TIER[setype]
                    else:
                        continue

                # Launcher range check — hard skip.
                in_launcher = False
                near_launcher = False
                for lp in enemy_launchers:
                    ld = spos.distance_squared(lp)
                    if ld <= 26:
                        in_launcher = True
                        break
                    if ld <= 50:
                        near_launcher = True
                if in_launcher:
                    continue

                score = 0
                # Tier bonus (empty=30, transport=20, road=10).
                score += (3 - tier) * 10
                # Core hittable from this position?
                for face_d in ALL_DIRECTIONS:
                    if ct.can_fire_from(
                        spos,
                        face_d,
                        EntityType.SENTINEL,
                        self.enemy_core_pos,
                    ):
                        score += 50
                        break
                # Closer to enemy core = better.
                core_dist = spos.distance_squared(self.enemy_core_pos)
                score += max(0, 100 - core_dist // 10)
                # Near launcher but safe — can hit protected targets.
                if near_launcher:
                    score += 5
                # Undefended area bonus.
                if not any(spos.distance_squared(tp) <= 32 for tp in enemy_turrets):
                    score += 15

                if score > best_score:
                    best_score = score
                    best = (hpos, spos)

        return best

    def _aggro_attack(self, ct: Controller) -> None:
        """Attack an enemy building the builder needs to clear."""
        target = self.connect_attack_pos
        if target is None:
            return
        # Check if the enemy building is still there.
        info = self.visible_buildings.get(target)
        if info is None or info[2] == self.my_team:
            dbg(f"r={self.round_no} id={self.my_id} aggro attack done at {target}")
            self.connect_attack_pos = None
            return
        # Walk onto the building tile if not there.
        if self.my_pos != target:
            self._walk_toward(ct, target)
            return
        # Fire at it.
        if ct.get_action_cooldown() != 0:
            return
        if ct.can_fire(self.my_pos):
            ct.fire(self.my_pos)
            dbg(f"r={self.round_no} id={self.my_id} aggro fire at {target}")

    def _aggro_advance_blind(self, ct: Controller) -> None:
        """Walk toward map centre to generate vision and resolve symmetry."""
        if self.map_w is None or self.map_h is None:
            return
        # If we have unresolved symmetry candidates, walk toward closest remaining.
        if self.enemy_core_candidates:
            remaining = [
                self.enemy_core_candidates[i]
                for i in range(3)
                if not self.symmetry_eliminated[i]
            ]
            if remaining:
                # Pick closest candidate.
                best = min(remaining, key=self.my_pos.distance_squared)
                self._walk_toward(ct, best, best_effort=True)
                return
        # Fallback: walk toward map centre.
        centre = Position(self.map_w // 2, self.map_h // 2)
        self._walk_toward(ct, centre, best_effort=True)

    _ORBIT_DIRS = [
        (0, -1),
        (1, -1),
        (1, 0),
        (1, 1),
        (0, 1),
        (-1, 1),
        (-1, 0),
        (-1, -1),
    ]

    def _aggro_scout(self, ct: Controller) -> None:
        """Orbit enemy core to find harvesters."""
        if self.enemy_core_pos is None or self.my_pos is None or self.map_w is None:
            return
        dx, dy = self._ORBIT_DIRS[self.aggro_orbit_step % 8]
        r = AGGRO_ORBIT_RADIUS
        tx = max(0, min(self.map_w - 1, self.enemy_core_pos.x + dx * r))
        ty = max(0, min(self.map_h - 1, self.enemy_core_pos.y + dy * r))
        target = Position(tx, ty)
        if self.my_pos.distance_squared(target) <= 4:
            self.aggro_orbit_step += 1
            dx, dy = self._ORBIT_DIRS[self.aggro_orbit_step % 8]
            tx = max(0, min(self.map_w - 1, self.enemy_core_pos.x + dx * r))
            ty = max(0, min(self.map_h - 1, self.enemy_core_pos.y + dy * r))
            target = Position(tx, ty)
        self._walk_toward(ct, target, best_effort=True)

    # Enemy building types that the aggro builder can clear with fire().
    CLEARABLE_BUILDINGS = {
        EntityType.ROAD,
        EntityType.CONVEYOR,
        EntityType.BRIDGE,
        EntityType.SPLITTER,
        EntityType.ARMOURED_CONVEYOR,
    }
    # Tier cost for clearable buildings (lower = preferred).
    # Prefer transport over roads: clearing a conveyor disrupts enemy economy.
    # Roads are cheap for enemy to rebuild and low strategic value.
    CLEARABLE_TIER = {
        EntityType.CONVEYOR: 1,
        EntityType.BRIDGE: 1,
        EntityType.SPLITTER: 1,
        EntityType.ARMOURED_CONVEYOR: 1,
        EntityType.ROAD: 2,
    }

    def _try_build_outpost_sentinel(self, ct: Controller) -> None:
        """Build sentinel at aggro_sentinel_pos, then resume advancing."""
        if self.aggro_sentinel_pos is None:
            return
        self.aggro_sentinel_turns += 1
        # Give up after 40 turns of non-Ti issues (clearing, walking, blocked).
        # Don't count turns where we're just waiting for Ti.
        titanium_now, _ = ct.get_global_resources()
        sentinel_cost_now = ct.get_sentinel_cost()[0]
        pos = self.aggro_sentinel_pos
        dist_sq = self.my_pos.distance_squared(pos)
        # Tile is "clear enough" if empty or has our own road (we placed it to hold).
        tile_info = self.visible_buildings.get(pos)
        tile_held = tile_info is None or (
            tile_info[2] == self.my_team and tile_info[1] == EntityType.ROAD
        )
        waiting_for_ti = dist_sq <= 2 and titanium_now < sentinel_cost_now and tile_held
        if waiting_for_ti:
            self.aggro_sentinel_turns = max(
                0,
                self.aggro_sentinel_turns - 1,
            )  # freeze timer
            dbg(
                f"r={self.round_no} id={self.my_id} aggro wait_ti need={sentinel_cost_now} have={titanium_now}",
            )
        if self.aggro_sentinel_turns > 40:
            dbg(f"r={self.round_no} id={self.my_id} aggro sentinel timeout, giving up")
            if self.aggro_harvester_pos is not None:
                self.aggro_failed_targets.add(self.aggro_harvester_pos)
            self.aggro_sentinel_pos = None
            self.aggro_harvester_pos = None
            return

        if dist_sq > 2:
            dbg(
                f"r={self.round_no} id={self.my_id} aggro walking to sentinel pos {pos} dist={dist_sq}",
            )
            self._walk_toward(ct, pos)
            return

        # Can't build on a tile we're standing on — step off only when
        # we can afford the sentinel. Otherwise place a road to hold the tile.
        if dist_sq == 0:
            titanium_check, _ = ct.get_global_resources()
            sentinel_cost_check = ct.get_sentinel_cost()[0]
            if titanium_check < sentinel_cost_check:
                # Hold tile with a road so enemy can't rebuild here.
                if ct.get_action_cooldown() == 0 and ct.can_build_road(self.my_pos):
                    ct.build_road(self.my_pos)
                    dbg(
                        f"r={self.round_no} id={self.my_id} aggro road hold at {self.my_pos} wait_ti={sentinel_cost_check}",
                    )
                return
            for d in ALL_DIRECTIONS:
                if ct.can_move(d):
                    ct.move(d)
                    dbg(
                        f"r={self.round_no} id={self.my_id} aggro step off sentinel pos",
                    )
                    return
            return

        if ct.get_action_cooldown() != 0:
            return

        # Check tile BEFORE Ti — start clearing while saving up.
        info = self.visible_buildings.get(pos)
        if info is not None:
            _, etype, team = info
            if etype == EntityType.MARKER:
                pass  # markers can be built over
            elif team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                # Our own road (placed to hold tile) — destroy it before building.
                if ct.can_destroy(pos):
                    ct.destroy(pos)
                    dbg(
                        f"r={self.round_no} id={self.my_id} aggro destroyed own road at {pos} for sentinel",
                    )
                    # Don't return — fall through to build sentinel this turn
                else:
                    return
            elif team != self.my_team and etype in self.CLEARABLE_BUILDINGS:
                self.connect_attack_pos = pos
                dbg(
                    f"r={self.round_no} id={self.my_id} aggro clearing enemy {etype.name} at {pos} for sentinel",
                )
                return
            else:
                dbg(
                    f"r={self.round_no} id={self.my_id} aggro sentinel pos blocked by {etype.name}, giving up",
                )
                if self.aggro_harvester_pos is not None:
                    self.aggro_failed_targets.add(self.aggro_harvester_pos)
                self.aggro_sentinel_pos = None
                self.aggro_harvester_pos = None
                return

        # Check we can afford it.
        titanium, _ = ct.get_global_resources()
        sentinel_cost = ct.get_sentinel_cost()[0]
        if titanium < sentinel_cost:
            dbg(
                f"r={self.round_no} id={self.my_id} aggro wait_ti need={sentinel_cost} have={titanium}",
            )
            return

        # Pick facing that maximises coverage of permanent enemy targets.
        # Only score things worth orienting for (permanent, high-value).
        # Bots/roads/harvesters are temporary or low-value — skip.
        harvester = self.aggro_harvester_pos
        _TARGET_WEIGHT = {
            EntityType.SENTINEL: 10,
            EntityType.GUNNER: 10,
            EntityType.BREACH: 10,
            EntityType.LAUNCHER: 10,
            EntityType.CORE: 5,
            EntityType.CONVEYOR: 2,
            EntityType.BRIDGE: 2,
            EntityType.SPLITTER: 2,
            EntityType.ARMOURED_CONVEYOR: 2,
        }

        best_dir: Direction | None = None
        best_score = -1
        for direction in ALL_DIRECTIONS:
            ddx, ddy = DIRECTION_DELTA[direction]
            if harvester and Position(pos.x + ddx, pos.y + ddy) == harvester:
                continue
            if not ct.can_build_sentinel(pos, direction):
                continue
            score = 0
            for tile in ct.get_attackable_tiles_from(
                pos,
                direction,
                EntityType.SENTINEL,
            ):
                info = self.visible_buildings.get(tile)
                if info is not None and info[2] != self.my_team:
                    score += _TARGET_WEIGHT.get(info[1], 0)
            if score > best_score:
                best_score = score
                best_dir = direction

        if best_dir is not None:
            ct.build_sentinel(pos, best_dir)
            dbg(
                f"r={self.round_no} id={self.my_id} aggro sentinel at {pos} facing {best_dir.name} score={best_score}",
            )
            self.aggro_sentinel_pos = None
            self.aggro_harvester_pos = None
            self.aggro_orbit_step += 2  # move to fresh area after placement
        else:
            dbg(
                f"r={self.round_no} id={self.my_id} aggro can_build_sentinel=False pos={pos} all dirs ti={titanium}",
            )

    # ------------------------------------------------------------------
    # Walking
    # ------------------------------------------------------------------

    def _step_toward_chain_end(self, ct: Controller) -> None:
        """After building, use remaining move cooldown to step toward chain_end."""
        if self.my_pos is None or self.chain_end is None:
            return
        if ct.get_move_cooldown() != 0:
            return
        dx = self.chain_end.x - self.my_pos.x
        dy = self.chain_end.y - self.my_pos.y
        if dx == 0 and dy == 0:
            return
        sx = max(-1, min(1, dx))
        sy = max(-1, min(1, dy))
        d = DELTA_TO_DIRECTION.get((sx, sy))
        if d is not None and ct.can_move(d):
            ct.move(d)
            self.my_pos = ct.get_position()

    def _build_walk_cache(self) -> None:
        """Pre-compute (x,y) tuple sets for A* walk. Rebuilt once per turn."""
        if self._walk_cache_round == self.round_no:
            return
        self._walk_cache_round = self.round_no
        wc_walls = self._wc_walls
        wc_blocked = self._wc_blocked
        wc_known = self._wc_known
        wc_units = self._wc_units
        wc_enemy_core = self._wc_enemy_core
        wc_walls.clear()
        wc_blocked.clear()
        wc_known.clear()
        wc_units.clear()
        wc_enemy_core.clear()

        for pos, env in self.tile_env.items():
            xy = (pos.x, pos.y)
            wc_known.add(xy)
            if env == Environment.WALL:
                wc_walls.add(xy)

        for pos, (_, etype, team) in self.visible_buildings.items():
            xy = (pos.x, pos.y)
            if (
                etype in {EntityType.ROAD, EntityType.MARKER}
                or etype in WALKABLE_BUILDINGS
            ):
                continue
            if etype == EntityType.CORE:
                if team != self.my_team:
                    for ddx in range(2):
                        for ddy in range(2):
                            wc_enemy_core.add((pos.x + ddx, pos.y + ddy))
                continue  # own core is passable
            wc_blocked.add(xy)

        # Always block enemy core 3×3 based on inferred position (not just vision).
        if self.enemy_core_pos is not None:
            ex, ey = self.enemy_core_pos.x, self.enemy_core_pos.y
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    wc_enemy_core.add((ex + dx, ey + dy))

        for pos in self.visible_unit_positions:
            wc_units.add((pos.x, pos.y))

    def _walk_toward(
        self,
        ct: Controller,
        target: Position,
        best_effort: bool = False,
    ) -> bool:
        """Move one step toward target, paving roads as needed."""
        if self.my_pos is None or ct.get_move_cooldown() != 0:
            return False

        self._build_walk_cache()
        result = astar_walk(
            self.my_pos.x,
            self.my_pos.y,
            target.x,
            target.y,
            self._wc_walls,
            self._wc_blocked,
            self._wc_known,
            self._wc_units,
            self._wc_enemy_core,
            self.map_w or 50,
            self.map_h or 50,
            cpu_fn=ct.get_cpu_time_elapsed,
            best_effort=best_effort,
        )

        if result is not None:
            dx, dy = result
            direction = DELTA_TO_DIRECTION.get((dx, dy))
            nav_source = "astar"
        else:
            direction = None
            nav_source = "none"

        # Greedy fallback: A* can't find path (CPU exhaustion or no path).
        if direction is None:
            best_dir = None
            best_dist = self.my_pos.distance_squared(target)
            for d in ALL_DIRECTIONS:
                ddx, ddy = DIRECTION_DELTA[d]
                nxt = Position(self.my_pos.x + ddx, self.my_pos.y + ddy)
                if not self._is_possibly_passable(nxt):
                    continue
                dist = nxt.distance_squared(target)
                if dist < best_dist:
                    best_dist = dist
                    best_dir = d
            direction = best_dir
            if direction is not None:
                nav_source = "greedy"

        if direction is None:
            dbg(
                f"r={self.round_no} id={self.my_id} nav=no_dir at {self.my_pos} -> {target}",
            )
            return False

        dx, dy = DIRECTION_DELTA[direction]
        next_pos = Position(self.my_pos.x + dx, self.my_pos.y + dy)

        if ct.can_move(direction):
            ct.move(direction)
            self.my_pos = ct.get_position()
            return True

        # Try to pave a road if the tile is empty or has a marker (markers are
        # not walkable but can be built over by either team).
        bld_info = self.visible_buildings.get(next_pos)
        can_pave = bld_info is None or (bld_info[1] == EntityType.MARKER)
        if ct.get_action_cooldown() == 0 and can_pave and ct.can_build_road(next_pos):
            ct.build_road(next_pos)
            if ct.can_move(direction):
                ct.move(direction)
                self.my_pos = ct.get_position()
                return True

        env = self.tile_env.get(next_pos)
        bld = self.visible_buildings.get(next_pos)
        bld_str = f"{bld[1].name}({bld[2]})" if bld else "none"
        dbg(
            f"r={self.round_no} id={self.my_id} stuck at {self.my_pos} dir={direction.name} "
            f"nav={nav_source} next={next_pos} env={env} bld={bld_str} "
            f"cd={ct.get_action_cooldown()}",
        )
        return False

    # ------------------------------------------------------------------
    # Harvester building
    # ------------------------------------------------------------------

    def _update_damaged_turns(self, ct: Controller) -> None:
        """Track how long friendly buildings have been at 1-3 HP missing."""
        seen: set[Position] = set()
        for pos, (eid, _, team) in self.visible_buildings.items():
            if team != self.my_team:
                continue
            missing = ct.get_max_hp(eid) - ct.get_hp(eid)
            if 0 < missing < 4:
                self.damaged_turns[pos] = self.damaged_turns.get(pos, 0) + 1
                seen.add(pos)
            # Reset if fully healed or heavily damaged (will be healed normally).
        # Clear entries for buildings we can see that are fine or gone.
        for pos in list(self.damaged_turns):
            if pos not in seen:
                self.damaged_turns.pop(pos)

    def _needs_heal(self, pos: Position, eid: int, ct: Controller) -> bool:
        """Check if a friendly building needs healing."""
        missing = ct.get_max_hp(eid) - ct.get_hp(eid)
        if missing <= 0:
            return False
        if missing >= 4:
            return True
        # Minor damage: only heal if persistent (being attacked).
        return self.damaged_turns.get(pos, 0) >= 3

    def _find_heal_target(self, ct: Controller) -> Position | None:
        """Find a damaged friendly building in vision worth walking to.

        Only called when not connecting and no ore target — i.e. idle builders.
        For the core, returns the nearest core tile rather than center.
        """
        if self.my_pos is None:
            return None
        best_pos: Position | None = None
        best_missing = 0
        for pos, (eid, etype, team) in self.visible_buildings.items():
            if team != self.my_team:
                continue
            if not self._needs_heal(pos, eid, ct):
                continue
            missing = ct.get_max_hp(eid) - ct.get_hp(eid)
            # For core, walk toward nearest edge tile.
            walk_to = pos
            if etype == EntityType.CORE:
                nearest_dist = 999
                for cdx in range(-1, 2):
                    for cdy in range(-1, 2):
                        cpos = Position(pos.x + cdx, pos.y + cdy)
                        d = self.my_pos.distance_squared(cpos)
                        if d < nearest_dist:
                            nearest_dist = d
                            walk_to = cpos
            if self.my_pos.distance_squared(walk_to) <= 2:
                continue  # adjacent — _try_heal handles these
            if missing > best_missing:
                best_missing = missing
                best_pos = walk_to
        return best_pos

    def _try_heal(self, ct: Controller) -> bool:
        """Heal self or an adjacent damaged friendly building that _needs_heal.

        Returns True if we healed (consumed the turn).
        """
        if self.my_pos is None:
            return False
        # Self-heal: builder HP missing >= 4.
        my_hp = ct.get_hp()
        my_max = ct.get_max_hp()
        if my_max - my_hp >= 4 and ct.can_heal(self.my_pos):
            ct.heal(self.my_pos)
            dbg(f"r={self.round_no} id={self.my_id} self-heal missing={my_max - my_hp}")
            return True
        best_pos: Position | None = None
        best_missing = 0
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                pos = Position(self.my_pos.x + dx, self.my_pos.y + dy)
                info = self.visible_buildings.get(pos)
                if info is None:
                    continue
                eid, _, team = info
                if team != self.my_team:
                    continue
                if not self._needs_heal(pos, eid, ct):
                    continue
                missing = ct.get_max_hp(eid) - ct.get_hp(eid)
                if missing > best_missing:
                    best_missing = missing
                    best_pos = pos
        # Core is 3x3 but only center is in visible_buildings — check edge tiles.
        if self.core_pos is not None:
            core_info = self.visible_buildings.get(self.core_pos)
            if core_info is not None and core_info[2] == self.my_team:
                eid = core_info[0]
                if self._needs_heal(self.core_pos, eid, ct):
                    missing = ct.get_max_hp(eid) - ct.get_hp(eid)
                    if missing > best_missing:
                        for cdx in range(-1, 2):
                            for cdy in range(-1, 2):
                                cpos = Position(
                                    self.core_pos.x + cdx,
                                    self.core_pos.y + cdy,
                                )
                                if self.my_pos.distance_squared(cpos) <= 2:
                                    best_pos = cpos
                                    best_missing = missing
                                    break
                            if best_missing == missing:
                                break
        if best_pos is not None and ct.can_heal(best_pos):
            ct.heal(best_pos)
            dbg(
                f"r={self.round_no} id={self.my_id} heal at {best_pos} missing={best_missing}",
            )
            return True
        return False

    def _step_off_ore(self, ct: Controller) -> bool:
        """If standing on target ore, step to an adjacent tile so we can build."""
        if self.target_ore is None or self.my_pos is None:
            return False
        if self.my_pos != self.target_ore:
            return False
        for d in ALL_DIRECTIONS:
            if ct.can_move(d):
                ct.move(d)
                dbg(
                    f"r={self.round_no} id={self.my_id} step off ore {self.target_ore} dir={d.name}",
                )
                return True
        return False

    def _try_build_harvester(
        self,
        ct: Controller,
        target_override: Position | None = None,
    ) -> bool:
        if self.target_ore is None or ct.get_action_cooldown() != 0:
            return False

        # Clear a friendly road/barrier on the ore tile
        info = self.visible_buildings.get(self.target_ore)
        if info is not None:
            _, etype, team = info
            if (
                team == self.my_team
                and etype
                in {
                    EntityType.ROAD,
                    EntityType.BARRIER,
                    EntityType.MARKER,
                }
                and ct.can_destroy(self.target_ore)
            ):
                ct.destroy(self.target_ore)
                self.visible_buildings.pop(self.target_ore, None)

        # Decide routing target and validate source pad BEFORE building.
        if target_override is not None:
            target = target_override
        else:
            target = self._nearest_unsaturated_terminal(self.target_ore)
            if target is None:
                target = self.core_pos

        source_pad = self._pick_source_pad(self.target_ore, target)
        if source_pad is None:
            dbg(
                f"r={self.round_no} id={self.my_id} no source pad for {self.target_ore} — skipping",
            )
            self.claimed_ores.add(self.target_ore)
            self.target_ore = None
            return False

        if not ct.can_build_harvester(self.target_ore):
            # Diagnose why
            titanium, _ = ct.get_global_resources()
            harv_cost = ct.get_harvester_cost()[0]
            info2 = self.visible_buildings.get(self.target_ore)
            if titanium < harv_cost:
                reason = f"need_ti={harv_cost} have={titanium}"
            elif info2 is not None:
                _, bt, bteam = info2
                reason = f"blocked_by={bt.name} team={'own' if bteam == self.my_team else 'enemy'}"
            else:
                reason = "unknown"
            dbg(
                f"r={self.round_no} id={self.my_id} can't build harvester at {self.target_ore} ({reason})",
            )
            return False

        ct.build_harvester(self.target_ore)
        dbg(
            f"r={self.round_no} id={self.my_id} built harvester at {self.target_ore} pad={source_pad}",
        )

        self.connecting = True
        self.connect_turns = 0
        self.connect_last_build_round = self.round_no
        self.connect_harvester_pos = self.target_ore
        self.chain_end = source_pad
        self.connect_target = target
        self.claimed_ores.add(self.target_ore)
        self.target_ore = None
        self.connect_plan = None
        self.connect_plan_idx = 0
        self.connect_unwind_destroy = None
        self.connect_attack_pos = None
        dbg(
            f"r={self.round_no} id={self.my_id} connect start pad={source_pad} target={target}",
        )
        return True

    # ------------------------------------------------------------------
    # Connect-back: A* planned chain extension
    # ------------------------------------------------------------------

    def _pick_source_pad(
        self,
        harvester_pos: Position,
        toward: Position,
    ) -> Position | None:
        """Cardinal neighbor of harvester closest to toward.

        Skips walls and tiles already occupied by non-clearable buildings
        (e.g., a neighbouring harvester on an adjacent ore deposit) so the
        connect-back always starts on a usable tile.  Allied roads and
        existing chain conveyors are acceptable because the connect-back can
        clear roads and the merge check handles conveyors in our tree.

        """
        opposite_ore = Environment.ORE_AXIONITE

        # Collect valid pads: prefer clean (no contamination adjacency), fall
        # back to contaminated if no clean pads exist.
        clean_best, clean_dist = None, float("inf")
        contam_best, contam_dist = None, float("inf")
        for d in CARDINALS:
            dx, dy = DIRECTION_DELTA[d]
            pad = Position(harvester_pos.x + dx, harvester_pos.y + dy)
            if not self._in_bounds(pad):
                continue
            env = self.tile_env.get(pad)
            if env == Environment.WALL:
                continue
            # Skip pads on opposite-type ore.
            if env == opposite_ore:
                continue
            info = self.visible_buildings.get(pad)
            if info is not None:
                _, btype, bteam = info
                if btype in (EntityType.ROAD, EntityType.MARKER):
                    pass  # clearable — ok
                elif self._is_core_tile(pad):
                    pass  # core tile — ok
                elif (
                    bteam == self.my_team
                    and btype == EntityType.ROAD
                    and pad in self.my_tree
                ):
                    pass  # own road in tree — clearable, ok
                elif (
                    bteam == self.my_team
                    and btype in WALKABLE_BUILDINGS
                    and pad in self.my_tree
                ):
                    # Own bridge/conveyor — can't build over it, skip
                    continue
                else:
                    continue  # foreign building, harvester, enemy, etc. — skip
            dist = pad.distance_squared(toward)
            # Check if pad is adjacent to opposite-type ore (contamination risk).
            adj_contaminated = False
            for adx, ady in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                adj_env = self.tile_env.get(Position(pad.x + adx, pad.y + ady))
                if adj_env == opposite_ore:
                    adj_contaminated = True
                    break
            if adj_contaminated:
                if dist < contam_dist:
                    contam_dist = dist
                    contam_best = pad
            elif dist < clean_dist:
                clean_dist = dist
                clean_best = pad
        return clean_best if clean_best is not None else contam_best

    def _build_chain_cache(self) -> None:
        """Pre-compute (x,y) sets for A* chain planning from _classify_tile logic.

        Skips rebuild if tile_env and known_buildings haven't changed since last build.
        """
        cache_key = (len(self.tile_env), len(self.known_buildings))
        if hasattr(self, "_cc_cache_key") and self._cc_cache_key == cache_key:
            return  # no new tiles, cache is still valid
        self._cc_cache_key = cache_key

        cc_free: set[tuple[int, int]] = set()
        cc_blocked: set[tuple[int, int]] = set()
        cc_ore: set[tuple[int, int]] = set()
        cc_walls: set[tuple[int, int]] = set()
        cc_known: set[tuple[int, int]] = set()

        for pos, env in self.tile_env.items():
            xy = (pos.x, pos.y)
            cc_known.add(xy)
            if env == Environment.WALL:
                cc_walls.add(xy)
            elif env in (Environment.ORE_TITANIUM, Environment.ORE_AXIONITE):
                cc_ore.add(xy)

        # Hard-block tiles cardinally adjacent to Ax ores to prevent contamination.
        for pos, env in self.tile_env.items():
            if env == Environment.ORE_AXIONITE:
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    xy = (pos.x + dx, pos.y + dy)
                    cc_blocked.add(xy)
                    cc_free.discard(xy)

        for pos, (_, etype, team) in self.known_buildings.items():
            xy = (pos.x, pos.y)
            if team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                cc_free.add(xy)
                continue
            if self._is_core_tile(pos):
                cc_free.add(xy)
                continue
            if team != self.my_team and etype == EntityType.ROAD:
                # Enemy roads are attackable — treat as free so A* routes through them.
                cc_free.add(xy)
                continue
            cc_blocked.add(xy)

        # Always block enemy core 3x3 regardless of visibility.
        if self.enemy_core_pos is not None:
            ex, ey = self.enemy_core_pos.x, self.enemy_core_pos.y
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    cc_blocked.add((ex + dx, ey + dy))

        self._cc_free = cc_free
        self._cc_blocked = cc_blocked
        self._cc_ore = cc_ore
        self._cc_walls = cc_walls
        self._cc_known = cc_known

    def _get_connect_terminals(self) -> set[tuple[int, int]]:
        """Build set of (x,y) positions where the chain can terminate.

        Excludes nodes belonging to saturated trees (>= MAX_HARVESTERS_PER_TREE).
        Core tiles are always included (connecting there starts a new tree).
        """
        terminals: set[tuple[int, int]] = set()
        for p in self.my_tree:
            tree_id = self.tree_ids.get(p)
            if (
                tree_id is not None
                and self.tree_harvester_counts[tree_id] >= MAX_HARVESTERS_PER_TREE
            ):
                continue
            terminals.add((p.x, p.y))
        # Core tiles always valid — connecting here starts a new tree.
        if self.core_pos is not None:
            cx, cy = self.core_pos.x, self.core_pos.y
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    terminals.add((cx + dx, cy + dy))
        return terminals

    def _compute_connect_plan(self, ct: Controller) -> None:
        """Run A* to plan the full connect-back chain."""
        self._build_chain_cache()
        terminals = self._get_connect_terminals()

        plan = astar_chain(
            self.chain_end.x,
            self.chain_end.y,
            self.connect_target.x,
            self.connect_target.y,
            terminals,
            self._cc_free,
            self._cc_blocked,
            self._cc_ore,
            self._cc_walls,
            self._cc_known,
            (self.connect_harvester_pos.x, self.connect_harvester_pos.y)
            if self.connect_harvester_pos
            else None,
            self.map_w or 50,
            self.map_h or 50,
            cpu_fn=ct.get_cpu_time_elapsed,
        )
        self.connect_plan = plan
        self.connect_plan_idx = 0
        if plan is not None:
            dbg(
                f"r={self.round_no} id={self.my_id} A* plan len={len(plan)} from {self.chain_end} -> {self.connect_target}",
            )
        else:
            dbg(
                f"r={self.round_no} id={self.my_id} A* plan FAILED from {self.chain_end} -> {self.connect_target}",
            )

    def _plan_step_invalid(self) -> bool:
        """Check if the next planned step is still valid."""
        if self.connect_plan is None or self.connect_plan_idx >= len(self.connect_plan):
            return True
        step = self.connect_plan[self.connect_plan_idx]
        action = step[0]
        if action == "conv":
            pos = Position(step[1], step[2])
            tc = self._classify_tile(pos)
            if tc not in ("free", "unseen", "enemy_road"):
                dbg(
                    f"r={self.round_no} id={self.my_id} plan step {self.connect_plan_idx} invalid: conv at {pos} is {tc}",
                )
                return True
            # Also check if the output tile is blocked by a non-clearable building.
            next_idx = self.connect_plan_idx + 1
            if next_idx < len(self.connect_plan):
                ns = self.connect_plan[next_idx]
                ddx = ns[1] - step[1]
                ddy = ns[2] - step[2]
                out_pos = Position(step[1] + ddx, step[2] + ddy)
                out_info = self.visible_buildings.get(out_pos)
                if out_info is not None:
                    _, out_etype, out_team = out_info
                    if out_team == self.my_team and out_etype not in {
                        EntityType.ROAD,
                        EntityType.MARKER,
                    }:
                        is_merge = out_pos in self.my_tree
                        if not self._is_core_tile(out_pos) and not is_merge:
                            dbg(
                                f"r={self.round_no} id={self.my_id} plan step {self.connect_plan_idx} invalid: conv output {out_pos} has own {out_etype.name}",
                            )
                            return True
            return False
        # bridge
        # Check landing is still valid
        landing = Position(step[3], step[4])
        tc = self._classify_tile(landing)
        terminals = self._get_connect_terminals()
        if tc in ("free", "enemy_road") or (landing.x, landing.y) in terminals:
            return False
        dbg(
            f"r={self.round_no} id={self.my_id} plan step {self.connect_plan_idx} invalid: bridge landing {landing} is {tc}",
        )
        return True

    def _detect_enemy_blocking(self, ct: Controller) -> None:
        """Check if chain_end or its planned output has an attackable enemy building.

        Sets connect_attack_pos if an enemy road (or other attackable building) is
        found at the placement tile or the conveyor output tile.
        """
        if self.chain_end is None:
            return

        # Enemy building at chain_end itself (the tile we need to build on)
        info = self.visible_buildings.get(self.chain_end)
        if info is not None:
            _, etype, team = info
            if team != self.my_team and etype == EntityType.ROAD:
                self.connect_attack_pos = self.chain_end
                dbg(
                    f"r={self.round_no} id={self.my_id} attack target: enemy {etype.name} at chain_end {self.chain_end}",
                )
                return

        # Enemy building at the planned output tile (the tile the conveyor will point to)
        if self.connect_plan and self.connect_plan_idx < len(self.connect_plan):
            step = self.connect_plan[self.connect_plan_idx]
            if step[0] == "conv":
                conv_pos = self.chain_end
                next_idx = self.connect_plan_idx + 1
                if next_idx < len(self.connect_plan):
                    ns = self.connect_plan[next_idx]
                    out_pos = Position(ns[1], ns[2])
                else:
                    # Last step: output toward terminal
                    adj = self._find_adjacent_terminal(conv_pos)
                    if adj is not None:
                        out_pos = adj[0]
                    else:
                        return
                out_info = self.visible_buildings.get(out_pos)
                if out_info is not None:
                    _, out_etype, out_team = out_info
                    if out_team != self.my_team and out_etype == EntityType.ROAD:
                        self.connect_attack_pos = out_pos
                        dbg(
                            f"r={self.round_no} id={self.my_id} attack target: enemy {out_etype.name} at output {out_pos}",
                        )
                        return

    def _execute_connect_step(self, ct: Controller) -> None:
        """Execute the next step from the A* plan."""
        if self.connect_plan is None or self.connect_plan_idx >= len(self.connect_plan):
            self._finish_connect(success=True, terminal=self.chain_end)
            return

        step = self.connect_plan[self.connect_plan_idx]
        action = step[0]

        if action == "conv":
            # Place conveyor at chain_end pointing toward next position
            conv_pos = self.chain_end
            _step_x, _step_y = step[1], step[2]

            # Determine direction: from chain_end to the step position
            # The step IS at chain_end (the conveyor is placed at chain_end)
            # and the NEXT step tells us where to point
            next_idx = self.connect_plan_idx + 1
            if next_idx < len(self.connect_plan):
                ns = self.connect_plan[next_idx]
                if ns[0] == "conv":
                    target_x, target_y = ns[1], ns[2]
                else:  # bridge — bridge FROM is the next chain_end
                    target_x, target_y = ns[1], ns[2]
                ddx = target_x - conv_pos.x
                ddy = target_y - conv_pos.y
            else:
                # Last step: point toward a terminal
                adj = self._find_adjacent_terminal(conv_pos)
                if adj is not None:
                    adj_pos, conv_dir = adj
                    if self._try_place_conveyor(ct, conv_pos, conv_dir):
                        self.current_chain.append(conv_pos)
                        dbg(
                            f"r={self.round_no} id={self.my_id} connect DONE (plan) turns={self.connect_turns}",
                        )
                        self._finish_connect(success=True, terminal=adj_pos)
                    return
                # No adjacent terminal — try to point toward connect_target
                ddx = self.connect_target.x - conv_pos.x
                ddy = self.connect_target.y - conv_pos.y

            conv_dir = DELTA_TO_DIRECTION.get((ddx, ddy))
            if conv_dir is None:
                # Non-cardinal delta — this shouldn't happen for conveyors
                self.connect_plan = None  # re-plan
                return

            if self._try_place_conveyor(ct, conv_pos, conv_dir):
                self.current_chain.append(conv_pos)
                self.chain_end = Position(conv_pos.x + ddx, conv_pos.y + ddy)
                self.connect_plan_idx += 1
                self._step_toward_chain_end(ct)

        elif action == "bridge":
            from_pos = self.chain_end
            landing = Position(step[3], step[4])
            if self._try_bridge_to(ct, from_pos, landing):
                self.current_chain.append(from_pos)
                self.chain_end = landing
                self.connect_plan_idx += 1
                self._step_toward_chain_end(ct)

    def _try_bridge_to(
        self,
        ct: Controller,
        from_pos: Position,
        landing: Position,
    ) -> bool:
        """Build a bridge from from_pos to a specific landing position."""
        if ct.get_action_cooldown() != 0:
            return False
        if self.my_pos is None or self.my_pos.distance_squared(from_pos) > 2:
            return False
        if self._is_enemy_core_tile(landing):
            return False
        titanium, _ = ct.get_global_resources()
        bridge_cost = ct.get_bridge_cost()[0]
        if titanium < bridge_cost:
            self.connect_last_build_round = self.round_no  # Ti wait ≠ stall
            return False
        # Clear own road/marker at bridge source if needed
        info = self.visible_buildings.get(from_pos)
        if info is not None:
            _, etype, team = info
            if team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                if ct.can_destroy(from_pos):
                    ct.destroy(from_pos)
                    self.visible_buildings.pop(from_pos, None)
                else:
                    return False
            elif etype in WALKABLE_BUILDINGS or (
                etype == EntityType.CORE and team == self.my_team
            ):
                return False
        if ct.can_build_bridge(from_pos, landing):
            ct.build_bridge(from_pos, landing)
            self.connect_last_build_round = self.round_no
            self.connect_stall_recoverable = False
            dbg(f"r={self.round_no} id={self.my_id} bridge {from_pos} -> {landing}")
            return True
        return False

    def _run_connect_back(self, ct: Controller) -> None:
        if self.my_pos is None or self.chain_end is None or self.connect_target is None:
            self._finish_connect(success=False)
            return

        # If chain_end has landed on one of our own existing tree conveyors,
        # the resource flow is already established through that chain.
        if self.chain_end in self.my_tree:
            dbg(
                f"r={self.round_no} id={self.my_id} "
                f"connect merged with own tree at {self.chain_end}",
            )
            self._finish_connect(success=True, terminal=self.chain_end)
            return

        # Detect chain interference: if another builder placed a building at
        # chain_end (not in our tree/chain), unwind to the previous chain node.
        # This prevents contamination when two builders' bridges share a landing.
        chain_end_info = self.visible_buildings.get(self.chain_end)
        if (
            chain_end_info is not None
            and self.chain_end not in self.my_tree
            and self.chain_end not in self.current_chain
        ):
            _, ce_etype, ce_team = chain_end_info
            if ce_team == self.my_team and ce_etype in {
                EntityType.CONVEYOR,
                EntityType.BRIDGE,
                EntityType.ARMOURED_CONVEYOR,
            }:
                # Own-team building we didn't place — another builder took this tile.
                if self.current_chain:
                    old_end = self.chain_end
                    # Rewind chain_end to the last node we placed a building at.
                    # Don't pop yet — we need to walk back and destroy it first.
                    self.chain_end = self.current_chain[-1]
                    self.connect_unwind_destroy = self.chain_end
                    self.connect_plan = None
                    self.connect_last_build_round = self.round_no
                    dbg(
                        f"r={self.round_no} id={self.my_id} "
                        f"connect unwind {old_end} -> {self.chain_end} "
                        f"(foreign {ce_etype.name} at chain_end)",
                    )
                    return
                # Chain start itself was taken — abandon
                dbg(
                    f"r={self.round_no} id={self.my_id} connect abandon: foreign building at chain start {self.chain_end}",
                )
                self._finish_connect(success=False)
                return

        # Handle pending unwind destroy: walk to the node and destroy our
        # bridge/conveyor so resources stop flowing to the contaminated tile.
        if self.connect_unwind_destroy is not None:
            destroy_pos = self.connect_unwind_destroy
            if self.my_pos.distance_squared(destroy_pos) > 2:
                self._walk_toward(ct, destroy_pos)
                return
            if ct.get_action_cooldown() == 0 and ct.can_destroy(destroy_pos):
                ct.destroy(destroy_pos)
                self.visible_buildings.pop(destroy_pos, None)
                self.current_chain.pop()  # remove the destroyed node
                self.connect_unwind_destroy = None
                self.connect_last_build_round = self.round_no
                dbg(
                    f"r={self.round_no} id={self.my_id} connect unwind destroyed at {destroy_pos}",
                )
            return

        # Attack sub-state: destroy enemy building blocking chain progress.
        if self.connect_attack_pos is not None:
            atk = self.connect_attack_pos
            info = self.visible_buildings.get(atk)
            if info is None or info[2] == self.my_team:
                # Destroyed or gone
                self.connect_attack_pos = None
                self.connect_last_build_round = self.round_no
                self.connect_plan = None  # re-plan now that tile is clear
                dbg(f"r={self.round_no} id={self.my_id} attack cleared at {atk}")
            elif self.my_pos != atk:
                self._walk_toward(ct, atk)
            elif ct.can_fire(self.my_pos):
                ct.fire(self.my_pos)
                dbg(
                    f"r={self.round_no} id={self.my_id} fire at enemy {info[1].name} at {atk}",
                )
            return

        # Check if chain_end or its planned output has an attackable enemy building.
        self._detect_enemy_blocking(ct)
        if self.connect_attack_pos is not None:
            return

        self.connect_turns += 1

        # Recoverable stalls (resource wait, ally blocking) get a larger limit.
        if self.chain_end in self.visible_ally_positions:
            self.connect_stall_recoverable = True
        stall = self.round_no - self.connect_last_build_round
        effective_limit = (
            CONNECT_STALL_LIMIT * 3
            if self.connect_stall_recoverable
            else CONNECT_STALL_LIMIT
        )
        if stall > effective_limit:
            dbg(
                f"r={self.round_no} id={self.my_id} connect STALL timeout stall={stall} limit={effective_limit} turns={self.connect_turns}",
            )
            self._finish_connect(success=False)
            return

        # Termination logic
        if self.chain_end in self.my_tree or self._is_core_tile(self.chain_end):
            dbg(
                f"r={self.round_no} id={self.my_id} connect DONE turns={self.connect_turns}",
            )
            self._finish_connect(success=True, terminal=self.chain_end)
            return

        # Walk to within action radius of chain_end
        if self.my_pos.distance_squared(self.chain_end) > 2:
            self._walk_toward(ct, self.chain_end)
            return

        # Plan phase: compute or revalidate A* plan
        if self.connect_plan is None:
            self._compute_connect_plan(ct)
        elif self._plan_step_invalid():
            self.connect_plan = None
            self._compute_connect_plan(ct)

        if self.connect_plan is None:
            # A* couldn't find a path — walk toward target to reveal tiles
            self._walk_toward(ct, self.connect_target)
            return

        if not self.connect_plan:
            # Empty plan = already adjacent to terminal
            adj = self._find_adjacent_terminal(self.chain_end)
            if adj is not None:
                terminal_pos, conv_dir = adj
                if self._try_place_conveyor(ct, self.chain_end, conv_dir):
                    self.current_chain.append(self.chain_end)
                    dbg(
                        f"r={self.round_no} id={self.my_id} connect DONE turns={self.connect_turns}",
                    )
                    self._finish_connect(success=True, terminal=terminal_pos)
                    return
                if self._try_bridge_over(ct, self.chain_end, terminal_pos):
                    self._step_toward_chain_end(ct)
            return

        # Execute next step from plan
        self._execute_connect_step(ct)

    def _classify_tile(self, pos: Position) -> str:
        """Classify a tile for connect-back: free, ore, wall, blocked, unseen, enemy_road."""
        if not self._in_bounds(pos):
            return "wall"
        if self._is_enemy_core_tile(pos):
            return "blocked"
        env = self.tile_env.get(pos)
        if env is None:
            return "unseen"
        if env == Environment.WALL:
            return "wall"
        # Hard-block tiles cardinally adjacent to Ax ore to prevent contamination.
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            adj_env = self.tile_env.get(Position(pos.x + dx, pos.y + dy))
            if adj_env == Environment.ORE_AXIONITE:
                return "blocked"
        # Check both visible and remembered buildings.
        info = self.visible_buildings.get(pos) or self.known_buildings.get(pos)
        if info is not None:
            _, etype, team = info
            if team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                return "free"
            if self._is_core_tile(pos):
                return "free"  # Ti builders can use core tiles
            if team != self.my_team and etype == EntityType.ROAD:
                return "enemy_road"
            return "blocked"
        # Bare ore tile — route around it to avoid blocking future harvesters.
        if env in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
            return "ore"
        return "free"

    def _has_incoming_foreign_conveyor(self, ct: Controller, pos: Position) -> bool:
        """Check if any cardinal neighbor has an own-team conveyor that outputs INTO pos.

        Such a conveyor would feed resources into pos, contaminating our chain.
        Excludes conveyors in our own tree and current in-progress chain.
        """
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            adj = Position(pos.x + dx, pos.y + dy)
            info = self.visible_buildings.get(adj)
            if info is not None:
                eid, etype, team = info
                if (
                    team == self.my_team
                    and etype == EntityType.CONVEYOR
                    and adj not in self.my_tree
                    and adj not in self.current_chain
                ):
                    # Check if this conveyor actually outputs toward pos.
                    try:
                        conv_dir = ct.get_direction(eid)
                        cdx, cdy = DIRECTION_DELTA[conv_dir]
                        if adj.x + cdx == pos.x and adj.y + cdy == pos.y:
                            return True
                    except Exception:
                        # Can't determine direction — be conservative.
                        return True
        return False

    def _try_place_conveyor(
        self,
        ct: Controller,
        pos: Position,
        direction: Direction,
    ) -> bool:
        """Place a conveyor at pos. Handles road clearing and resource check."""
        if ct.get_action_cooldown() != 0:
            return False
        if self.my_pos is not None and self.my_pos.distance_squared(pos) > 2:
            return False
        # Reject if a foreign conveyor could feed into this position.
        if self._has_incoming_foreign_conveyor(ct, pos):
            dbg(
                f"r={self.round_no} id={self.my_id} conv rejected: {pos} has incoming foreign conveyor",
            )
            return False
        # Don't output into an enemy building or enemy core.
        odx, ody = DIRECTION_DELTA[direction]
        out_pos = Position(pos.x + odx, pos.y + ody)
        out_info = self.visible_buildings.get(out_pos)
        if out_info is not None:
            _, out_etype, out_team = out_info
            if out_team != self.my_team:
                dbg(
                    f"r={self.round_no} id={self.my_id} conv rejected: output {out_pos} has enemy {out_etype.name}",
                )
                return False
            # Don't output into own-team non-clearable buildings unless they're
            # a valid merge point (own tree) or core.
            if out_etype not in {EntityType.ROAD, EntityType.MARKER}:
                is_merge = out_pos in self.my_tree
                if not self._is_core_tile(out_pos) and not is_merge:
                    dbg(
                        f"r={self.round_no} id={self.my_id} conv rejected: output {out_pos} has own {out_etype.name}",
                    )
                    return False
        if self._is_enemy_core_tile(out_pos):
            dbg(
                f"r={self.round_no} id={self.my_id} conv rejected: output {out_pos} is enemy core",
            )
            return False

        titanium, _ = ct.get_global_resources()
        conv_cost = ct.get_conveyor_cost()[0]
        if titanium < conv_cost:
            self.connect_last_build_round = self.round_no  # Ti wait ≠ stall
            return False

        # Clear own road or marker if present
        info = self.visible_buildings.get(pos)
        if info is not None:
            _, etype, team = info
            if team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                if ct.can_destroy(pos):
                    ct.destroy(pos)
                    self.visible_buildings.pop(pos, None)
                else:
                    return False
            elif not self._is_core_tile(pos):
                dbg(
                    f"r={self.round_no} id={self.my_id} conv rejected: {pos} has {etype.name}",
                )
                return False

        if ct.can_build_conveyor(pos, direction):
            ct.build_conveyor(pos, direction)
            self.connect_last_build_round = self.round_no
            self.connect_stall_recoverable = False
            dbg(f"r={self.round_no} id={self.my_id} conv at {pos} -> {direction.name}")
            return True
        return False

    def _try_bridge_over(
        self,
        ct: Controller,
        from_pos: Position,
        toward: Position,
    ) -> bool:
        """Try to build a bridge from from_pos jumping over an obstacle."""
        if ct.get_action_cooldown() != 0:
            return False
        if self.my_pos is None or self.my_pos.distance_squared(from_pos) > 2:
            return False

        titanium, _ = ct.get_global_resources()
        bridge_cost = ct.get_bridge_cost()[0]
        if titanium < bridge_cost:
            self.connect_last_build_round = self.round_no  # Ti wait ≠ stall
            return False

        # Reject if a foreign conveyor could feed into the bridge source.
        if self._has_incoming_foreign_conveyor(ct, from_pos):
            return False

        # Clear own road or sector-claim marker at bridge source if needed
        info = self.visible_buildings.get(from_pos)
        if info is not None:
            _, etype, team = info
            if team == self.my_team and etype in {EntityType.ROAD, EntityType.MARKER}:
                if ct.can_destroy(from_pos):
                    ct.destroy(from_pos)
                    self.visible_buildings.pop(from_pos, None)
                else:
                    return False
            elif etype in WALKABLE_BUILDINGS or (
                etype == EntityType.CORE and team == self.my_team
            ):
                return False

        from_dist = from_pos.distance_squared(toward)
        best_landing = None
        best_score = float("inf")

        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx == 0 and dy == 0:
                    continue
                dist_sq = dx * dx + dy * dy
                if dist_sq > BRIDGE_MAX_DIST_SQ:
                    continue
                landing = Position(from_pos.x + dx, from_pos.y + dy)
                if not self._in_bounds(landing):
                    continue
                if self._classify_tile(landing) != "free":
                    continue
                if landing == self.connect_harvester_pos:
                    continue
                landing_dist = landing.distance_squared(toward)
                if landing_dist >= from_dist:
                    continue  # Must make progress toward core
                # Reject landings where a foreign conveyor could feed into them.
                if self._has_incoming_foreign_conveyor(ct, landing):
                    continue
                # Score: minimize distance to core, prefer longer jumps
                score = landing_dist - dist_sq * 0.1
                if score < best_score:
                    best_score = score
                    best_landing = landing

        if best_landing is None:
            return False

        if ct.can_build_bridge(from_pos, best_landing):
            ct.build_bridge(from_pos, best_landing)
            self.connect_last_build_round = self.round_no
            self.connect_stall_recoverable = False
            self.current_chain.append(from_pos)
            self.chain_end = best_landing
            dbg(
                f"r={self.round_no} id={self.my_id} bridge {from_pos} -> {best_landing}",
            )
            return True
        return False

    def _closest_core_tile(self, pos: Position) -> Position | None:
        if self.core_pos is None:
            return None
        best, best_dist = None, float("inf")
        cx, cy = self.core_pos.x, self.core_pos.y
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                ct_pos = Position(cx + dx, cy + dy)
                d = pos.distance_squared(ct_pos)
                if d < best_dist:
                    best_dist = d
                    best = ct_pos
        return best

    def _is_core_tile(self, pos: Position) -> bool:
        if self.core_pos is None:
            return False
        return abs(pos.x - self.core_pos.x) <= 1 and abs(pos.y - self.core_pos.y) <= 1

    def _is_enemy_core_tile(self, pos: Position) -> bool:
        if self.enemy_core_pos is None:
            return False
        return (
            abs(pos.x - self.enemy_core_pos.x) <= 1
            and abs(pos.y - self.enemy_core_pos.y) <= 1
        )

    def _nearest_unsaturated_terminal(self, pos: Position) -> Position | None:
        """Return nearest unsaturated tree node or core tile to pos.

        Tree nodes belonging to trees with >= MAX_HARVESTERS_PER_TREE are skipped.
        Core tiles are always included (connecting there starts a new tree).
        """
        best: Position | None = None
        best_dist = float("inf")
        for tp in self.my_tree:
            tree_id = self.tree_ids.get(tp)
            if (
                tree_id is not None
                and self.tree_harvester_counts[tree_id] >= MAX_HARVESTERS_PER_TREE
            ):
                continue
            d = pos.distance_squared(tp)
            if d < best_dist:
                best_dist = d
                best = tp
        if self.core_pos is not None:
            cx, cy = self.core_pos.x, self.core_pos.y
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    cp = Position(cx + dx, cy + dy)
                    d = pos.distance_squared(cp)
                    if d < best_dist:
                        best_dist = d
                        best = cp
        return best

    def _find_adjacent_terminal(
        self,
        pos: Position,
    ) -> tuple[Position, Direction] | None:
        """Return (neighbor, direction) if pos is cardinally adjacent to a terminal.

        Prefer unsaturated tree nodes, then core tiles. Skips saturated trees.
        """
        best = None
        for d in CARDINALS:
            dx, dy = DIRECTION_DELTA[d]
            neighbor = Position(pos.x + dx, pos.y + dy)
            if neighbor in self.my_tree:
                tree_id = self.tree_ids.get(neighbor)
                if (
                    tree_id is not None
                    and self.tree_harvester_counts[tree_id] >= MAX_HARVESTERS_PER_TREE
                ):
                    continue  # saturated
                return (neighbor, d)
            if best is None and self._is_core_tile(neighbor):
                best = (neighbor, d)
        return best

    def _finish_connect(
        self,
        success: bool = False,
        terminal: Position | None = None,
    ) -> None:
        if success:
            self.my_tree.update(self.current_chain)
            # Determine which tree this chain belongs to.
            tree_id = None
            if terminal is not None and terminal in self.tree_ids:
                existing_id = self.tree_ids[terminal]
                if self.tree_harvester_counts[existing_id] < MAX_HARVESTERS_PER_TREE:
                    tree_id = existing_id
            if tree_id is None:
                # New tree (connected to core or unknown terminal).
                tree_id = len(self.tree_harvester_counts)
                self.tree_harvester_counts.append(0)
            self.tree_harvester_counts[tree_id] += 1
            for pos in self.current_chain:
                self.tree_ids[pos] = tree_id
            if terminal is not None:
                self.tree_ids[terminal] = tree_id
            dbg(
                f"r={self.round_no} id={self.my_id} tree#{tree_id} now has {self.tree_harvester_counts[tree_id]} harvesters",
            )
        self.current_chain.clear()
        self.connecting = False
        self.connect_turns = 0
        self.connect_last_build_round = 0
        self.connect_stall_recoverable = False
        self.connect_harvester_pos = None
        self.chain_end = None
        self.connect_target = None
        self.connect_plan = None
        self.connect_plan_idx = 0
        self.connect_unwind_destroy = None
        self.connect_attack_pos = None

    # ------------------------------------------------------------------
    # Healing patrol
    # ------------------------------------------------------------------

    def _run_heal_patrol(self, ct: Controller) -> None:
        """Walk along own tree, healing damaged buildings."""
        if ct.get_action_cooldown() == 0:
            for pos in self._nearby_tree_positions():
                if self.my_pos.distance_squared(pos) <= 2 and ct.can_heal(pos):
                    ct.heal(pos)
                    dbg(f"r={self.round_no} id={self.my_id} heal patrol at {pos}")
                    return

        if (
            self.heal_target is None
            or self.my_pos.distance_squared(self.heal_target) <= 2
        ):
            self.heal_target = self._pick_heal_target()

        if self.heal_target is not None:
            self._walk_toward(ct, self.heal_target, best_effort=True)

    def _pick_heal_target(self) -> Position | None:
        """Pick a tree node to patrol toward. Cycles through nodes, preferring
        ones we haven't been near recently (far from current position).
        """
        if not self.my_tree or self.my_pos is None:
            return None
        # Pick a random tree node that's at least 5 tiles away.
        # This spreads patrol coverage instead of always bouncing to extremes.
        candidates = [p for p in self.my_tree if self.my_pos.distance_squared(p) > 25]
        if candidates:
            return random.choice(candidates)
        # All tree nodes are close — pick any.
        return random.choice(list(self.my_tree)) if self.my_tree else None

    def _nearby_tree_positions(self) -> list[Position]:
        """Tree positions within vision radius (dist^2 <= 20)."""
        if self.my_pos is None:
            return []
        return [p for p in self.my_tree if self.my_pos.distance_squared(p) <= 20]

    # ------------------------------------------------------------------
    # Sector claiming
    # ------------------------------------------------------------------

    def _update_sector_claims(self, ct: Controller) -> None:
        """Ingest nearby sector claim markers from allied builders."""
        for eid, etype, team in self.visible_buildings.values():
            if etype != EntityType.MARKER or team != self.my_team:
                continue
            try:
                val = ct.get_marker_value(eid)
            except Exception:
                continue
            opcode, rnd, owner_id, sector = decode_sector(val)
            if opcode != OPCODE_SECTOR:
                continue
            age = (self.round_no - rnd) & 0x7FF
            if age > SECTOR_CLAIM_TTL:
                continue
            existing = self.sector_claims.get(sector)
            if existing is None or owner_id < existing[0]:
                self.sector_claims[sector] = (owner_id, rnd)

    def _claim_sector(self, ct: Controller) -> None:
        """Pick / maintain a sector and place a claim marker."""
        if self.core_pos is None or self.my_pos is None:
            return

        # Initial pick: random sector to spread builders out.
        if self.sector_index < 0:
            self.sector_index = random.randint(0, 3)
            dbg(f"r={self.round_no} id={self.my_id} initial sector={self.sector_index}")

        # Yield if a lower-ID builder claims our sector.
        claim = self.sector_claims.get(self.sector_index)
        if claim is not None and claim[0] < self.my_id:
            for offset in range(1, 4):
                candidate = (self.sector_index + offset) % 4
                other = self.sector_claims.get(candidate)
                if other is None or other[0] >= self.my_id:
                    dbg(
                        f"r={self.round_no} id={self.my_id} yield sector {self.sector_index}→{candidate}",
                    )
                    self.sector_index = candidate
                    self.explore_radius_step = 0
                    self.explore_target = None
                    break

        if self.round_no > 10 and self.round_no % 5 != (self.my_id or 0) % 5:
            return  # sector claims every 5 turns, staggered by builder id. Every turn for first 10.
        marker_val = encode_sector(self.round_no, self.my_id, self.sector_index)

        if ct.can_place_marker(self.my_pos):
            ct.place_marker(self.my_pos, marker_val)
        else:
            for d in ALL_DIRECTIONS:
                adj = self.my_pos.add(d)
                if ct.can_place_marker(adj):
                    ct.place_marker(adj, marker_val)
                    break

    # ------------------------------------------------------------------
    # Exploration
    # ------------------------------------------------------------------

    def _explore(self, ct: Controller) -> None:
        if (
            self.explore_target is None
            or self.my_pos.distance_squared(self.explore_target) <= 8
        ):
            if self.explore_target is not None:
                self.explore_radius_step += 1
            self.explore_target = self._sector_explore_target()
            if self.explore_target is None:
                self.explore_target = self._random_explore_target()

        if self.explore_target is not None:
            dbg(
                f"r={self.round_no} id={self.my_id} sector={self.sector_index} exploring toward {self.explore_target}",
            )
            if not self._walk_toward(ct, self.explore_target, best_effort=True):
                self.explore_target = None
        else:
            # Nothing to explore — patrol our tree and heal.
            self._run_heal_patrol(ct)

    # Sector edge directions: left and right boundaries of each quadrant.
    # NE: north edge to east edge. SE: east to south. SW: south to west. NW: west to north.
    SECTOR_EDGES = [
        ((0, -1), (1, 0)),  # NE
        ((1, 0), (0, 1)),  # SE
        ((0, 1), (-1, 0)),  # SW
        ((-1, 0), (0, -1)),  # NW
    ]

    def _sector_explore_target(self) -> Position | None:
        """Sweep sector with density scaling by radius.

        Each radius band has enough waypoints to keep ~8 tile spacing along
        the arc: max(3, radius // 4) points interpolated between left and
        right edges. Returns None when sector is exhausted.
        """
        if self.core_pos is None or self.sector_index < 0:
            return None
        left, right = self.SECTOR_EDGES[self.sector_index]
        max_radius = max(self.map_w or 40, self.map_h or 40)

        # Walk through radius bands, consuming explore_radius_step.
        # Cap iterations to avoid burning CPU on large maps.
        step = self.explore_radius_step
        radius = 8
        skipped = 0
        while radius <= max_radius and skipped < 12:
            n_points = max(3, radius // 4)
            if step < n_points:
                # Interpolate between left and right edges.
                t = step / max(1, n_points - 1)  # 0.0 = left, 1.0 = right
                lx, ly = left[0] * radius, left[1] * radius
                rx, ry = right[0] * radius, right[1] * radius
                dx = lx + (rx - lx) * t
                dy = ly + (ry - ly) * t
                tx = int(self.core_pos.x + dx)
                ty = int(self.core_pos.y + dy)
                # Skip waypoints that are out of bounds — don't clamp to edge.
                if self.map_w and (tx < 0 or tx >= self.map_w):
                    self.explore_radius_step += 1
                    step += 1
                    skipped += 1
                    continue
                if self.map_h and (ty < 0 or ty >= self.map_h):
                    self.explore_radius_step += 1
                    step += 1
                    skipped += 1
                    continue
                target = Position(tx, ty)
                if self.enemy_core_pos is not None and self._in_enemy_half(target):
                    self.explore_radius_step += 1
                    step += 1
                    skipped += 1
                    continue
                return target
            step -= n_points
            radius += 5
        return None

    def _random_explore_target(self) -> Position | None:
        """Pick an unseen point on our half. Returns None if our half looks explored."""
        if self.map_w is None or self.map_h is None:
            return None
        # Quick check: if we've seen most of the map, skip sampling.
        total_tiles = self.map_w * self.map_h
        if len(self.tile_env) > total_tiles * 3 // 4:
            return None
        for _ in range(15):
            x = random.randint(0, self.map_w - 1)
            y = random.randint(0, self.map_h - 1)
            target = Position(x, y)
            if self._in_enemy_half(target):
                continue
            if target not in self.tile_env:
                return target
        return None

    # ------------------------------------------------------------------
    # Ore picking
    # ------------------------------------------------------------------

    def _pick_ore(self) -> Position | None:
        if not self.known_ores or self.my_pos is None:
            return None
        best: Position | None = None
        best_score = float("inf")
        for ore in self.known_ores:
            if ore in self.claimed_ores:
                continue
            info = self.visible_buildings.get(ore)
            if info is not None:
                _, etype, team = info
                if etype == EntityType.HARVESTER:
                    if team == self.my_team:
                        self.claimed_ores.add(ore)
                    continue  # skip any harvester, own or enemy
                if team != self.my_team:
                    continue  # skip any enemy building

            # Econ builders stay on own half.
            if self._in_enemy_half(ore):
                continue

            my_dist = self.my_pos.distance_squared(ore)

            ally_closer = False
            for ally_pos in self.visible_allies.values():
                if ally_pos.distance_squared(ore) < my_dist:
                    ally_closer = True
                    break
            if ally_closer:
                continue

            connect_ref = self._nearest_unsaturated_terminal(ore)
            if connect_ref is None:
                connect_ref = self.core_pos
            connect_dist = ore.distance_squared(connect_ref) if connect_ref else 0
            # Skip ores too far to connect efficiently.
            if connect_dist > MAX_ORE_CONNECT_DIST_SQ:
                continue
            score = my_dist + connect_dist * 2
            # Mild preference for ores within our sector.
            if self.sector_index >= 0 and self.core_pos is not None:
                sx, sy = SECTOR_OFFSETS[self.sector_index]
                odx = ore.x - self.core_pos.x
                ody = ore.y - self.core_pos.y
                in_sector = (odx * sx >= 0) and (ody * sy >= 0)
                if in_sector:
                    score = int(score * 0.7)

            if score < best_score:
                best_score = score
                best = ore
        return best

    # ------------------------------------------------------------------
    # Passability callbacks for nav
    # ------------------------------------------------------------------

    def _is_passable(self, pos: Position, ct: Controller) -> bool:
        """Can the bugnav simulation step here?

        Returns True for visible tiles that are not walls, not blocked by
        impassable buildings, and not currently occupied by another unit.
        Buildings (including core) are checked before unit-occupancy so that
        a unit standing on a walkable building does not make the tile appear
        impassable (the core entity is itself a unit returned by get_nearby_units).
        """
        if not self._in_bounds(pos):
            return False
        if self._is_enemy_core_tile(pos):
            return False
        env = self.tile_env.get(pos)
        if env is None:
            return False
        if env == Environment.WALL:
            return False
        info = self.visible_buildings.get(pos)
        if info is not None:
            _, etype, team = info
            if etype in {EntityType.ROAD, EntityType.MARKER}:
                return True
            if etype in WALKABLE_BUILDINGS:
                return True
            return bool(etype == EntityType.CORE and team == self.my_team)
        # Empty tile — block if another mobile unit is standing here.
        return pos not in self.visible_unit_positions

    def _is_possibly_passable(self, pos: Position) -> bool:
        """Could this tile be passable? Unseen tiles count as yes."""
        if not self._in_bounds(pos):
            return False
        if self._is_enemy_core_tile(pos):
            return False
        env = self.tile_env.get(pos)
        if env is None:
            return True
        if env == Environment.WALL:
            return False
        info = self.visible_buildings.get(pos)
        if info is not None:
            _, etype, team = info
            if etype in {EntityType.ROAD, EntityType.MARKER}:
                return True
            if etype in WALKABLE_BUILDINGS:
                return True
            return bool(etype == EntityType.CORE and team == self.my_team)
        return True

    def _in_enemy_half(self, pos: Position) -> bool:
        """True if pos is on the enemy side and not peripheral enough to contest.

        Strict midline: d_enemy < d_own. But peripheral ores (far from both
        cores) get tolerance proportional to min(d_own, d_enemy), allowing
        econ builders to contest ores that neither side owns cheaply.
        """
        if self.core_pos is None or self.enemy_core_pos is None:
            return False
        d_own = pos.distance_squared(self.core_pos)
        d_enemy = pos.distance_squared(self.enemy_core_pos)
        tolerance = int(min(d_own, d_enemy) * OWN_SIDE_SLIPPAGE)
        return d_enemy < d_own - tolerance

    def _in_bounds(self, pos: Position) -> bool:
        if self.map_w is None or self.map_h is None:
            return True
        return 0 <= pos.x < self.map_w and 0 <= pos.y < self.map_h
