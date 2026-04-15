"""Unified flow model — directed graph of transport connections."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from building import (
    TRANSPORT,
    BuildingArmouredConveyor,
    BuildingBreach,
    BuildingBridge,
    BuildingConveyor,
    BuildingGunner,
    BuildingHarvester,
    BuildingMarker,
    BuildingRoad,
    BuildingSentinel,
    BuildingSplitter,
)
from cambc import Environment
from util import DIR4_DELTA

if TYPE_CHECKING:
    from state import State


class FlowModel:
    """Directed flow graph built from transport buildings.

    Tracks both our team and enemy transport. Provides queries for:
    - Forward/backward path tracing
    - Source/sink/leak classification
    - Connectivity (replaces state_update._update_connectivity)
    - Capacity (replaces state_update._update_capacity)
    - Feed verification for turrets
    - Flow frontier (where chains can extend)
    - Enemy flow interception points
    """

    __slots__ = (
        "_bwd",
        "_en_fwd",
        "_en_sources",
        "_fwd",
        "_leaks",
        "_parent",
        "_s",
        "_sinks",
        "_sources",
        "_w",
        "bottleneck",
        "branch_load",
        "connected",
        "connected_harvesters",
        "load",
        "tile_branch",
    )

    def __init__(self, s: State) -> None:
        self._s = s
        self._w = s.w
        self._fwd: dict[int, list[int]] = {}
        self._bwd: dict[int, list[int]] = {}
        self._sources: set[int] = set()
        self._sinks: set[int] = set()
        self._leaks: set[int] = set()
        self.connected: set[int] = set()
        self.connected_harvesters: set[int] = set()
        self._fed: set[int] = set()  # tiles reachable from any harvester via _fwd
        self._parent: dict[int, int] = {}
        self.load: dict[int, int] = {}
        self.bottleneck: dict[int, int] = {}
        self.branch_load: dict[int, int] = {}
        self.tile_branch: dict[int, int] = {}
        self._en_fwd: dict[int, list[int]] = {}
        self._en_sources: set[int] = set()

    # ── Build (called once per turn) ───────────────────────

    def build(self) -> None:
        self._build_graph()
        self._classify()
        self._bfs_connectivity()
        self._bfs_from_sources()  # mark tiles fed by any harvester
        self._trace_capacity()
        self._build_enemy_graph()

    def _build_graph(self) -> None:
        """Build forward/backward adjacency from our buildings."""
        s = self._s
        fwd: dict[int, list[int]] = {}
        bwd: dict[int, list[int]] = {}

        for ti in s.my_transport | s.my_harvesters:
            outputs = self._get_outputs(ti)
            if outputs:
                fwd[ti] = outputs
                for oi in outputs:
                    bwd.setdefault(oi, []).append(ti)

        # Core tiles accept from all cardinal neighbors
        for _ci in s.core_tiles:
            # Don't add forward edges from core (core doesn't output)
            # But add backward edges: anything adjacent that outputs toward core
            pass  # handled by fwd/bwd of transport tiles pointing at core

        self._fwd = fwd
        self._bwd = bwd

    def _classify(self) -> None:
        """Mark sources, sinks, and leak points."""
        s = self._s
        self._sources = set(s.my_harvesters)
        self._sinks = set(s.core_tiles)

        # Ammo-consuming turrets are sinks
        for ti in s.my_transport | s.core_tiles:
            bld = s.building[ti]
            if isinstance(bld, (BuildingGunner, BuildingSentinel, BuildingBreach)):
                self._sinks.add(ti)

        # Leaks: our transport whose outputs go nowhere useful
        leaks: set[int] = set()
        for ti in s.my_transport:
            outputs = self._fwd.get(ti, [])
            if not outputs:
                leaks.add(ti)
                continue
            all_dead = True
            for oi in outputs:
                bld = s.building[oi]
                if bld is None:
                    all_dead = True  # empty = leak (no receiver)
                    continue
                if oi in s.core_tiles:
                    all_dead = False
                    break
                if bld.team == s.my_team:
                    all_dead = False
                    break
                # Enemy building = our flow goes to enemy = also a leak
            if all_dead:
                leaks.add(ti)
        self._leaks = leaks

    def _bfs_connectivity(self) -> None:
        """BFS from core backward through _bwd. Replaces state_update._update_connectivity."""
        s = self._s
        core_tiles = s.core_tiles

        visited: set[int] = set(core_tiles)
        queue: deque[int] = deque(core_tiles)
        connected_transport: set[int] = set()
        connected_harvesters: set[int] = set()
        parent: dict[int, int] = {}

        while queue:
            ci = queue.popleft()
            # Check backward edges (tiles that output toward ci)
            for ni in self._bwd.get(ci, []):
                if ni in visited:
                    continue
                bld = s.building[ni]
                if bld is None or bld.team != s.my_team:
                    continue
                visited.add(ni)
                parent[ni] = ci
                if ni in s.my_transport:
                    connected_transport.add(ni)
                    queue.append(ni)
                elif ni in s.my_harvesters:
                    connected_harvesters.add(ni)
                    # Don't enqueue harvesters — they're leaves

        self.connected = connected_transport
        self.connected_harvesters = connected_harvesters
        self._parent = parent

    def _bfs_from_sources(self) -> None:
        """BFS forward from all harvesters through _fwd. Marks all tiles that are fed."""
        fed: set[int] = set(self._sources)
        queue: deque[int] = deque(self._sources)
        while queue:
            ti = queue.popleft()
            for ni in self._fwd.get(ti, []):
                if ni not in fed:
                    fed.add(ni)
                    queue.append(ni)
        self._fed = fed

    def _trace_capacity(self) -> None:
        """Compute load and bottleneck. Replaces state_update._update_capacity."""
        core_tiles = self._s.core_tiles
        parent = self._parent

        # Load: count harvesters per path tile
        load: dict[int, int] = {}
        for hi in self.connected_harvesters:
            current = parent.get(hi)
            seen: set[int] = set()
            while current is not None:
                if current in seen:
                    break
                seen.add(current)
                load[current] = load.get(current, 0) + 1
                if current in core_tiles:
                    break
                current = parent.get(current)

        # Bottleneck: max load from tile to core (BFS from core outward)
        children: dict[int, list[int]] = {}
        for child, par in parent.items():
            children.setdefault(par, []).append(child)

        bottleneck: dict[int, int] = {}
        bfs_q: deque[int] = deque()
        for ct_tile in core_tiles:
            bottleneck[ct_tile] = load.get(ct_tile, 0)
            bfs_q.append(ct_tile)
        while bfs_q:
            ti = bfs_q.popleft()
            parent_bn = bottleneck[ti]
            for child in children.get(ti, []):
                child_load = load.get(child, 0)
                bottleneck[child] = max(parent_bn, child_load)
                bfs_q.append(child)

        # Branch load
        branch_load: dict[int, int] = {}
        tile_branch: dict[int, int] = {}
        for hi in self.connected_harvesters:
            current = parent.get(hi)
            prev = hi
            seen: set[int] = set()
            while current is not None and current not in core_tiles:
                if current in seen:
                    break
                seen.add(current)
                prev = current
                current = parent.get(current)
            if current in core_tiles:
                tile_branch[hi] = prev
                branch_load[prev] = branch_load.get(prev, 0) + 1

        self.load = load
        self.bottleneck = bottleneck
        self.branch_load = branch_load
        self.tile_branch = tile_branch

    def _build_enemy_graph(self) -> None:
        """Lightweight enemy forward edges."""
        s = self._s
        en_fwd: dict[int, list[int]] = {}
        for ti in s.en_transport | s.en_harvesters:
            outputs = self._get_outputs(ti)
            if outputs:
                en_fwd[ti] = outputs
        self._en_fwd = en_fwd
        self._en_sources = set(s.en_harvesters)

    # ── Core: single source of truth for outputs ───────────

    def _get_outputs(self, ti: int) -> list[int]:
        """Output tiles for any building. ONE function, used everywhere."""
        s = self._s
        w = self._w
        bld = s.building[ti]
        if bld is None:
            return []
        x, y = ti % w, ti // w
        match bld:
            case BuildingConveyor(direction=d) | BuildingArmouredConveyor(direction=d):
                dx, dy = d.delta()
                nx, ny = x + dx, y + dy
                return [ny * w + nx] if s.in_bounds(nx, ny) else []
            case BuildingSplitter(direction=d):
                dx, dy = d.delta()
                result = []
                for odx, ody in [(dx, dy), (-dy, dx), (dy, -dx)]:
                    nx, ny = x + odx, y + ody
                    if s.in_bounds(nx, ny):
                        result.append(ny * w + nx)
                return result
            case BuildingBridge(target=tgt):
                return [tgt.y * w + tgt.x] if s.in_bounds(tgt.x, tgt.y) else []
            case BuildingHarvester():
                result = []
                for dx, dy in DIR4_DELTA:
                    nx, ny = x + dx, y + dy
                    if s.in_bounds(nx, ny):
                        result.append(ny * w + nx)
                return result
        return []

    # ── Queries ────────────────────────────────────────────

    def outputs_of(self, ti: int) -> list[int]:
        """Forward edges from tile."""
        return self._fwd.get(ti, [])

    def inputs_to(self, ti: int) -> list[int]:
        """Backward edges into tile."""
        return self._bwd.get(ti, [])

    @property
    def sources(self) -> set[int]:
        return self._sources

    @property
    def sinks(self) -> set[int]:
        return self._sinks

    @property
    def leaks(self) -> set[int]:
        return self._leaks

    def parent_of(self, ti: int) -> int | None:
        return self._parent.get(ti)

    def trace_forward(self, tile: int, max_depth: int = 50) -> list[int]:
        """Trace flow forward from tile. Returns path until sink or dead end."""
        path = [tile]
        visited: set[int] = {tile}
        current = tile
        for _ in range(max_depth):
            outputs = self._fwd.get(current, [])
            if not outputs:
                break
            nxt = outputs[0]  # primary output
            if nxt in visited:
                break
            visited.add(nxt)
            path.append(nxt)
            if nxt in self._sinks:
                break
            current = nxt
        return path

    def trace_backward(self, tile: int, max_depth: int = 50) -> list[int]:
        """Trace flow backward from tile. Returns path until source or dead end."""
        path = [tile]
        visited: set[int] = {tile}
        current = tile
        for _ in range(max_depth):
            inputs = self._bwd.get(current, [])
            if not inputs:
                break
            nxt = inputs[0]  # primary input
            if nxt in visited:
                break
            visited.add(nxt)
            path.append(nxt)
            if nxt in self._sources:
                break
            current = nxt
        return path

    def feeds_sink(self, tile: int) -> bool:
        """Does flow from this tile eventually reach a sink?"""
        visited: set[int] = {tile}
        current = tile
        for _ in range(50):
            outputs = self._fwd.get(current, [])
            if not outputs:
                return False
            nxt = outputs[0]
            if nxt in self._sinks or nxt in self._s.core_tiles:
                return True
            if nxt in visited:
                return False
            visited.add(nxt)
            current = nxt
        return False

    def has_source(self, tile: int) -> bool:
        """Is this tile fed by a harvester? O(1) lookup from precomputed _fed set."""
        return tile in self._fed

    def has_feed_for_turret(
        self, turret_ti: int, facing_dx: int, facing_dy: int
    ) -> bool:
        """Check if a turret at turret_ti with given facing has verified ammo feed.

        Valid feed = adjacent non-facing cardinal tile with:
        - Harvester (any team, outputs all 4 cardinal)
        - Transport outputting toward turret_ti that either:
          a) has flow now (connected to econ or tiles_with_flow), OR
          b) traces back to a harvester (chain will carry Ti soon)
        """
        s = self._s
        w = self._w
        tx, ty = turret_ti % w, turret_ti // w
        for dx, dy in DIR4_DELTA:
            if (dx, dy) == (facing_dx, facing_dy):
                continue  # facing side can't receive
            ax, ay = tx + dx, ty + dy
            if not s.in_bounds(ax, ay):
                continue
            ai = ay * w + ax
            bld = s.building[ai]
            if bld is None:
                continue
            if isinstance(bld, BuildingHarvester):
                return True  # harvester outputs all 4 cardinal
            # Transport pointing at turret?
            outputs_here = turret_ti in self._fwd.get(
                ai, []
            ) or turret_ti in self._en_fwd.get(ai, [])
            if not outputs_here:
                continue
            # Has flow now?
            if ai in self.connected or ai in s.tiles_with_flow:
                return True
            # Or traces back to a harvester (fresh attack chain)?
            if self.has_source(ai):
                return True
        return False

    def flow_frontier(self) -> list[tuple[int, int]]:
        """Find (transport_tile, gap_tile) pairs where our transport with flow
        outputs to a buildable tile. These are where attack chains can extend.

        Returns list sorted by distance to nearest enemy building.
        """
        s = self._s
        result: list[tuple[int, int]] = []
        for ti, outputs in self._fwd.items():
            bld = s.building[ti]
            if bld is None or bld.team != s.my_team:
                continue
            # Must have flow (connected to econ or seen with Ti)
            if ti not in self.connected and ti not in s.tiles_with_flow:
                continue
            for oi in outputs:
                if s.env[oi] == Environment.WALL:
                    continue
                obld = s.building[oi]
                if obld is None or isinstance(obld, (BuildingRoad, BuildingMarker)):
                    result.append((ti, oi))
                elif obld.team != s.my_team and isinstance(obld, TRANSPORT):
                    result.append((ti, oi))  # enemy transport = parasitize
        return result

    def enemy_tappable(self) -> list[tuple[int, int]]:
        """Find enemy transport tiles that output to a tile we could build on.

        Returns list of (enemy_transport_tile, buildable_output_tile).
        """
        s = self._s
        result: list[tuple[int, int]] = []
        for ti, outputs in self._en_fwd.items():
            if ti not in s.tiles_with_flow:
                continue
            if ti in s.danger_zones:
                continue
            for oi in outputs:
                if s.env[oi] == Environment.WALL:
                    continue
                if oi in s.danger_zones:
                    continue
                obld = s.building[oi]
                if obld is None or isinstance(obld, (BuildingRoad, BuildingMarker)):
                    result.append((ti, oi))
        return result
