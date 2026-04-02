"""Titanium economy bot.

Every unit (core and builders) runs the same Player instance. The core
spawns builders; builders find ore, build harvesters, and connect them back
to core via bridge/conveyor chains.  Connect-back routes around bare ore
tiles so future harvesters aren't blocked.

Builder state machine (all builders use the same generalist waterfall):
  1. SEEK_ORE        — pick nearest unclaimed Ti ore and walk to it
  2. BUILD_HARVESTER — adjacent to ore, build harvester
  3. CONNECT_BACK    — lay conveyor chain from harvester back to core/tree
  4. SENTINEL        — after 2nd+ connection, place defensive sentinel near harvester
  5. EXPLORE         — no visible ore, wander to discover new deposits
"""

from __future__ import annotations

import contextlib
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

CONNECT_STALL_LIMIT = 40
DEFENSE_RESERVE_SETS = 1  # reserve Ti for this many gunner+splitter combos
MAX_HARVESTERS_PER_TREE = 4

# Max squared connection distance from nearest tree node / core when picking ore.
# Prevents claiming ores that would require extremely long chains.
MAX_ORE_CONNECT_DIST_SQ = 900  # 30 tiles

# Peripheral ore slippage: econ builders push past midline for ores far from
# both cores. Tolerance = min(d_own, d_enemy) * SLIPPAGE.  0.3 ≈ allows ~17%
# past midline for equidistant ores, blocks deep enemy territory.
OWN_SIDE_SLIPPAGE = 0.3


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

        # Builder state
        self.target_ore: Position | None = None
        self.explore_target: Position | None = None
        # Walk cache (rebuilt once per turn for A* walk)
        self._walk_cache_round: int = -1
        self._wc_walls: set[tuple[int, int]] = set()
        self._wc_blocked: set[tuple[int, int]] = set()
        self._wc_known: set[tuple[int, int]] = set()
        self._wc_units: set[tuple[int, int]] = set()
        self._wc_enemy_core: set[tuple[int, int]] = set()
        self._wc_danger: set[tuple[int, int]] = set()

        # Tree state (persists across connect-backs)
        self.my_tree: set[Position] = set()
        self.my_chain_dirs: dict[Position, Direction] = {}  # pos → conveyor direction
        self.tree_ids: dict[Position, int] = {}  # node → tree index
        self.tree_harvester_counts: list[int] = []  # harvester count per tree

        # Offensive attack state
        self._attack_target: Position | None = None
        self._attack_gunner_pos: Position | None = None
        self._attack_gunner_dir: Direction | None = None
        self._attack_ore: Position | None = None  # ore to build harvester for ammo

        # Task commitment
        self.task: str = "idle"  # "seek_ore", "connect", "idle", "attack"
        self.suspended_task: str | None = None
        self.suspended_state: dict | None = None

        # Healing state
        self.heal_target: Position | None = None
        self.damaged_turns: dict[
            Position,
            int,
        ] = {}  # pos → turns seen with 1-3 HP missing

        # Reactive gunner placement state
        self.gunner_build: dict | None = None  # active gunner build task
        # Chain repair state
        self._repair_target: Position | None = None

        # Stuck detection for _walk_toward
        self._stuck_target: Position | None = None
        self._stuck_turns: int = 0

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
        self.connect_unwind_destroy: Position | None = None

        # Post-harvest sentinel placement
        self._pending_sentinel_harvester: Position | None = None
        self._sentinels_placed: int = 0
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
        elif etype == EntityType.LAUNCHER:
            self._run_launcher(ct)
        elif etype == EntityType.GUNNER:
            self._run_gunner(ct)
        elif etype == EntityType.BUILDER_BOT:
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
            # Cache direction for all friendly directional buildings (for chain repair).
            if team == self.my_team and etype in {
                EntityType.CONVEYOR,
                EntityType.SPLITTER,
                EntityType.ARMOURED_CONVEYOR,
            }:
                with contextlib.suppress(Exception):
                    self.my_chain_dirs[pos] = ct.get_direction(eid)
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
            elif etype == EntityType.HARVESTER:
                # Don't shoot harvesters feeding any of our turrets.
                hpos = ct.get_position(eid)
                feeds_ours = False
                for hdx, hdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    adj = Position(hpos.x + hdx, hpos.y + hdy)
                    ainfo = self.visible_buildings.get(adj)
                    if (
                        ainfo is not None
                        and ainfo[2] == my_team
                        and ainfo[1]
                        in {
                            EntityType.SENTINEL,
                            EntityType.GUNNER,
                            EntityType.BREACH,
                        }
                    ):
                        feeds_ours = True
                        break
                if feeds_ours:
                    continue
                priority = 3
            else:
                continue  # barriers, markers, etc.
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
    # Launcher fire control
    # ------------------------------------------------------------------

    def _run_launcher(self, ct: Controller) -> None:
        """Throw adjacent enemy builder bots away from our core."""
        if self.my_pos is None or ct.get_action_cooldown() != 0:
            return

        # Find adjacent enemy bots.
        enemy_bots: list[Position] = []
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == self.my_team:
                continue
            upos = ct.get_position(uid)
            if self.my_pos.distance_squared(upos) <= 2:
                enemy_bots.append(upos)

        if not enemy_bots:
            return

        # Try to throw each enemy bot, preferring throw targets far from our core.
        core = self.core_pos
        map_w = self.map_w or 50
        map_h = self.map_h or 50
        for bot_pos in enemy_bots:
            best_target = None
            best_dist = -1
            # Sample candidate targets within throw range r²=26.
            for tx in range(max(0, self.my_pos.x - 5), min(map_w, self.my_pos.x + 6)):
                for ty in range(
                    max(0, self.my_pos.y - 5),
                    min(map_h, self.my_pos.y + 6),
                ):
                    tp = Position(tx, ty)
                    if self.my_pos.distance_squared(tp) > 26:
                        continue
                    d = tp.distance_squared(core) if core else 0
                    if d > best_dist and ct.can_launch(bot_pos, tp):
                        best_dist = d
                        best_target = tp
            if best_target is not None:
                ct.launch(bot_pos, best_target)
                dbg(
                    f"r={self.round_no} id={self.my_id} launcher threw bot from {bot_pos} to {best_target}",
                )
                return

    # ------------------------------------------------------------------
    # Gunner fire control
    # ------------------------------------------------------------------

    _GUNNER_TARGET_PRIORITY = {
        EntityType.SENTINEL: 50,
        EntityType.GUNNER: 50,
        EntityType.BREACH: 50,
        EntityType.LAUNCHER: 40,
        EntityType.CONVEYOR: 20,
        EntityType.BRIDGE: 20,
        EntityType.SPLITTER: 20,
        EntityType.ARMOURED_CONVEYOR: 20,
        EntityType.HARVESTER: 15,
        EntityType.ROAD: 5,
    }

    def _run_gunner(self, ct: Controller) -> None:
        """Fire at highest-priority enemy target in range."""
        if self.my_pos is None or ct.get_action_cooldown() != 0:
            return

        best_target = None
        best_prio = -1
        for tile in ct.get_attackable_tiles():
            if not ct.can_fire(tile):
                continue
            info = self.visible_buildings.get(tile)
            if info is not None and info[2] != self.my_team:
                prio = self._GUNNER_TARGET_PRIORITY.get(info[1], 1)
                if prio > best_prio:
                    best_prio = prio
                    best_target = tile
            # Also target enemy bots on the tile.
            elif tile in self.visible_unit_positions:
                for uid in ct.get_nearby_units():
                    if (
                        ct.get_team(uid) != self.my_team
                        and ct.get_position(uid) == tile
                    ):
                        if best_prio < 10:
                            best_prio = 10
                            best_target = tile
                        break

        if best_target is not None:
            ct.fire(best_target)
            dbg(
                f"r={self.round_no} id={self.my_id} gunner fire at {best_target} prio={best_prio}",
            )
            return

        # No target in current facing — try rotating 45° CW or CCW.
        # Only rotate if we have ammo (stored resource). No point rotating without ammo.
        try:
            if ct.get_stored_resource() is None:
                return  # no ammo — don't waste Ti on rotation
        except Exception:
            pass
        current_dir = ct.get_direction()
        ci = ALL_DIRECTIONS.index(current_dir)
        best_rot_dir = None
        best_rot_prio = -1
        for rot in [(ci + 1) % 8, (ci - 1) % 8]:
            d = ALL_DIRECTIONS[rot]
            for tile in ct.get_attackable_tiles_from(self.my_pos, d, EntityType.GUNNER):
                info = self.visible_buildings.get(tile)
                if info is not None and info[2] != self.my_team:
                    if not ct.can_fire_from(self.my_pos, d, EntityType.GUNNER, tile):
                        continue
                    prio = self._GUNNER_TARGET_PRIORITY.get(info[1], 1)
                    if prio > best_rot_prio:
                        best_rot_prio = prio
                        best_rot_dir = d
                    break
        if best_rot_dir is not None:
            titanium, _ = ct.get_global_resources()
            if titanium >= 10 and ct.get_action_cooldown() == 0:
                try:
                    ct.rotate(best_rot_dir)
                    dbg(
                        f"r={self.round_no} id={self.my_id} gunner rotate {current_dir.name}->{best_rot_dir.name} prio={best_rot_prio}",
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _run_core(self, ct: Controller) -> None:
        if ct.get_action_cooldown() != 0:
            return

        titanium, _ = ct.get_global_resources()
        builder_cost = ct.get_builder_bot_cost()[0]
        harvester_cost = ct.get_harvester_cost()[0]
        conveyor_cost = ct.get_conveyor_cost()[0]

        alive_builders = ct.get_unit_count() - 1  # subtract core

        # Emergency spawn: if enemy bots near core, spawn defender immediately.
        enemy_near = 0
        for eid in ct.get_nearby_units():
            if ct.get_team(eid) != self.my_team:
                enemy_near += 1
        if enemy_near > 0 and titanium >= builder_cost:
            for direction in ALL_DIRECTIONS:
                spawn_pos = self.my_pos.add(direction)
                if ct.can_spawn(spawn_pos):
                    ct.spawn_builder(spawn_pos)
                    self.num_spawned += 1
                    dbg(
                        f"r={self.round_no} core EMERGENCY spawn #{self.num_spawned} at {spawn_pos} (enemy_near={enemy_near})",
                    )
                    return

        # Reserve scales with alive builders. Even first 4 need runway.
        per_econ_reserve = harvester_cost + conveyor_cost * 5
        if alive_builders < 4:
            # First 4: need builder cost + reserve for existing builders.
            reserve = per_econ_reserve * max(1, alive_builders)
            if titanium < builder_cost + reserve:
                return
        else:
            # Beyond 4: steeper — 2x builder cost + scaled reserve.
            econ_builders = min(4, alive_builders)
            extra_builders = max(0, alive_builders - 4)
            per_extra_reserve = ct.get_sentinel_cost()[0]
            reserve = (
                per_econ_reserve * econ_builders + per_extra_reserve * extra_builders
            )
            if titanium < builder_cost * 2 + reserve:
                return

        for direction in ALL_DIRECTIONS:
            spawn_pos = self.my_pos.add(direction)
            if ct.can_spawn(spawn_pos):
                ct.spawn_builder(spawn_pos)
                self.num_spawned += 1
                dbg(f"r={self.round_no} core spawn #{self.num_spawned} at {spawn_pos}")
                return

    # ------------------------------------------------------------------
    # Builder state machine
    # ------------------------------------------------------------------

    def _run_builder(self, ct: Controller) -> None:
        if self.my_pos is None:
            return

        # Maintain sector ownership every turn.
        self._update_sector_claims(ct)
        self._claim_sector(ct)

        # Track persistent minor damage for trickle-attack detection.
        self._update_damaged_turns(ct)

        # Active gunner build takes priority over everything.
        if self.gunner_build is not None and self._continue_gunner_build(ct):
            return

        # Check for enemy turret threats — higher priority than healing symptom.
        if self.gunner_build is None and self._check_for_threats(ct):
            return

        # Opportunistic healing: heal adjacent damaged friendly buildings.
        if ct.get_action_cooldown() == 0 and self._try_heal(ct):
            return

        # Chain repair: detect gaps in own tree and rebuild.
        if self.task != "connect" and self._check_chain_repair(ct):
            return

        # If connecting back, continue that
        if self.connecting:
            self._run_connect_back(ct)
            return

        # Defensive turrets disabled — rely on reactive gunner placement
        # from _check_for_threats when enemies actually attack.
        self._pending_sentinel_harvester = None

        # Keep existing ore target if still valid. Only re-pick when None.
        if self.target_ore is not None:
            # Check if target was claimed by someone else.
            info = self.visible_buildings.get(
                self.target_ore,
            ) or self.known_buildings.get(self.target_ore)
            if info is not None and info[1] == EntityType.HARVESTER:
                self.claimed_ores.add(self.target_ore)
                self.target_ore = None
                self.task = "idle"
        if self.target_ore is None:
            self.target_ore = self._pick_ore()
            if self.target_ore is not None:
                self.task = "seek_ore"
                dbg(
                    f"r={self.round_no} id={self.my_id} task=seek_ore ore={self.target_ore}",
                )

        if self.target_ore is not None:
            dist_sq = self.my_pos.distance_squared(self.target_ore)
            if dist_sq == 0:
                # If enemy road on our ore, fire at it to clear.
                einfo = self.visible_buildings.get(self.target_ore)
                if (
                    einfo is not None
                    and einfo[2] != self.my_team
                    and einfo[1] == EntityType.ROAD
                ):
                    if ct.get_action_cooldown() == 0 and ct.can_fire(self.my_pos):
                        ct.fire(self.my_pos)
                        dbg(
                            f"r={self.round_no} id={self.my_id} fire at enemy road on ore {self.target_ore}",
                        )
                    return
                self._step_off_ore(ct)
                return
            if dist_sq <= 2:
                # If enemy road on ore, walk onto it to clear.
                einfo = self.visible_buildings.get(self.target_ore)
                if (
                    einfo is not None
                    and einfo[2] != self.my_team
                    and einfo[1] == EntityType.ROAD
                ):
                    dbg(
                        f"r={self.round_no} id={self.my_id} walk onto enemy road at ore {self.target_ore}",
                    )
                    if (
                        not self._walk_toward(ct, self.target_ore)
                        and self._stuck_turns >= 5
                    ):
                        dbg(
                            f"r={self.round_no} id={self.my_id} abandon ore {self.target_ore} (stuck on enemy road)",
                        )
                        self.target_ore = None
                        self.task = "idle"
                    return
                self._try_build_harvester(ct)
                return
            self.explore_target = None
            dbg(
                f"r={self.round_no} id={self.my_id} walk to ore {self.target_ore} dist²={dist_sq}",
            )
            if not self._walk_toward(ct, self.target_ore):
                if self._stuck_turns >= 5:
                    dbg(
                        f"r={self.round_no} id={self.my_id} abandon ore {self.target_ore} (stuck {self._stuck_turns} turns)",
                    )
                    self.target_ore = None
                    self.task = "idle"
            return

        # No ore — explore to find more.
        self._explore(ct)

    # ------------------------------------------------------------------
    # Sentinel placement (post-harvest defense)
    # ------------------------------------------------------------------

    def _try_place_harvester_sentinel(self, ct: Controller) -> bool:
        """Place a sentinel adjacent to our harvester. Returns True if busy.

        Harvester feeds sentinel directly via adjacency — no splitter needed.
        Uses gunner_build state machine for walking + Ti wait + placement.
        """
        harv = self._pending_sentinel_harvester
        if harv is None or self.my_pos is None:
            return False
        # Check harvester still exists.
        info = self.visible_buildings.get(harv) or self.known_buildings.get(harv)
        if info is None or info[1] != EntityType.HARVESTER:
            self._pending_sentinel_harvester = None
            return False

        # Find the chain side: which cardinal neighbor of harvester has our conveyor.
        chain_dx, chain_dy = 0, 0
        for cdx, cdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            cpos = Position(harv.x + cdx, harv.y + cdy)
            cinfo = self.visible_buildings.get(cpos) or self.known_buildings.get(cpos)
            if (
                cinfo is not None
                and cinfo[2] == self.my_team
                and cinfo[1]
                in {
                    EntityType.CONVEYOR,
                    EntityType.SPLITTER,
                    EntityType.BRIDGE,
                    EntityType.ARMOURED_CONVEYOR,
                }
            ):
                chain_dx, chain_dy = cdx, cdy
                break

        # Pick best cardinal neighbor. Prefer diagonal to chain tile for coverage.
        best_pos = None
        best_score = -999
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            spos = Position(harv.x + dx, harv.y + dy)
            if self.core_pos is not None and spos.distance_squared(self.core_pos) <= 8:
                continue
            env = self.tile_env.get(spos)
            if env is None or env == Environment.WALL:
                continue
            if env in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
                continue
            sbld = self.visible_buildings.get(spos) or self.known_buildings.get(spos)
            if sbld is not None:
                _, setype, steam = sbld
                if setype == EntityType.MARKER or (
                    steam == self.my_team and setype == EntityType.ROAD
                ):
                    pass
                else:
                    continue
            score = 0
            # Best: opposite the chain (gunner faces outward, covers diagonals).
            # Second: perpendicular to chain. Worst: same side as chain.
            if chain_dx != 0 or chain_dy != 0:
                if dx == -chain_dx and dy == -chain_dy:
                    # Opposite to chain — best for gunner.
                    score += 20
                elif dx != chain_dx and dy != chain_dy:
                    # Perpendicular — second choice.
                    score += 10
                # Same side as chain — worst (score 0).
            score -= self.my_pos.distance_squared(spos) // 4
            if score > best_score:
                best_score = score
                best_pos = spos

        if best_pos is None:
            self._pending_sentinel_harvester = None
            dbg(
                f"r={self.round_no} id={self.my_id} no sentinel pos for harvester {harv}",
            )
            return False

        # Facing: diagonal toward the two unprotected sides of the harvester.
        # The unprotected sides are the two cardinal neighbors that have neither
        # chain nor sentinel. Face the diagonal that covers both.
        sdx = best_pos.x - harv.x  # sentinel offset from harvester
        sdy = best_pos.y - harv.y
        # The two unprotected sides are the ones perpendicular to both chain and sentinel.
        # Face direction = from sentinel, toward the "gap" = opposite of sentinel offset
        # combined with opposite of chain offset.
        face_dx = -sdx  # toward harvester...
        face_dy = -sdy
        if chain_dx != 0 or chain_dy != 0:
            # Shift to diagonal: combine opposite-sentinel with opposite-chain.
            face_dx = -chain_dx if sdx == 0 else -sdx
            face_dy = -chain_dy if sdy == 0 else -sdy
        facing = DELTA_TO_DIRECTION.get((face_dx, face_dy))
        # Don't face directly at harvester (blocks ammo).
        harv_dir = DELTA_TO_DIRECTION.get((-sdx, -sdy))
        if facing is None or facing == harv_dir:
            # Fallback: 45° off harvester.
            if harv_dir is not None:
                hi = ALL_DIRECTIONS.index(harv_dir)
                facing = ALL_DIRECTIONS[(hi + 1) % 8]
            else:
                facing = Direction.NORTH

        # Use gunner_build state machine — skip splitter phase, direct placement.
        # Place gunner (not sentinel) for better DPS + rotation capability.
        self.gunner_build = {
            "enemy_pos": self.enemy_core_pos or harv,
            "gunner_pos": best_pos,
            "gunner_dir": facing,
            "chain_pos": None,
            "chain_type": EntityType.HARVESTER,  # skip splitter phase
            "phase": 2,  # skip to walk-to-turret
            "start_round": self.round_no,
            "est_turns": 5,
        }
        self._pending_sentinel_harvester = None
        dbg(
            f"r={self.round_no} id={self.my_id} def gunner at {best_pos} facing {facing.name} for harvester {harv}",
        )
        return self._continue_gunner_build(ct)

    _OPP_SENTINEL_WEIGHT = {
        EntityType.SENTINEL: 10,
        EntityType.GUNNER: 10,
        EntityType.BREACH: 10,
        EntityType.LAUNCHER: 10,
        EntityType.CONVEYOR: 2,
        EntityType.BRIDGE: 2,
        EntityType.SPLITTER: 2,
        EntityType.ARMOURED_CONVEYOR: 2,
        EntityType.HARVESTER: 3,
    }

    def _eval_sentinel_placement(
        self,
        ct: Controller,
        harv_pos: Position,
    ) -> tuple[Position, Direction] | None:
        """Score all (tile, facing) combos adjacent to an enemy harvester.

        Called when builder is near the harvester with full vision.
        Returns (pos, direction) or None.
        """
        # Core direction for tiebreaking.
        core_dx, core_dy = 0.0, 0.0
        if self.enemy_core_pos is not None:
            cdx = self.enemy_core_pos.x - harv_pos.x
            cdy = self.enemy_core_pos.y - harv_pos.y
            mag = max(1.0, (cdx * cdx + cdy * cdy) ** 0.5)
            core_dx, core_dy = cdx / mag, cdy / mag

        best_pos = None
        best_dir = None
        best_score = -999
        for pdx, pdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            spos = Position(harv_pos.x + pdx, harv_pos.y + pdy)
            env = self.tile_env.get(spos)
            if env is None or env == Environment.WALL:
                continue
            if env in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
                continue
            bld = self.visible_buildings.get(spos)
            if bld is not None:
                _, betype, bteam = bld
                if betype in (EntityType.MARKER, EntityType.ROAD) or (
                    bteam != self.my_team
                    and betype
                    in {
                        EntityType.CONVEYOR,
                        EntityType.BRIDGE,
                        EntityType.SPLITTER,
                        EntityType.ARMOURED_CONVEYOR,
                    }
                ):
                    pass
                else:
                    continue
            harv_dir = DELTA_TO_DIRECTION.get(
                (harv_pos.x - spos.x, harv_pos.y - spos.y),
            )
            for d in ALL_DIRECTIONS:
                if d == harv_dir:
                    continue  # can't face toward ammo source
                score = 0
                hits_core = False
                for tile in ct.get_attackable_tiles_from(spos, d, EntityType.SENTINEL):
                    if self.enemy_core_pos is not None and not hits_core:
                        if tile == self.enemy_core_pos:
                            score += 30  # core LoS is very high value
                            hits_core = True
                            continue
                    tinfo = self.visible_buildings.get(tile)
                    if tinfo is not None and tinfo[2] != self.my_team:
                        score += self._OPP_SENTINEL_WEIGHT.get(tinfo[1], 0)
                # Heavy core direction bias — offensive sentinels should pressure core.
                fdx, fdy = DIRECTION_DELTA[d]
                fmag = max(1.0, (fdx * fdx + fdy * fdy) ** 0.5)
                score += (fdx * core_dx + fdy * core_dy) / fmag * 15
                if score > best_score:
                    best_score = score
                    best_pos = spos
                    best_dir = d

        if best_pos is not None and best_dir is not None:
            return best_pos, best_dir
        return None

    def _try_opportunistic_sentinel(self, ct: Controller) -> bool:
        """Place sentinel on exposed enemy harvester while exploring. Returns True if busy."""
        if self.my_pos is None:
            return False
        best_harv = None
        best_dist = 999
        for pos, (_eid, etype, team) in self.visible_buildings.items():
            if team == self.my_team or etype != EntityType.HARVESTER:
                continue
            # Skip Ax harvesters — sentinel needs Ti ammo, not Ax.
            ore_env = self.tile_env.get(pos)
            if ore_env == Environment.ORE_AXIONITE:
                continue
            # Skip if already has our sentinel adjacent (1 per harvester).
            has_sentinel = False
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                adj = Position(pos.x + dx, pos.y + dy)
                ainfo = self.visible_buildings.get(adj) or self.known_buildings.get(adj)
                if (
                    ainfo is not None
                    and ainfo[2] == self.my_team
                    and ainfo[1] == EntityType.SENTINEL
                ):
                    has_sentinel = True
                    break
            if has_sentinel:
                continue
            # Deconflict: only respond if closest ally.
            d = self.my_pos.distance_squared(pos)
            ally_closer = False
            for apos in self.visible_allies.values():
                if apos.distance_squared(pos) < d:
                    ally_closer = True
                    break
            if ally_closer:
                continue
            if d < best_dist:
                best_dist = d
                best_harv = pos
        if best_harv is None:
            return False
        dbg(
            f"r={self.round_no} id={self.my_id} opp sentinel: found enemy harv {best_harv} dist²={best_dist}",
        )
        # Walk to the harvester first. Tile + facing scored at build time
        # (phase 3) when we have full vision of surroundings.
        # Walk toward harvester. Tile + facing evaluated when adjacent.
        self.gunner_build = {
            "enemy_pos": best_harv,
            "gunner_pos": best_harv,  # walk TO harvester; re-eval at arrival
            "gunner_dir": Direction.NORTH,  # placeholder, re-eval'd
            "chain_pos": None,
            "chain_type": EntityType.HARVESTER,
            "phase": 2,  # walk-to-turret phase
            "start_round": self.round_no,
            "est_turns": 10,
            "_is_sentinel": True,
            "_needs_eval": True,  # flag: re-evaluate tile+facing when adjacent
        }
        dbg(
            f"r={self.round_no} id={self.my_id} opportunistic sentinel: walking to enemy harv {best_harv}",
        )
        return self._continue_gunner_build(ct)

    # ------------------------------------------------------------------
    # Offensive gunner attack
    # ------------------------------------------------------------------

    _ATTACK_TARGETS = {
        EntityType.CORE,
        EntityType.SENTINEL,
        EntityType.GUNNER,
        EntityType.BREACH,
        EntityType.LAUNCHER,
        EntityType.HARVESTER,
        EntityType.CONVEYOR,
        EntityType.BRIDGE,
        EntityType.SPLITTER,
        EntityType.ARMOURED_CONVEYOR,
    }

    _ATTACK_TIER = {
        EntityType.CORE: 0,  # always target
        EntityType.SENTINEL: 1,
        EntityType.GUNNER: 1,
        EntityType.BREACH: 1,
        EntityType.LAUNCHER: 1,  # turrets — actively dangerous
        EntityType.HARVESTER: 2,  # cut econ
        EntityType.CONVEYOR: 3,
        EntityType.BRIDGE: 3,
        EntityType.SPLITTER: 3,
        EntityType.ARMOURED_CONVEYOR: 3,  # transport — low priority
    }

    def _find_attack_target(self, ct: Controller) -> Position | None:
        """Find best enemy building to attack. Core > turrets > harvesters > transport.

        Only returns tier 0-1 targets for gunner placement. Tier 2-3 handled by
        opportunistic sentinels — don't waste gunners on low-value targets.
        """
        if self.my_pos is None:
            return None
        best = None
        best_tier = 999
        best_dist = 999
        for pos, (_eid, etype, team) in self.visible_buildings.items():
            if team == self.my_team:
                continue
            tier = self._ATTACK_TIER.get(etype, 999)
            if tier > 2:
                continue  # skip transport — sentinels handle those
            d = self.my_pos.distance_squared(pos)
            if tier < best_tier or (tier == best_tier and d < best_dist):
                best_tier = tier
                best_dist = d
                best = pos
        return best

    def _pick_gunner_for_target(
        self,
        ct: Controller,
        target: Position,
    ) -> tuple[Position | None, Direction | None]:
        """Find a gunner position with LoS to target on seen tiles.

        Only returns positions where ammo can be delivered (at least one
        cardinal neighbor has or could have an ammo source).
        """
        best_pos = None
        best_dir = None
        best_score = -999
        for gx in range(max(0, target.x - 4), min((self.map_w or 50), target.x + 5)):
            for gy in range(
                max(0, target.y - 4),
                min((self.map_h or 50), target.y + 5),
            ):
                gpos = Position(gx, gy)
                if gpos.distance_squared(target) > 13:
                    continue
                if self._is_enemy_core_tile(gpos):
                    continue
                env = self.tile_env.get(gpos)
                if env is None or env == Environment.WALL:
                    continue
                if env in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
                    continue
                ginfo = self.visible_buildings.get(gpos)
                if ginfo is not None and ginfo[1] not in {
                    EntityType.ROAD,
                    EntityType.MARKER,
                }:
                    continue
                # Compute facing.
                dx = target.x - gx
                dy = target.y - gy
                if dx != 0:
                    dx = dx // abs(dx)
                if dy != 0:
                    dy = dy // abs(dy)
                gun_dir = DELTA_TO_DIRECTION.get((dx, dy))
                if gun_dir is None:
                    continue
                if not ct.can_fire_from(gpos, gun_dir, EntityType.GUNNER, target):
                    continue
                # Verify ammo can arrive from at least one non-facing cardinal side.
                fdx, fdy = DIRECTION_DELTA[gun_dir]
                has_ammo_path = False
                for adx, ady in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    if adx == fdx and ady == fdy:
                        continue  # facing side — can't accept
                    apos = Position(gx + adx, gy + ady)
                    aenv = self.tile_env.get(apos)
                    if aenv is not None and aenv != Environment.WALL:
                        has_ammo_path = True
                        break
                if not has_ammo_path:
                    continue
                # Score: prefer positions closer to builder.
                score = -self.my_pos.distance_squared(gpos) if self.my_pos else 0
                if score > best_score:
                    best_score = score
                    best_pos = gpos
                    best_dir = gun_dir
        return best_pos, best_dir

    def _find_ammo_for_gunner(
        self,
        ct: Controller,
        gunner_pos: Position,
        gunner_dir: Direction,
    ) -> dict | None:
        """Find an ammo source for a gunner. Returns dict with source info or None."""
        fdx, fdy = DIRECTION_DELTA[gunner_dir]

        # Check cardinal neighbors of gunner pos (not facing side) for direct ammo.
        for cdx, cdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if cdx == fdx and cdy == fdy:
                continue  # gunner can't accept from facing side
            cpos = Position(gunner_pos.x + cdx, gunner_pos.y + cdy)
            cinfo = self.visible_buildings.get(cpos) or self.known_buildings.get(cpos)
            if cinfo is None:
                continue
            _, cetype, cteam = cinfo
            # Enemy Ti harvester — free ammo if not defended by enemy turrets.
            if cteam != self.my_team and cetype == EntityType.HARVESTER:
                ore_env = self.tile_env.get(cpos)
                if ore_env == Environment.ORE_AXIONITE:
                    continue
                # Check if defended by enemy turrets.
                defended = False
                for tdx, tdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    tpos = Position(cpos.x + tdx, cpos.y + tdy)
                    tinfo = self.visible_buildings.get(tpos)
                    if (
                        tinfo is not None
                        and tinfo[2] != self.my_team
                        and tinfo[1] in self._ENEMY_TURRET_TYPES
                    ):
                        defended = True
                        break
                if defended:
                    continue
                return {"type": "direct", "pos": cpos}
            # Own harvester — free ammo.
            if cteam == self.my_team and cetype == EntityType.HARVESTER:
                return {"type": "direct", "pos": cpos}
            # Own conveyors/splitters NOT direct — they carry resources toward core,
            # not sideways to a gunner. Would need splitter swap (not implemented).

        # No direct ammo — find nearest ammo source to route a chain from.
        # Check: secured enemy Ti harvesters (no build needed) and Ti ore (build harvester).
        best_source = None
        best_dist = 999
        best_type = None

        # Secured enemy harvesters (no enemy turrets adjacent).
        for pos, (_eid, etype, team) in (self.visible_buildings or {}).items():
            if team == self.my_team or etype != EntityType.HARVESTER:
                continue
            ore_env = self.tile_env.get(pos)
            if ore_env == Environment.ORE_AXIONITE:
                continue
            # Check not defended.
            defended = False
            for tdx, tdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                tpos = Position(pos.x + tdx, pos.y + tdy)
                tinfo = self.visible_buildings.get(tpos)
                if (
                    tinfo is not None
                    and tinfo[2] != self.my_team
                    and tinfo[1] in self._ENEMY_TURRET_TYPES
                ):
                    defended = True
                    break
            if defended:
                continue
            d = gunner_pos.distance_squared(pos)
            if d > 100:
                continue
            if d < best_dist:
                best_dist = d
                best_source = pos
                best_type = "enemy_harvester"

        # Ti ore (need to build harvester).
        for ore_pos in self.known_ores:
            oinfo = self.visible_buildings.get(ore_pos) or self.known_buildings.get(
                ore_pos,
            )
            if oinfo is not None:
                continue
            if ore_pos in self.claimed_ores:
                continue
            ore_env = self.tile_env.get(ore_pos)
            if ore_env != Environment.ORE_TITANIUM:
                continue
            d = gunner_pos.distance_squared(ore_pos)
            if d > 100:
                continue
            # Ore is slightly worse than existing harvester (need to build).
            if d + 20 < best_dist:
                best_dist = d + 20
                best_source = ore_pos
                best_type = "ore"

        if best_source is not None:
            return {"type": best_type, "pos": best_source}
        return None

    def _try_start_attack(self, ct: Controller) -> bool:
        """Try to initiate an offensive gunner attack. Returns True if started."""
        if self.my_pos is None:
            return False
        target = self._find_attack_target(ct)
        if target is None:
            return False
        gunner_pos, gunner_dir = self._pick_gunner_for_target(ct, target)
        if gunner_pos is None:
            return False
        ammo = self._find_ammo_for_gunner(ct, gunner_pos, gunner_dir)
        if ammo is None:
            return False

        self._attack_target = target
        self._attack_gunner_pos = gunner_pos
        self._attack_gunner_dir = gunner_dir

        if ammo["type"] == "direct":
            # Ammo adjacent — skip chain, go straight to gunner placement.
            self.gunner_build = {
                "enemy_pos": target,
                "gunner_pos": gunner_pos,
                "gunner_dir": gunner_dir,
                "chain_pos": ammo["pos"],
                "chain_type": EntityType.HARVESTER,  # skip splitter phase
                "phase": 2,
                "start_round": self.round_no,
                "est_turns": 5,
                "_is_attack": True,
            }
            dbg(
                f"r={self.round_no} id={self.my_id} attack: direct gunner at {gunner_pos} -> {target} ammo={ammo['pos']}",
            )
            return self._continue_gunner_build(ct)
        if ammo["type"] == "enemy_harvester":
            # Secured enemy harvester — route chain from it, no build needed.
            self._attack_ore = None  # no harvester to build
            self.task = "attack"
            harv_pos = ammo["pos"]
            source_pad = self._pick_source_pad(harv_pos, gunner_pos)
            if source_pad is None:
                dbg(
                    f"r={self.round_no} id={self.my_id} attack: no source pad from enemy harv {harv_pos}",
                )
                self._clear_attack()
                return False
            self.connecting = True
            self.connect_turns = 0
            self.connect_last_build_round = self.round_no
            self.connect_harvester_pos = harv_pos
            self.chain_end = source_pad
            self.connect_target = gunner_pos
            self.connect_plan = None
            self.connect_plan_idx = 0
            self.current_chain = []
            self.connect_unwind_destroy = None
            self.connect_attack_pos = None
            self.connect_stall_recoverable = False
            dbg(
                f"r={self.round_no} id={self.my_id} attack: chain from enemy harv {harv_pos} pad={source_pad} -> gunner {gunner_pos}",
            )
            return True
        # Need to build harvester on ore, then route chain.
        self._attack_ore = ammo["pos"]
        self.task = "attack"
        dbg(
            f"r={self.round_no} id={self.my_id} attack: ore={ammo['pos']} gunner={gunner_pos} -> {target}",
        )
        return self._continue_attack(ct)

    def _continue_attack(self, ct: Controller) -> bool:
        """Continue an attack: build harvester, route chain, place gunner."""
        if self._attack_target is None:
            return False

        # If gunner build is active, let it run.
        if self.gunner_build is not None:
            return self._continue_gunner_build(ct)

        # If mid-connect (routing chain), continue.
        if self.connecting:
            self._run_connect_back(ct)
            return True

        # If we need to build a harvester for ammo.
        if self._attack_ore is not None:
            ore = self._attack_ore
            dist = self.my_pos.distance_squared(ore)
            # Check if ore is still free.
            oinfo = self.visible_buildings.get(ore) or self.known_buildings.get(ore)
            if oinfo is not None:
                dbg(f"r={self.round_no} id={self.my_id} attack: ore {ore} taken, abort")
                self._clear_attack()
                return False
            if dist > 2:
                self._walk_toward(ct, ore)
                return True
            # Adjacent — build harvester.
            if ct.get_action_cooldown() != 0:
                return True
            harv_cost = ct.get_harvester_cost()[0]
            titanium, _ = ct.get_global_resources()
            if titanium < harv_cost:
                dbg(
                    f"r={self.round_no} id={self.my_id} attack: wait harv ti={titanium} cost={harv_cost}",
                )
                return True
            if ct.can_build_harvester(ore):
                ct.build_harvester(ore)
                dbg(f"r={self.round_no} id={self.my_id} attack: harvester at {ore}")
                self._attack_ore = None
                # Start chain from harvester to gunner pos.
                gunner_pos = self._attack_gunner_pos
                source_pad = self._pick_source_pad(ore, gunner_pos)
                if source_pad is None:
                    dbg(
                        f"r={self.round_no} id={self.my_id} attack: no source pad, abort",
                    )
                    self._clear_attack()
                    return False
                self.task = "connect"
                self.connecting = True
                self.connect_turns = 0
                self.connect_last_build_round = self.round_no
                self.connect_harvester_pos = ore
                self.chain_end = source_pad
                self.connect_target = gunner_pos
                self.connect_plan = None
                self.connect_plan_idx = 0
                self.current_chain = []
                self.connect_unwind_destroy = None
                self.connect_attack_pos = None
                self.connect_stall_recoverable = False
                dbg(
                    f"r={self.round_no} id={self.my_id} attack: chain from {source_pad} -> gunner {gunner_pos}",
                )
                return True
            self._clear_attack()
            return False

        # Chain finished — place gunner.
        if self._attack_gunner_pos is not None and self.gunner_build is None:
            self.gunner_build = {
                "enemy_pos": self._attack_target,
                "gunner_pos": self._attack_gunner_pos,
                "gunner_dir": self._attack_gunner_dir,
                "chain_pos": None,
                "chain_type": EntityType.HARVESTER,
                "phase": 2,
                "start_round": self.round_no,
                "est_turns": 5,
                "_is_attack": True,
            }
            dbg(
                f"r={self.round_no} id={self.my_id} attack: chain done, gunner at {self._attack_gunner_pos}",
            )
            return self._continue_gunner_build(ct)

        self._clear_attack()
        return False

    def _clear_attack(self) -> None:
        """Reset attack state."""
        self._attack_target = None
        self._attack_gunner_pos = None
        self._attack_gunner_dir = None
        self._attack_ore = None
        if self.task == "attack":
            self.task = "idle"

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

    def _build_walk_cache(self, ct: Controller = None) -> None:
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

        # Danger zones: enemy turret attack tiles (cost penalty, not blocked).
        wc_danger = self._wc_danger
        wc_danger.clear()
        _TURRET_TYPES = {
            EntityType.SENTINEL,
            EntityType.GUNNER,
            EntityType.BREACH,
            EntityType.LAUNCHER,
        }
        for pos, (eid, etype, team) in self.visible_buildings.items():
            if team == self.my_team or etype not in _TURRET_TYPES:
                continue
            if ct is None:
                continue
            try:
                # Launchers are omnidirectional — direction is ignored.
                if etype == EntityType.LAUNCHER:
                    d = Direction.NORTH  # dummy, ignored by API
                else:
                    d = ct.get_direction(eid)
                for tile in ct.get_attackable_tiles_from(pos, d, etype):
                    wc_danger.add((tile.x, tile.y))
            except Exception:
                pass

    def _walk_toward(
        self,
        ct: Controller,
        target: Position,
        best_effort: bool = False,
    ) -> bool:
        """Move one step toward target, paving roads as needed."""
        if self.my_pos is None or ct.get_move_cooldown() != 0:
            return False

        # Don't route into enemy core tiles — A* treats them as impassable
        # so we'd get no path. Use best_effort to get as close as possible.
        if self._is_enemy_core_tile(target):
            best_effort = True

        self._build_walk_cache(ct)
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
            # Reduced turret avoidance during gunner builds (need to approach but
            # shouldn't walk through unnecessary danger). Full avoidance otherwise.
            danger_set=self._wc_danger or None,
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
            # Count as stuck so callers can abandon unreachable targets.
            if target == self._stuck_target:
                self._stuck_turns += 1
            else:
                self._stuck_target = target
                self._stuck_turns = 1
            return False

        dx, dy = DIRECTION_DELTA[direction]
        next_pos = Position(self.my_pos.x + dx, self.my_pos.y + dy)

        if ct.can_move(direction):
            ct.move(direction)
            old_pos = self.my_pos
            self.my_pos = ct.get_position()
            dbg(
                f"r={self.round_no} id={self.my_id} move {old_pos}->{self.my_pos} nav={nav_source} toward {target}",
            )
            self._stuck_target = None
            self._stuck_turns = 0
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
        # Track consecutive failures on same target
        if target == self._stuck_target:
            self._stuck_turns += 1
        else:
            self._stuck_target = target
            self._stuck_turns = 1
        if self._stuck_turns >= 5:
            dbg(
                f"r={self.round_no} id={self.my_id} STUCK {self._stuck_turns} turns on {target}, caller should abandon",
            )
            # Trapped by own buildings? Destroy least valuable adjacent one to escape.
            if self._stuck_turns >= 8 and ct.get_action_cooldown() == 0:
                # Only destroy non-walkable own buildings (roads/conveyors are walkable).
                _DESTROY_PRIO = {
                    EntityType.SENTINEL: 1,
                    EntityType.GUNNER: 2,
                    EntityType.BARRIER: 0,
                }
                best_destroy = None
                best_prio = 999
                for d in ALL_DIRECTIONS:
                    ddx, ddy = DIRECTION_DELTA[d]
                    adj = Position(self.my_pos.x + ddx, self.my_pos.y + ddy)
                    ainfo = self.visible_buildings.get(adj)
                    if ainfo is None:
                        continue
                    _, aetype, ateam = ainfo
                    if ateam != self.my_team:
                        continue
                    prio = _DESTROY_PRIO.get(aetype, 999)
                    if prio < best_prio:
                        best_prio = prio
                        best_destroy = adj
                if best_destroy is not None and best_prio < 999:
                    if ct.can_destroy(best_destroy):
                        ct.destroy(best_destroy)
                        self.visible_buildings.pop(best_destroy, None)
                        dbg(
                            f"r={self.round_no} id={self.my_id} escape: destroyed own building at {best_destroy}",
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
        # Don't futilely heal buildings under sustained attack we can't counter.
        # If damaged for 10+ turns and we haven't started a gunner build, give up.
        if self.damaged_turns.get(pos, 0) >= 10 and self.gunner_build is None:
            return False
        if missing >= 4:
            return True
        # Minor damage: only heal if persistent (being attacked).
        return self.damaged_turns.get(pos, 0) >= 5

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

        # Check defense reserve before spending.
        harv_cost = ct.get_harvester_cost()[0]
        if not self._can_afford(ct, harv_cost):
            dbg(f"r={self.round_no} id={self.my_id} harvester: defense reserve hold")
            return False

        if not ct.can_build_harvester(self.target_ore):
            # Diagnose why
            titanium, _ = ct.get_global_resources()
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

        self.task = "connect"
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
            info = self.visible_buildings.get(pad) or self.known_buildings.get(pad)
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
        cache_key = (len(self.tile_env), len(self.known_buildings), self.round_no)
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
        # Attack chain: gunner position is a valid terminal.
        if self._attack_gunner_pos is not None:
            gp = self._attack_gunner_pos
            terminals.add((gp.x, gp.y))
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
                    else:
                        dbg(
                            f"r={self.round_no} id={self.my_id} connect last-step conv failed at {conv_pos} dir={conv_dir.name} cd={ct.get_action_cooldown()}",
                        )
                    return
                # No adjacent terminal — try to point toward connect_target
                dbg(
                    f"r={self.round_no} id={self.my_id} connect last-step no terminal adj to {conv_pos}",
                )
                ddx = self.connect_target.x - conv_pos.x
                ddy = self.connect_target.y - conv_pos.y

            conv_dir = DELTA_TO_DIRECTION.get((ddx, ddy))
            if conv_dir is None:
                dbg(
                    f"r={self.round_no} id={self.my_id} connect non-cardinal delta ({ddx},{ddy}) at {conv_pos}, replan",
                )
                self.connect_plan = None  # re-plan
                return

            if self._try_place_conveyor(ct, conv_pos, conv_dir):
                self.current_chain.append(conv_pos)
                self.chain_end = Position(conv_pos.x + ddx, conv_pos.y + ddy)
                self.connect_plan_idx += 1
                self._step_toward_chain_end(ct)
            else:
                dbg(
                    f"r={self.round_no} id={self.my_id} connect conv failed at {conv_pos} dir={conv_dir.name} cd={ct.get_action_cooldown()}",
                )

        elif action == "bridge":
            from_pos = self.chain_end
            landing = Position(step[3], step[4])
            if self._try_bridge_to(ct, from_pos, landing):
                self.current_chain.append(from_pos)
                self.chain_end = landing
                self.connect_plan_idx += 1
            else:
                dbg(
                    f"r={self.round_no} id={self.my_id} connect bridge failed from {from_pos} -> {landing} cd={ct.get_action_cooldown()}",
                )
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
        bridge_cost = ct.get_bridge_cost()[0]
        if not self._can_afford(ct, bridge_cost):
            titanium, _ = ct.get_global_resources()
            dbg(
                f"r={self.round_no} id={self.my_id} bridge: can't afford ti={titanium} cost={bridge_cost}",
            )
            self.connect_last_build_round = self.round_no  # Ti/reserve wait ≠ stall
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
            dbg(
                f"r={self.round_no} id={self.my_id} connect walk to chain_end {self.chain_end} dist²={self.my_pos.distance_squared(self.chain_end)}",
            )
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
            if self._stuck_turns >= 5:
                dbg(
                    f"r={self.round_no} id={self.my_id} abandon connect_target {self.connect_target} (stuck {self._stuck_turns} turns)",
                )
                self.connect_target = None
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

        conv_cost = ct.get_conveyor_cost()[0]
        if not self._can_afford(ct, conv_cost):
            self.connect_last_build_round = self.round_no  # Ti/reserve wait ≠ stall
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
            self.my_chain_dirs[pos] = direction
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
        # Queue sentinel unless there's already one nearby (dist²≤18, ~4 tiles).
        if success and self.connect_harvester_pos is not None:
            hpos = self.connect_harvester_pos
            has_nearby = False
            for bpos, binfo in (self.visible_buildings or {}).items():
                if binfo[2] == self.my_team and binfo[1] == EntityType.SENTINEL:
                    if hpos.distance_squared(bpos) <= 25:
                        has_nearby = True
                        break
            if not has_nearby:
                # Also check known_buildings for sentinels out of vision.
                for bpos, binfo in self.known_buildings.items():
                    if binfo[2] == self.my_team and binfo[1] == EntityType.SENTINEL:
                        if hpos.distance_squared(bpos) <= 25:
                            has_nearby = True
                            break
            if not has_nearby:
                self._pending_sentinel_harvester = hpos
            else:
                dbg(
                    f"r={self.round_no} id={self.my_id} skip sentinel for {hpos} — friendly sentinel nearby",
                )

        self.current_chain.clear()
        if self.task != "attack":
            self.task = "idle"
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
    # Reactive gunner placement (healer-defender)
    # ------------------------------------------------------------------

    _ENEMY_TURRET_TYPES = {
        EntityType.SENTINEL,
        EntityType.GUNNER,
        EntityType.BREACH,
        EntityType.LAUNCHER,
    }

    def _check_chain_repair(self, ct: Controller) -> bool:
        """Detect gaps in any friendly chain and rebuild. Returns True if handling repair."""
        if self.my_pos is None or not self.my_chain_dirs:
            return False
        # Already repairing — walk to gap and rebuild.
        if self.task == "repair" and self._repair_target is not None:
            return self._continue_repair(ct)
        # Scan all cached chain positions for gaps visible to us.
        # my_chain_dirs includes both own-placed AND other builders' conveyors
        # seen during _scan. This enables cross-builder repair.
        for pos, direction in self.my_chain_dirs.items():
            if self.my_pos.distance_squared(pos) > 20:
                continue  # out of vision range
            info = self.visible_buildings.get(pos)
            if info is not None:
                continue  # building still there
            # Position was a conveyor but now empty — gap detected.
            # Skip if enemy building replaced it (threat response handles that).
            dbg(
                f"r={self.round_no} id={self.my_id} repair: gap at {pos} dir={direction.name}",
            )
            self._repair_target = pos
            self.task = "repair"
            return self._continue_repair(ct)
        return False

    def _continue_repair(self, ct: Controller) -> bool:
        """Walk to repair target and rebuild conveyor."""
        pos = self._repair_target
        if pos is None:
            self.task = "idle"
            return False
        # Check if already repaired or enemy has taken the tile.
        info = self.visible_buildings.get(pos)
        if info is not None:
            _, retype, reteam = info
            if reteam == self.my_team:
                dbg(f"r={self.round_no} id={self.my_id} repair: {pos} already rebuilt")
                self._repair_target = None
                self.task = "idle"
                return False
            # Enemy building on our chain tile — escalate to gunner.
            if retype in self._ENEMY_TURRET_TYPES:
                plan = self._plan_gunner(ct, pos)
                if plan is not None:
                    self.gunner_build = plan
                    self._repair_target = None
                    self.task = "idle"
                    dbg(
                        f"r={self.round_no} id={self.my_id} repair: enemy {retype.name} at {pos}, escalating to gunner",
                    )
                    return self._continue_gunner_build(ct)
            # Enemy non-turret (road/conveyor) — we can fire to clear after walking on.
            dbg(
                f"r={self.round_no} id={self.my_id} repair: enemy {retype.name} at {pos}, clearing",
            )
        # Abandon if stuck.
        if self._stuck_turns >= 10:
            dbg(f"r={self.round_no} id={self.my_id} repair: abandon {pos} (stuck)")
            self._repair_target = None
            self.task = "idle"
            return False
        dist = self.my_pos.distance_squared(pos)
        if dist > 2:
            self._walk_toward(ct, pos)
            return True
        # Adjacent — place conveyor with stored direction.
        direction = self.my_chain_dirs.get(pos)
        if direction is None:
            self._repair_target = None
            self.task = "idle"
            return False
        if ct.get_action_cooldown() != 0:
            return True
        # Clear own road/marker if blocking.
        bld = self.visible_buildings.get(pos)
        if (
            bld is not None
            and bld[2] == self.my_team
            and bld[1] in {EntityType.ROAD, EntityType.MARKER}
        ) and ct.can_destroy(pos):
            ct.destroy(pos)
        # If our turret is adjacent, rebuild as splitter to feed it.
        has_turret_adj = False
        for tdx, tdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            tpos = Position(pos.x + tdx, pos.y + tdy)
            tinfo = self.visible_buildings.get(tpos)
            if (
                tinfo is not None
                and tinfo[2] == self.my_team
                and tinfo[1]
                in {
                    EntityType.SENTINEL,
                    EntityType.GUNNER,
                    EntityType.BREACH,
                }
            ):
                has_turret_adj = True
                break
        if has_turret_adj and ct.can_build_splitter(pos, direction):
            ct.build_splitter(pos, direction)
            dbg(
                f"r={self.round_no} id={self.my_id} repair: rebuilt SPLITTER at {pos} -> {direction.name} (turret adj)",
            )
        elif ct.can_build_conveyor(pos, direction):
            ct.build_conveyor(pos, direction)
            dbg(
                f"r={self.round_no} id={self.my_id} repair: rebuilt conv at {pos} -> {direction.name}",
            )
            self._repair_target = None
            self.task = "idle"
            return True
        dbg(f"r={self.round_no} id={self.my_id} repair: can't build at {pos}")
        return True

    def _check_for_threats(self, ct: Controller) -> bool:
        """Scan for enemy turrets near our infrastructure. If found, start gunner build.

        Returns True if handling a threat (caller should return).
        """
        if self.my_pos is None:
            return False

        # Already building a gunner — continue that.
        if self.gunner_build is not None:
            return self._continue_gunner_build(ct)

        # Scan for enemy turrets near our tree/core.
        for pos, (_eid, etype, team) in self.visible_buildings.items():
            if team == self.my_team or etype not in self._ENEMY_TURRET_TYPES:
                continue
            # Deconflict: only respond if we're the closest ally to this threat.
            my_dist = self.my_pos.distance_squared(pos)
            ally_closer = False
            for ally_pos in self.visible_allies.values():
                if ally_pos.distance_squared(pos) < my_dist:
                    ally_closer = True
                    break
            if ally_closer:
                continue
            # Is this near our infrastructure (completed tree + in-progress chain)?
            near_us = False
            for own_pos in self.my_tree:
                if pos.distance_squared(own_pos) <= 25:
                    near_us = True
                    break
            if not near_us:
                for own_pos in self.current_chain:
                    if pos.distance_squared(own_pos) <= 25:
                        near_us = True
                        break
            if not near_us and self.connect_harvester_pos is not None:
                if pos.distance_squared(self.connect_harvester_pos) <= 25:
                    near_us = True
            if not near_us and self.core_pos is not None:
                if pos.distance_squared(self.core_pos) <= 64:
                    near_us = True
            # Respond to any enemy turret in our half of the map.
            if not near_us and not self._in_enemy_half(pos):
                near_us = True
            if not near_us:
                continue

            # Skip if we already have a gunner that can reach this threat (any facing).
            already_covered = False
            for gpos, ginfo in self.visible_buildings.items():
                if ginfo[2] == self.my_team and ginfo[1] == EntityType.GUNNER:
                    if gpos.distance_squared(pos) > 13:
                        continue
                    for d in ALL_DIRECTIONS:
                        if ct.can_fire_from(gpos, d, EntityType.GUNNER, pos):
                            already_covered = True
                            break
                    if already_covered:
                        break
            if already_covered:
                continue

            # Found a threat — try to plan a gunner.
            plan = self._plan_gunner(ct, pos)
            if plan is not None:
                # Suspend current task for resumption after gunner build.
                if self.task == "seek_ore" and self.target_ore is not None:
                    self.suspended_task = "seek_ore"
                    self.suspended_state = {"target_ore": self.target_ore}
                    dbg(
                        f"r={self.round_no} id={self.my_id} suspend task=seek_ore ore={self.target_ore}",
                    )
                self.gunner_build = plan
                dbg(
                    f"r={self.round_no} id={self.my_id} defender: targeting {etype.name} at {pos}, gunner at {plan['gunner_pos']}",
                )
                return self._continue_gunner_build(ct)

        return False

    def _plan_gunner(self, ct: Controller, enemy_pos: Position) -> dict | None:
        """Find best gunner position to kill an enemy turret.

        Scores by estimated turns to eliminate the threat:
        - Walk distance to build site (~sqrt of dist²)
        - Gunner tile clearing: 0 if empty/own road/marker, ~3 if enemy road
        - Ammo source: 0 if adjacent to own harvester (direct feed),
          1 if adjacent to own splitter, 1 if conveyor→splitter swap needed
        - LoS obstruction: ceil(HP/10) per building between gunner and target
        - Kill time: 3 rounds (sentinel 30HP / 10 dmg)

        Returns build plan dict or None.
        """
        if self.my_pos is None:
            return None

        # Precompute enemy turret's attackable tiles so we avoid placing ammo
        # sources in its line of fire.
        enemy_info = self.visible_buildings.get(enemy_pos)
        enemy_attack_tiles: set[Position] = set()
        if enemy_info is not None:
            try:
                enemy_dir = ct.get_direction(enemy_info[0])
                enemy_attack_tiles = set(
                    ct.get_attackable_tiles_from(enemy_pos, enemy_dir, enemy_info[1]),
                )
            except Exception:
                pass  # can't get direction, skip check

        best = None
        best_turns = 999

        for gx in range(
            max(0, enemy_pos.x - 4),
            min((self.map_w or 50), enemy_pos.x + 5),
        ):
            for gy in range(
                max(0, enemy_pos.y - 4),
                min((self.map_h or 50), enemy_pos.y + 5),
            ):
                gpos = Position(gx, gy)
                if gpos.distance_squared(enemy_pos) > 13:
                    continue
                env = self.tile_env.get(gpos)
                if env is None or env == Environment.WALL:
                    continue
                if env in {Environment.ORE_TITANIUM, Environment.ORE_AXIONITE}:
                    continue

                # Tile clearing cost.
                tile_clear_turns = 0
                ginfo = self.visible_buildings.get(gpos)
                if ginfo is not None:
                    _, getype, gteam = ginfo
                    if getype == EntityType.MARKER:
                        pass  # buildable-over
                    elif gteam == self.my_team and getype == EntityType.ROAD:
                        pass  # destroy() free
                    elif gteam != self.my_team and getype == EntityType.ROAD:
                        tile_clear_turns = 3  # fire() at 2 dmg/turn, road 5 HP
                    else:
                        continue  # non-clearable

                # Compute facing direction from gunner to enemy.
                dx = enemy_pos.x - gx
                dy = enemy_pos.y - gy
                if dx != 0:
                    dx = dx // abs(dx)
                if dy != 0:
                    dy = dy // abs(dy)
                gun_dir = DELTA_TO_DIRECTION.get((dx, dy))
                if gun_dir is None:
                    continue

                # Check LoS.
                if not ct.can_fire_from(gpos, gun_dir, EntityType.GUNNER, enemy_pos):
                    continue

                # Find ammo source: adjacent harvester (best) or chain tile.
                # Gunner accepts ammo from any direction except facing.
                fdx, fdy = DIRECTION_DELTA[gun_dir]
                ammo_source = None
                ammo_type = None  # 'harvester', 'splitter', 'conveyor'
                ammo_turns = 999

                for cdx, cdy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    if cdx == fdx and cdy == fdy:
                        continue  # gunner can't accept from facing side
                    cpos = Position(gx + cdx, gy + cdy)
                    cinfo = self.visible_buildings.get(cpos)
                    if cinfo is None:
                        continue
                    _, cetype, cteam = cinfo
                    # Penalize ammo sources in enemy turret's line of fire.
                    in_fire = cpos in enemy_attack_tiles
                    fire_penalty = 5 if in_fire else 0

                    # Enemy Ti harvesters also feed our gunner (skip Ax — wrong resource).
                    if cteam != self.my_team and cetype == EntityType.HARVESTER:
                        ore_env = self.tile_env.get(cpos)
                        if ore_env == Environment.ORE_AXIONITE:
                            continue
                        cost = 0 + fire_penalty
                        if cost < ammo_turns:
                            ammo_source = cpos
                            ammo_type = "enemy_harvester"
                            ammo_turns = cost
                        continue
                    if cteam != self.my_team:
                        continue

                    if cetype == EntityType.HARVESTER:
                        # Best: harvester feeds gunner directly, no chain work.
                        cost = 0 + fire_penalty
                        if cost < ammo_turns:
                            ammo_source = cpos
                            ammo_type = "harvester"
                            ammo_turns = cost
                    elif cetype == EntityType.SPLITTER:
                        # Good: already a splitter, may feed us on a side output.
                        cost = 0 + fire_penalty
                        if cost < ammo_turns:
                            ammo_source = cpos
                            ammo_type = "splitter"
                            ammo_turns = cost
                    elif cetype == EntityType.CONVEYOR:
                        # OK: need to swap conveyor→splitter (+1 turn).
                        cost = 1 + fire_penalty
                        if (
                            cpos not in self.visible_unit_positions
                            and cost < ammo_turns
                        ):
                            ammo_source = cpos
                            ammo_type = "conveyor"
                            ammo_turns = cost

                if ammo_source is None:
                    continue

                # Walk distance: approximate as manhattan-ish.
                # Walk to ammo source first (if conveyor swap needed), then to gunner.
                if ammo_type == "conveyor":
                    walk_dist = (
                        int(self.my_pos.distance_squared(ammo_source) ** 0.5) + 1
                    )
                else:
                    walk_dist = int(self.my_pos.distance_squared(gpos) ** 0.5)

                # Total estimated turns.
                turns = walk_dist + ammo_turns + tile_clear_turns + 3  # +3 to kill

                if turns < best_turns:
                    best_turns = turns
                    best = {
                        "enemy_pos": enemy_pos,
                        "gunner_pos": gpos,
                        "gunner_dir": gun_dir,
                        "chain_pos": ammo_source,
                        "chain_type": EntityType.SPLITTER
                        if ammo_type == "splitter"
                        else EntityType.HARVESTER
                        if ammo_type in ("harvester", "enemy_harvester")
                        else EntityType.CONVEYOR,
                        "phase": 0,
                        "start_round": self.round_no,
                        "est_turns": turns,
                    }

        if best is not None:
            dbg(
                f"r={self.round_no} id={self.my_id} defender plan: gunner at {best['gunner_pos']} "
                f"ammo={best['chain_type'].name} at {best['chain_pos']} est={best['est_turns']}t",
            )
        return best

    def _finish_gunner_build(self) -> None:
        """Clear gunner build state and resume suspended task if any."""
        self.gunner_build = None
        # Clear attack state if this was an attack gunner.
        if self._attack_target is not None:
            self._clear_attack()
        if self.suspended_task is not None:
            self.task = self.suspended_task
            if self.suspended_task == "seek_ore" and self.suspended_state:
                self.target_ore = self.suspended_state.get("target_ore")
                dbg(
                    f"r={self.round_no} id={self.my_id} resume task={self.task} ore={self.target_ore}",
                )
            self.suspended_task = None
            self.suspended_state = None

    def _continue_gunner_build(self, ct: Controller) -> bool:
        """Execute the gunner build state machine. Returns True if busy."""
        gb = self.gunner_build
        if gb is None:
            return False

        # Self-heal if HP is low — don't walk into danger and die.
        my_hp = ct.get_hp()
        my_max = ct.get_max_hp()
        if (
            my_max - my_hp >= 8
            and ct.get_action_cooldown() == 0
            and ct.can_heal(self.my_pos)
        ):
            ct.heal(self.my_pos)
            dbg(
                f"r={self.round_no} id={self.my_id} defender: self-heal missing={my_max - my_hp}",
            )
            return True

        # Timeout: give up after 30 non-Ti-wait turns.
        # Don't count turns where we're just waiting for resources.
        elapsed = self.round_no - gb.get("start_round", self.round_no)
        is_sentinel = gb.get("_is_sentinel", False)
        ti_waiting = gb["phase"] == 3  # phase 3 = at position, waiting to build
        if ti_waiting and is_sentinel:
            # Sentinels wait indefinitely for Ti — don't timeout.
            pass
        elif elapsed > 30:
            dbg(
                f"r={self.round_no} id={self.my_id} defender: build timeout after {elapsed} turns",
            )
            self._finish_gunner_build()
            return False

        # Cancel if enemy turret gone (skip for proactive sentinel/attack builds).
        if not gb.get("_is_sentinel", False) and not gb.get("_is_attack", False):
            einfo = self.visible_buildings.get(gb["enemy_pos"])
            if einfo is not None and (
                einfo[2] == self.my_team or einfo[1] not in self._ENEMY_TURRET_TYPES
            ):
                dbg(
                    f"r={self.round_no} id={self.my_id} defender: threat gone at {gb['enemy_pos']}, cancel",
                )
                self._finish_gunner_build()
                return False
        # If we can't see the tile anymore, keep going (it might still be there).

        phase = gb["phase"]
        chain_pos = gb["chain_pos"]
        gunner_pos = gb["gunner_pos"]

        if phase == 0:
            # Harvester/splitter ammo source: skip straight to gunner placement.
            if gb["chain_type"] in {EntityType.HARVESTER, EntityType.SPLITTER}:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p0→p2: {gb['chain_type'].name} feeds gunner, skip splitter",
                )
                gb["phase"] = 2
                return True
            # Conveyor: walk to it to replace with splitter.
            dist = self.my_pos.distance_squared(chain_pos)
            if dist > 2:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p0: walk to chain {chain_pos} dist²={dist} from {self.my_pos}",
                )
                moved = self._walk_toward(ct, chain_pos)
                if not moved:
                    cinfo = self.visible_buildings.get(chain_pos)
                    units_on = chain_pos in self.visible_unit_positions
                    dbg(
                        f"r={self.round_no} id={self.my_id} defender p0: STUCK bld={cinfo[1].name if cinfo else 'none'} unit_on={units_on}",
                    )
                return True
            dbg(
                f"r={self.round_no} id={self.my_id} defender p0→p1: arrived at chain {chain_pos}",
            )
            gb["phase"] = 1
            return True

        if phase == 1:
            # Replace conveyor with splitter.
            if gb["chain_type"] != EntityType.CONVEYOR:
                gb["phase"] = 2
                return True
            if ct.get_action_cooldown() != 0:
                dbg(f"r={self.round_no} id={self.my_id} defender p1: wait action cd")
                return True
            cinfo = self.visible_buildings.get(chain_pos)
            if cinfo is None:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p1: chain tile gone at {chain_pos}, cancel",
                )
                self._finish_gunner_build()
                return False
            _, cetype, cteam = cinfo
            if cteam != self.my_team:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p1: chain tile enemy at {chain_pos}, cancel",
                )
                self._finish_gunner_build()
                return False
            # Find the UPSTREAM source that feeds this tile.
            # The splitter must face so its back accepts input.
            # Check conveyors first, then fall back to adjacent harvester.
            # If nothing found, use replaced conveyor's direction.
            conv_eid = cinfo[0]
            splitter_dir = ct.get_direction(conv_eid)  # fallback
            found_upstream = False
            for udx, udy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                upos = Position(chain_pos.x + udx, chain_pos.y + udy)
                uinfo = self.visible_buildings.get(upos)
                if uinfo is None:
                    continue
                _, utype, uteam = uinfo
                if uteam != self.my_team:
                    continue
                if utype not in {
                    EntityType.CONVEYOR,
                    EntityType.SPLITTER,
                    EntityType.ARMOURED_CONVEYOR,
                }:
                    continue
                # Check if this upstream building outputs toward chain_pos.
                u_dir = ct.get_direction(uinfo[0])
                fdx, fdy = DIRECTION_DELTA[u_dir]
                if upos.x + fdx == chain_pos.x and upos.y + fdy == chain_pos.y:
                    # This upstream conveyor feeds into chain_pos.
                    # Splitter should face the same direction to accept from back.
                    splitter_dir = u_dir
                    found_upstream = True
                    dbg(
                        f"r={self.round_no} id={self.my_id} defender p1: upstream {utype.name} at {upos} dir={u_dir.name}",
                    )
                    break
            # If no upstream conveyor, check for adjacent harvester.
            # Harvester outputs to any adjacent building, so splitter must
            # face AWAY from harvester (back toward it) to accept input.
            if not found_upstream:
                for udx, udy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    upos = Position(chain_pos.x + udx, chain_pos.y + udy)
                    uinfo = self.visible_buildings.get(upos)
                    if uinfo is None:
                        continue
                    _, utype, uteam = uinfo
                    if uteam != self.my_team or utype != EntityType.HARVESTER:
                        continue
                    hdx = chain_pos.x - upos.x
                    hdy = chain_pos.y - upos.y
                    hdir = DELTA_TO_DIRECTION.get((hdx, hdy))
                    if hdir is not None:
                        splitter_dir = hdir
                        dbg(
                            f"r={self.round_no} id={self.my_id} defender p1: upstream HARVESTER at {upos}, splitter dir={hdir.name}",
                        )
                        break
            # Check Ti BEFORE destroying — don't break chain if we can't rebuild.
            titanium, _ = ct.get_global_resources()
            splitter_cost = ct.get_splitter_cost()[0]
            if titanium < splitter_cost:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p1: wait splitter ti={titanium} cost={splitter_cost} (keeping {cetype.name})",
                )
                return True
            # Destroy and immediately rebuild as splitter.
            if ct.can_destroy(chain_pos):
                ct.destroy(chain_pos)
                self.visible_buildings.pop(chain_pos, None)
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p1: destroyed {cetype.name} at {chain_pos}",
                )
            if ct.can_build_splitter(chain_pos, splitter_dir):
                ct.build_splitter(chain_pos, splitter_dir)
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p1→p2: splitter at {chain_pos} dir={splitter_dir.name}",
                )
                gb["phase"] = 2
                return True
            dbg(
                f"r={self.round_no} id={self.my_id} defender p1: can't build splitter at {chain_pos} dir={splitter_dir.name}, cancel",
            )
            self._finish_gunner_build()
            return False

        if phase == 2:
            # Walk to gunner position.
            dist = self.my_pos.distance_squared(gunner_pos)
            if dist > 2:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p2: walk to gunner {gunner_pos} dist²={dist} from {self.my_pos}",
                )
                self._walk_toward(ct, gunner_pos)
                return True
            # Late evaluation: pick best (tile, facing) now with full vision.
            if gb.get("_needs_eval", False):
                harv_pos = gb["enemy_pos"]
                result = self._eval_sentinel_placement(ct, harv_pos)
                if result is None:
                    dbg(
                        f"r={self.round_no} id={self.my_id} defender p2: no valid placement near {harv_pos}",
                    )
                    self._finish_gunner_build()
                    return False
                gb["gunner_pos"] = result[0]
                gb["gunner_dir"] = result[1]
                gb["_needs_eval"] = False
                gunner_pos = result[0]
                dbg(
                    f"r={self.round_no} id={self.my_id} defender p2: eval'd sentinel at {result[0]} facing {result[1].name}",
                )
                # May need to walk to the chosen tile.
                if self.my_pos.distance_squared(gunner_pos) > 2:
                    self._walk_toward(ct, gunner_pos)
                    return True
            dbg(
                f"r={self.round_no} id={self.my_id} defender p2→p3: arrived at gunner {gunner_pos}",
            )
            gb["phase"] = 3
            return True  # process phase 3 next turn

        if phase == 3:
            # Check Ti first — don't clear the tile until we can afford the gunner.
            if ct.get_action_cooldown() != 0:
                return True
            titanium, _ = ct.get_global_resources()
            is_sentinel = gb.get("_is_sentinel", False)
            turret_cost = (
                ct.get_sentinel_cost()[0] if is_sentinel else ct.get_gunner_cost()[0]
            )
            if titanium < turret_cost:
                dbg(
                    f"r={self.round_no} id={self.my_id} defender: wait {'sentinel' if is_sentinel else 'gunner'} ti={titanium} cost={turret_cost}",
                )
                return True

            # Clear the gunner tile if occupied (only after Ti check).
            ginfo = self.visible_buildings.get(gunner_pos)
            if ginfo is not None:
                _, getype, gteam = ginfo
                if getype == EntityType.MARKER:
                    pass  # buildable-over
                elif gteam == self.my_team and getype in {
                    EntityType.ROAD,
                    EntityType.MARKER,
                }:
                    if ct.can_destroy(gunner_pos):
                        ct.destroy(gunner_pos)
                        self.visible_buildings.pop(gunner_pos, None)
                        dbg(
                            f"r={self.round_no} id={self.my_id} defender p3: cleared own {getype.name} at {gunner_pos}",
                        )
                elif gteam != self.my_team and getype in {
                    EntityType.ROAD,
                    EntityType.CONVEYOR,
                    EntityType.BRIDGE,
                    EntityType.SPLITTER,
                    EntityType.ARMOURED_CONVEYOR,
                }:
                    # Walk onto and fire to clear enemy building.
                    if self.my_pos != gunner_pos:
                        self._walk_toward(ct, gunner_pos)
                        return True
                    if ct.can_fire(self.my_pos):
                        ct.fire(self.my_pos)
                        dbg(
                            f"r={self.round_no} id={self.my_id} defender p3: fire at enemy {getype.name} {gunner_pos}",
                        )
                    return True
                elif getype != EntityType.MARKER:
                    dbg(
                        f"r={self.round_no} id={self.my_id} defender p3: {getype.name} blocking {gunner_pos}, cancel",
                    )
                    self._finish_gunner_build()
                    return False

            # Must not be standing on the tile to build.
            if self.my_pos == gunner_pos:
                moved = False
                for d in ALL_DIRECTIONS:
                    if ct.can_move(d):
                        ct.move(d)
                        dbg(
                            f"r={self.round_no} id={self.my_id} defender p3: step off gunner tile",
                        )
                        moved = True
                        break
                if not moved:
                    # Pave a road on an adjacent tile so we can step off next turn.
                    for d in ALL_DIRECTIONS:
                        ddx, ddy = DIRECTION_DELTA[d]
                        adj = Position(self.my_pos.x + ddx, self.my_pos.y + ddy)
                        if ct.can_build_road(adj):
                            ct.build_road(adj)
                            dbg(
                                f"r={self.round_no} id={self.my_id} defender p3: pave road at {adj} for step-off",
                            )
                            return True
                    return True  # truly stuck
            is_sentinel = gb.get("_is_sentinel", False)
            pos, facing = gb["gunner_pos"], gb["gunner_dir"]
            if is_sentinel:
                if ct.can_build_sentinel(pos, facing):
                    ct.build_sentinel(pos, facing)
                    self._sentinels_placed = getattr(self, "_sentinels_placed", 0) + 1
                    dbg(
                        f"r={self.round_no} id={self.my_id} defender: sentinel at {pos} facing {facing.name} (total={self._sentinels_placed})",
                    )
                    self._finish_gunner_build()
                    return True
            elif ct.can_build_gunner(pos, facing):
                ct.build_gunner(pos, facing)
                dbg(
                    f"r={self.round_no} id={self.my_id} defender: gunner at {pos} facing {facing.name} targeting {gb['enemy_pos']}",
                )
                self._finish_gunner_build()
                return True
            ginfo = self.visible_buildings.get(pos)
            gunit = pos in self.visible_unit_positions
            kind = "sentinel" if is_sentinel else "gunner"
            dbg(
                f"r={self.round_no} id={self.my_id} defender: can't build {kind} at {pos} dir={facing.name} bld={ginfo[1].name if ginfo else 'none'} unit={gunit}",
            )
            self._finish_gunner_build()
            return False

        self._finish_gunner_build()
        return False

    # ------------------------------------------------------------------
    # Healing patrol
    # ------------------------------------------------------------------

    def _run_heal_patrol(self, ct: Controller) -> None:
        """Walk along own tree, healing damaged buildings and checking for threats."""
        # Check for enemy turrets to counter with gunners.
        if self._check_for_threats(ct):
            return

        if ct.get_action_cooldown() == 0:
            for pos in self._nearby_tree_positions():
                if self.my_pos.distance_squared(pos) <= 2:
                    if ct.can_heal(pos):
                        ct.heal(pos)
                        dbg(f"r={self.round_no} id={self.my_id} heal patrol at {pos}")
                        return

        if (
            self.heal_target is None
            or self.my_pos.distance_squared(self.heal_target) <= 2
        ):
            self.heal_target = self._pick_heal_target()

        if self.heal_target is not None:
            dbg(
                f"r={self.round_no} id={self.my_id} heal patrol walk to {self.heal_target}",
            )
            self._walk_toward(ct, self.heal_target, best_effort=True)
        else:
            dbg(
                f"r={self.round_no} id={self.my_id} heal patrol: no target (tree={len(self.my_tree)} nodes)",
            )

    def _pick_heal_target(self) -> Position | None:
        """Pick a tree node to patrol toward. Cycles through nodes sorted by
        distance to core — spends more time near trunk, less at branches.
        """
        if not self.my_tree or self.my_pos is None:
            return self.core_pos
        # Sort by distance to core — patrol trunk first, branches later.
        cp = self.core_pos
        if cp is not None:
            nodes = sorted(self.my_tree, key=lambda p: p.distance_squared(cp))
        else:
            nodes = sorted(self.my_tree, key=lambda p: (p.x, p.y))
        if self.heal_target in self.my_tree:
            try:
                idx = nodes.index(self.heal_target)
                return nodes[(idx + 1) % len(nodes)]
            except ValueError:
                pass
        # Initial pick: start near core.
        return nodes[0] if nodes else None

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
        # Switch to maintenance when: 4+ harvesters, OR 1+ harvesters and sector exhausted.
        # Builders with any infrastructure should protect it.
        total_harvs = (
            sum(self.tree_harvester_counts) if self.tree_harvester_counts else 0
        )
        sector_exhausted = self._sector_explore_target() is None
        if self.my_tree and (
            total_harvs >= 4 or (total_harvs >= 1 and sector_exhausted)
        ):
            self._run_heal_patrol(ct)
            return

        # Sector exploration first (discover ore on our side).
        if (
            self.explore_target is None
            or self.my_pos.distance_squared(self.explore_target) <= 8
        ):
            if self.explore_target is not None:
                self.explore_radius_step += 1
            self.explore_target = self._sector_explore_target()
            if self.explore_target is None:
                # Sector exhausted — push into enemy territory.
                # Walk toward nearest known enemy building to discover their infra.
                # Fall back to enemy core, 180° guess, or map center.
                if not hasattr(self, "_visited_enemy"):
                    self._visited_enemy: set[Position] = set()
                best_enemy = None
                best_enemy_dist = 999
                for epos, (_, etype, eteam) in self.known_buildings.items():
                    if eteam == self.my_team:
                        continue
                    if etype in {EntityType.ROAD, EntityType.MARKER}:
                        continue
                    # Skip turrets (don't walk into fire) and already visited.
                    if etype in {
                        EntityType.SENTINEL,
                        EntityType.GUNNER,
                        EntityType.BREACH,
                        EntityType.LAUNCHER,
                    }:
                        continue
                    if epos in self._visited_enemy:
                        continue
                    d = self.my_pos.distance_squared(epos)
                    if d < best_enemy_dist:
                        best_enemy_dist = d
                        best_enemy = epos
                if best_enemy is not None:
                    self.explore_target = best_enemy
                    if self.my_pos.distance_squared(best_enemy) <= 8:
                        self._visited_enemy.add(best_enemy)
                else:
                    ecore = self.enemy_core_pos
                    if (
                        ecore is None
                        and self.enemy_core_candidates
                        and not self.symmetry_eliminated[2]
                    ):
                        ecore = self.enemy_core_candidates[2]
                    if ecore is not None:
                        if self.my_pos.distance_squared(ecore) <= 64:
                            ox = ecore.x + random.randint(-6, 6)
                            oy = ecore.y + random.randint(-6, 6)
                            ox = max(0, min((self.map_w or 40) - 1, ox))
                            oy = max(0, min((self.map_h or 40) - 1, oy))
                            self.explore_target = Position(ox, oy)
                        else:
                            self.explore_target = ecore
                    elif self.map_w is not None and self.map_h is not None:
                        self.explore_target = Position(self.map_w // 2, self.map_h // 2)
                    else:
                        self.explore_target = self._random_explore_target()
                if self.explore_target is not None:
                    dbg(
                        f"r={self.round_no} id={self.my_id} offensive: advancing toward {self.explore_target}",
                    )

        if self.explore_target is not None:
            # Offensive attack: try to place gunner targeting enemy infra/core.
            if self.gunner_build is None and self._attack_target is None:
                if self._try_start_attack(ct):
                    return
            # Continue existing attack (building harvester or routing chain).
            if self._attack_target is not None:
                if self._continue_attack(ct):
                    return
            # Opportunistic sentinel: if we see an exposed enemy harvester, parasite it.
            if self.gunner_build is None and self._try_opportunistic_sentinel(ct):
                return
            dbg(
                f"r={self.round_no} id={self.my_id} sector={self.sector_index} exploring toward {self.explore_target}",
            )
            if not self._walk_toward(ct, self.explore_target, best_effort=True):
                if self._stuck_turns >= 5:
                    self.explore_radius_step += 1
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
            info = self.visible_buildings.get(ore) or self.known_buildings.get(ore)
            if info is not None:
                _, etype, team = info
                if etype == EntityType.HARVESTER:
                    if team == self.my_team:
                        self.claimed_ores.add(ore)
                    continue  # skip any harvester, own or enemy
                if team != self.my_team:
                    continue  # skip any enemy building
                # Skip own buildings we can't clear for harvester placement.
                # _try_build_harvester clears roads, barriers, markers.
                if etype not in {
                    EntityType.ROAD,
                    EntityType.BARRIER,
                    EntityType.MARKER,
                }:
                    continue

            # After 2+ harvesters connected, consider all ore (expand into enemy half).
            total_harvs = (
                sum(self.tree_harvester_counts) if self.tree_harvester_counts else 0
            )
            skip_enemy_half = total_harvs < 2
            if skip_enemy_half and self._in_enemy_half(ore):
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

    def _can_afford(self, ct: Controller, cost: int) -> bool:
        """Check if we can spend `cost` Ti while keeping a defense reserve.

        Reserve = DEFENSE_RESERVE_SETS * (current gunner cost + splitter cost).
        Bypassed when actively building defense or mid-connect (chain completion
        restores income — don't let reserve prevent reconnection).
        """
        if self.gunner_build is not None or self.connecting or self.task == "repair":
            titanium, _ = ct.get_global_resources()
            return titanium >= cost
        reserve = DEFENSE_RESERVE_SETS * (
            ct.get_gunner_cost()[0] + ct.get_splitter_cost()[0]
        )
        titanium, _ = ct.get_global_resources()
        return titanium >= cost + reserve

    def _in_bounds(self, pos: Position) -> bool:
        if self.map_w is None or self.map_h is None:
            return True
        return 0 <= pos.x < self.map_w and 0 <= pos.y < self.map_h
