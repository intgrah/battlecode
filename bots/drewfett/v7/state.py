"""Builder state — belief state + capacity model.

Combines v2 state tracking with per-branch capacity awareness.
Each builder maintains:
- Building belief map (env, building arrays)
- Transport network topology (connected sets)
- Per-branch load tracking (harvesters per branch, bottleneck)
- Tree validity flags (per-branch invalidation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cambc import Controller, GameConstants, Position

if TYPE_CHECKING:
    from building import Building
    from nav import NavBfs
    from util import Symmetry


class State:
    def __init__(self, ct: Controller, core_pos: Position) -> None:
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        n = self.w * self.h
        self.my_team = ct.get_team()
        self.birthday = ct.get_current_round()
        self.age = 0
        self.core_pos = core_pos
        self.pos: Position = ct.get_position()

        self.core_tiles: set[int] = {
            (core_pos.y + dy) * self.w + (core_pos.x + dx)
            for dx in range(-1, 2)
            for dy in range(-1, 2)
            if 0 <= core_pos.x + dx < self.w and 0 <= core_pos.y + dy < self.h
        }

        # Belief map
        self.env: list = [None] * n
        self.building: list[Building | None] = [None] * n
        self.last_seen: list[int] = [0] * n

        # Nav
        self.nav: NavBfs | None = None

        # Symmetry
        self.symmetry: Symmetry | None = None

        # Ore
        self.ore_ti: set[int] = set()

        # Friendly sets
        self.my_harvesters: set[int] = set()
        self.my_transport: set[int] = set()
        self.my_turrets: set[int] = set()
        self.my_core_hp: int = GameConstants.CORE_MAX_HP

        # Enemy sets
        self.en_core_pos: Position | None = None
        self.en_core_tiles: set[int] = set()
        self.en_harvesters: set[int] = set()
        self.en_transport: set[int] = set()
        self.en_turrets: set[int] = set()

        # ── Capacity model ──
        # Connected network (tiles reachable from core through friendly transport)
        self.connected_transport: set[int] = set()
        self.connected_harvesters: set[int] = set()

        # Per-tile load: number of harvesters whose path passes through tile
        self.load: dict[int, int] = {}
        # Per-branch load: branch_id (core-adjacent tile) -> harvester count
        self.branch_load: dict[int, int] = {}
        # Bottleneck: tile -> max load on path from tile to core
        self.bottleneck: dict[int, int] = {}
        # Branch ID per transport tile: tile -> branch_id
        self.tile_branch: dict[int, int] = {}
        # Parent map: tile -> tile it outputs to (toward core)
        self._parent: dict[int, int] = {}
        # Bridge lookup: target_tile_index -> list of bridge tile indices
        self.bridges_by_target: dict[int, list[int]] = {}

        # Flow tracking: tile index -> freshness (4 = just seen with Ti, decays)
        self.flow_seen: dict[int, int] = {}

        # Ephemeral (reset each turn)
        self.unit_tiles: set[Position] = set()
        self.danger_zones: set[int] = set()
        self.enemy_bots_nearby: bool = False

        # Explore
        self.en_core_estimate: Position | None = None

    @property
    def tiles_with_flow(self) -> set[int]:
        return {ti for ti, f in self.flow_seen.items() if f > 0}

    def idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h
