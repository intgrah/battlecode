import heapq
import sys
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from PIL import Image, ImageDraw

from proto import cambc_pb2

type Pos = tuple[int, int]


@dataclass(frozen=True)
class MapGrid:
    w: int
    h: int
    walls: frozenset[Pos]
    ti_ores: tuple[Pos, ...]
    ax_ores: tuple[Pos, ...]
    core: Pos
    ore_set: frozenset[Pos] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ore_set",
            frozenset(self.ti_ores) | frozenset(self.ax_ores),
        )

    def in_bounds(self, p: Pos) -> bool:
        return 0 <= p[0] < self.w and 0 <= p[1] < self.h


def kmeans[T](
    points: list[T],
    k: int,
    dist: Callable[[T, T], float],
    mean: Callable[[list[T]], T],
    max_iter: int = 100,
) -> tuple[list[int], list[T]]:
    """Lloyd's algorithm. Returns (assignments, centres)."""
    n = len(points)
    assert k <= n
    rng = Random(42)
    centres = rng.sample(points, k)
    assignments = [0] * n
    for _ in range(max_iter):
        changed = False
        for i, p in enumerate(points):
            nearest = min(range(k), key=lambda c: dist(p, centres[c]))
            if nearest != assignments[i]:
                changed = True
                assignments[i] = nearest
        if not changed:
            break
        for ci in range(k):
            members = [p for p, a in zip(points, assignments, strict=True) if a == ci]
            if members:
                centres[ci] = mean(members)
    return assignments, centres


type Flow = tuple[float, float, float]

DIR4: tuple[Pos, ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))

OPPOSITE: dict[Pos, Pos] = {
    (-1, 0): (1, 0),
    (1, 0): (-1, 0),
    (0, -1): (0, 1),
    (0, 1): (0, -1),
}


def perpendiculars(d: Pos) -> tuple[Pos, Pos]:
    dx, dy = d
    return (-dy, dx), (dy, -dx)


class EntityType:
    CONVEYOR = "conveyor"
    BRIDGE = "bridge"
    HARVESTER_TI = "harvester_ti"
    HARVESTER_AX = "harvester_ax"
    FOUNDRY = "foundry"
    SPLITTER = "splitter"
    CORE = "core"


@dataclass
class Entity:
    etype: str
    pos: Pos
    direction: Pos | None = None
    bridge_target: Pos | None = None


@dataclass
class Network:
    entities: dict[Pos, Entity]

    def outputs(self, pos: Pos) -> list[Pos]:
        """Tiles that this entity sends flow to."""
        ent = self.entities.get(pos)
        if ent is None:
            return []
        match ent.etype:
            case EntityType.CONVEYOR:
                assert ent.direction is not None
                dx, dy = ent.direction
                dst = (pos[0] + dx, pos[1] + dy)
                return [dst] if dst in self.entities else []
            case EntityType.BRIDGE:
                assert ent.bridge_target is not None
                return [ent.bridge_target] if ent.bridge_target in self.entities else []
            case EntityType.SPLITTER:
                assert ent.direction is not None
                result = []
                for d in (ent.direction, *perpendiculars(ent.direction)):
                    dst = (pos[0] + d[0], pos[1] + d[1])
                    if dst in self.entities and self.accepts_from(dst, OPPOSITE[d]):
                        result.append(dst)
                return result
            case EntityType.HARVESTER_TI | EntityType.HARVESTER_AX:
                result = []
                for d in DIR4:
                    dst = (pos[0] + d[0], pos[1] + d[1])
                    if dst in self.entities and self.accepts_from(dst, OPPOSITE[d]):
                        result.append(dst)
                return result
            case EntityType.FOUNDRY:
                result = []
                for d in DIR4:
                    dst = (pos[0] + d[0], pos[1] + d[1])
                    if dst in self.entities and self.accepts_from(dst, OPPOSITE[d]):
                        result.append(dst)
                return result
            case EntityType.CORE:
                return []
            case _:
                return []

    def accepts_from(self, pos: Pos, from_dir: Pos) -> bool:
        """Does the entity at pos accept input from direction from_dir?
        from_dir is the direction FROM which the input arrives (e.g. (-1,0) means input comes from the west).
        """
        ent = self.entities.get(pos)
        if ent is None:
            return False
        match ent.etype:
            case EntityType.CONVEYOR:
                assert ent.direction is not None
                return from_dir != ent.direction
            case EntityType.BRIDGE:
                return True
            case EntityType.SPLITTER:
                assert ent.direction is not None
                return from_dir == OPPOSITE[ent.direction]
            case EntityType.HARVESTER_TI | EntityType.HARVESTER_AX:
                return False
            case EntityType.FOUNDRY:
                return True
            case EntityType.CORE:
                return True
            case _:
                return False

    def output_targets(self, pos: Pos) -> list[Pos]:
        """Tiles that this entity COULD output toward, regardless of what's there.
        Unlike outputs(), this doesn't check if the destination accepts.
        """
        ent = self.entities.get(pos)
        if ent is None:
            return []
        match ent.etype:
            case EntityType.CONVEYOR:
                assert ent.direction is not None
                dx, dy = ent.direction
                return [(pos[0] + dx, pos[1] + dy)]
            case EntityType.BRIDGE:
                assert ent.bridge_target is not None
                return [ent.bridge_target]
            case EntityType.SPLITTER:
                assert ent.direction is not None
                return [
                    (pos[0] + d[0], pos[1] + d[1])
                    for d in (ent.direction, *perpendiculars(ent.direction))
                ]
            case EntityType.HARVESTER_TI | EntityType.HARVESTER_AX:
                return [(pos[0] + d[0], pos[1] + d[1]) for d in DIR4]
            case EntityType.FOUNDRY:
                return [(pos[0] + d[0], pos[1] + d[1]) for d in DIR4]
            case _:
                return []

    def build_graph(self) -> dict[Pos, list[Pos]]:
        """Build the adjacency list from the entity placement."""
        graph: dict[Pos, list[Pos]] = {}
        for pos in self.entities:
            graph[pos] = self.outputs(pos)
        return graph


def compute_flow(network: Network) -> dict[Pos, Flow]:
    """Compute per-tile commodity flow using Kahn's topological sort.

    Harvesters produce 0.25 of their commodity.
    Foundries consume min(ti_in, ax_in) of each, produce that much rax.
    All other entities pass through flow unchanged.
    Flow is split equally across all outputs.

    Precondition: the network graph is a DAG.
    Returns: per-tile (ti, ax, rax) accumulated input flow.
    """
    graph = network.build_graph()

    nodes = set(graph.keys())
    for dsts in graph.values():
        nodes.update(dsts)

    in_degree: dict[Pos, int] = dict.fromkeys(nodes, 0)
    for dsts in graph.values():
        for v in dsts:
            in_degree[v] += 1

    flow: dict[Pos, Flow] = dict.fromkeys(nodes, (0.0, 0.0, 0.0))

    for pos in nodes:
        ent = network.entities.get(pos)
        if ent is None:
            continue
        match ent.etype:
            case EntityType.HARVESTER_TI:
                flow[pos] = (0.25, 0.0, 0.0)
            case EntityType.HARVESTER_AX:
                flow[pos] = (0.0, 0.25, 0.0)

    queue = deque(n for n in nodes if in_degree[n] == 0)

    while queue:
        u = queue.popleft()
        ti, ax, rax = flow[u]

        ent = network.entities.get(u)
        if ent is not None and ent.etype == EntityType.FOUNDRY:
            refined = min(ti, ax)
            out_ti = ti - refined
            out_ax = ax - refined
            out_rax = rax + refined
        else:
            out_ti, out_ax, out_rax = ti, ax, rax

        outputs = graph.get(u, [])
        n_out = len(outputs)
        if n_out > 0:
            for v in outputs:
                vti, vax, vrax = flow[v]
                flow[v] = (
                    vti + out_ti / n_out,
                    vax + out_ax / n_out,
                    vrax + out_rax / n_out,
                )
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

    return flow


CONV_COST = 3
BRIDGE_COST = 20
BRIDGE_DELTAS: tuple[Pos, ...] = tuple(
    (dx, dy) for dx in range(-3, 4) for dy in range(-3, 4) if 1 < dx * dx + dy * dy <= 9
)


def compute_banned(
    network: Network,
    tile_commodity: dict[Pos, str],
    commodity: str,
) -> frozenset[Pos]:
    """Compute tiles banned for building a chain carrying `commodity`.

    A tile X is banned if any adjacent entity outputs toward X and carries
    an incompatible commodity. This is directional: a conveyor only bans
    the tile in its output direction, not all 4 neighbours.
    """
    banned: set[Pos] = set()
    for pos, ent in network.entities.items():
        if ent.etype == EntityType.FOUNDRY:
            continue
        output_commodity = tile_commodity.get(pos)
        if output_commodity is None or output_commodity == commodity:
            continue
        for target in network.output_targets(pos):
            banned.add(target)
    return frozenset(banned)


def astar(
    grid: MapGrid,
    source: Pos,
    goals: frozenset[Pos],
    blocked: frozenset[Pos],
    tile_cost: dict[Pos, float] | None = None,
    network: Network | None = None,
) -> list[Pos] | None:
    """A* on a grid. Cardinal moves cost CONV_COST, bridge jumps cost BRIDGE_COST.
    tile_cost overrides the cost for specific tiles (e.g. 0 for reuse).
    Tiles in `blocked` are impassable.
    If network is provided, existing entities must accept from the arrival direction.
    Heuristic: min manhattan to any goal (admissible since min edge cost can be 0).
    """
    if source in goals:
        return [source]
    if not goals:
        return None

    goal_tuple = tuple(goals)
    inf = float("inf")

    def h(p: Pos) -> float:
        return min(abs(p[0] - g[0]) + abs(p[1] - g[1]) for g in goal_tuple)

    g_cost: dict[Pos, float] = {source: 0}
    parent: dict[Pos, Pos | None] = {source: None}
    heap: list[tuple[float, Pos]] = [(h(source), source)]

    while heap:
        f_val, cur = heapq.heappop(heap)

        if cur in goals:
            path: list[Pos] = []
            n: Pos | None = cur
            while n is not None:
                path.append(n)
                n = parent[n]
            path.reverse()
            return path

        gc = g_cost.get(cur, inf)
        if f_val > gc + h(cur):
            continue

        cx, cy = cur

        for dx, dy in DIR4:
            npos = (cx + dx, cy + dy)
            if not grid.in_bounds(npos):
                continue
            if npos in blocked:
                continue
            if network is not None and npos in network.entities:
                from_dir = (-dx, -dy)
                if not network.accepts_from(npos, from_dir):
                    continue
            if tile_cost is not None and npos in tile_cost:
                cost = tile_cost[npos]
            else:
                cost = CONV_COST
            new_g = gc + cost
            if new_g < g_cost.get(npos, inf):
                g_cost[npos] = new_g
                parent[npos] = cur
                heapq.heappush(heap, (new_g + h(npos), npos))

        for dx, dy in BRIDGE_DELTAS:
            npos = (cx + dx, cy + dy)
            if not grid.in_bounds(npos):
                continue
            if npos in blocked:
                continue
            if network is not None and npos in network.entities:
                from_dir = (-dx, -dy)
                if not network.accepts_from(npos, from_dir):
                    continue
            cost = BRIDGE_COST
            new_g = gc + cost
            if new_g < g_cost.get(npos, inf):
                g_cost[npos] = new_g
                parent[npos] = cur
                heapq.heappush(heap, (new_g + h(npos), npos))

    return None


def load_map(path: str) -> MapGrid:
    with Path(path).open("rb") as f:
        mm = cambc_pb2.Map()
        mm.ParseFromString(f.read())

    w, h = mm.width, mm.height
    ti: list[Pos] = []
    ax: list[Pos] = []
    walls: set[Pos] = set()
    for y, row in enumerate(mm.rows):
        for x, tile in enumerate(row.tiles):
            if tile == 1:
                walls.add((x, y))
            elif tile == 2:
                ti.append((x, y))
            elif tile == 3:
                ax.append((x, y))

    core: Pos = next((c.position.x, c.position.y) for c in mm.cores if c.team == 0)
    return MapGrid(
        w=w,
        h=h,
        walls=frozenset(walls),
        ti_ores=tuple(ti),
        ax_ores=tuple(ax),
        core=core,
    )


FOUNDRY_COST = 120
CAPACITY = 1.0


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def core_3x3(core: Pos, w: int, h: int) -> frozenset[Pos]:
    cx, cy = core
    return frozenset(
        (cx + dx, cy + dy)
        for dx in range(-1, 2)
        for dy in range(-1, 2)
        if 0 <= cx + dx < w and 0 <= cy + dy < h
    )


def pos_mean(points: list[Pos]) -> Pos:
    return (
        round(sum(p[0] for p in points) / len(points)),
        round(sum(p[1] for p in points) / len(points)),
    )


def place_foundry(
    grid: MapGrid,
    ax_members: list[Pos],
    ti_members: list[Pos],
    occupied: frozenset[Pos],
) -> Pos | None:
    all_pts = ax_members + ti_members
    cx, cy = pos_mean(all_pts)
    for r in range(40):
        best: Pos | None = None
        best_cost = float("inf")
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                pos = (cx + dx, cy + dy)
                if not grid.in_bounds(pos):
                    continue
                if pos in grid.walls or pos in grid.ore_set or pos in occupied:
                    continue
                cost = sum(manhattan(pos, m) for m in all_pts)
                cost += manhattan(pos, grid.core) // 2
                if cost < best_cost:
                    best_cost = cost
                    best = pos
        if best is not None:
            return best
    return None


def connect_sources(
    grid: MapGrid,
    network: Network,
    tile_commodity: dict[Pos, str],
    sources: list[Pos],
    dest_tiles: frozenset[Pos],
    commodity: str,
) -> int:
    """Connect each source to the tree rooted at dest_tiles using greedy A*.

    Places conveyors/bridges into network.entities. Tracks commodity per tile.
    Returns number of sources successfully connected.

    The tree grows with each connection. Same-commodity tiles in the tree
    are free to traverse (cost 0). New tiles cost CONV_COST or BRIDGE_COST.
    """
    tree: set[Pos] = set(dest_tiles)
    connected = 0

    sorted_src = sorted(sources, key=lambda s: min(manhattan(s, d) for d in dest_tiles))

    for src in sorted_src:
        # Find start tile: cardinal neighbour of source, not banned, not wall/ore
        banned = compute_banned(network, tile_commodity, commodity)
        best_start: Pos | None = None
        best_d = 999999
        for d in DIR4:
            n = (src[0] + d[0], src[1] + d[1])
            if not grid.in_bounds(n):
                continue
            if n in grid.walls or n in grid.ore_set:
                continue
            if n in banned and n not in tree:
                continue
            dist = min(manhattan(n, t) for t in tree)
            if dist < best_d:
                best_d = dist
                best_start = n
        if best_start is None:
            continue

        # Compute flow to find capacity
        flow = compute_flow(network)

        # Build tree parent map: each tile -> its output tile (toward root)
        tree_parent: dict[Pos, Pos | None] = {}
        for t in tree:
            outs = network.outputs(t)
            # Parent = the output tile that's also in the tree (toward root)
            parent_tile = None
            for o in outs:
                if o in tree:
                    parent_tile = o
                    break
            tree_parent[t] = parent_tile

        # A tile is available if adding 0.25 to every tile on the path to root
        # would not exceed capacity anywhere (except core tiles)
        ct_local = core_3x3(grid.core, grid.w, grid.h)
        full_tiles: set[Pos] = set()
        avail: set[Pos] = set()
        for t in tree:
            ok = True
            cur: Pos | None = t
            while cur is not None:
                total = sum(flow.get(cur, (0.0, 0.0, 0.0)))
                if total + 0.25 > CAPACITY + 0.01 and cur not in ct_local:
                    ok = False
                    break
                cur = tree_parent.get(cur)
            if ok:
                avail.add(t)
            else:
                full_tiles.add(t)
        if not avail:
            continue

        # Blocked: walls, ores, other-commodity tiles, banned tiles, full tree tiles
        blocked: set[Pos] = set()
        blocked |= grid.walls
        blocked |= grid.ore_set
        blocked |= banned
        blocked |= full_tiles
        for pos in network.entities:
            if pos not in tree and tile_commodity.get(pos) != commodity:
                blocked.add(pos)
        blocked -= avail

        # Cost for tree tiles: 0 if room for 2+ more, CONV_COST if last slot
        costs: dict[Pos, float] = {}
        for t in avail:
            total = sum(flow.get(t, (0.0, 0.0, 0.0)))
            if total + 0.50 <= CAPACITY + 0.01:
                costs[t] = 0
            else:
                costs[t] = CONV_COST

        path = astar(
            grid,
            best_start,
            frozenset(avail),
            frozenset(blocked),
            costs,
            network,
        )
        if path is None:
            continue

        # Place entities along the path
        new_tiles: list[Pos] = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            if a in network.entities:
                continue  # already built (reuse)
            dx = b[0] - a[0]
            dy = b[1] - a[1]
            if abs(dx) + abs(dy) == 1:
                network.entities[a] = Entity(
                    etype=EntityType.CONVEYOR,
                    pos=a,
                    direction=(dx, dy),
                )
            else:
                network.entities[a] = Entity(
                    etype=EntityType.BRIDGE,
                    pos=a,
                    bridge_target=b,
                )
            tile_commodity[a] = commodity
            tree.add(a)
            new_tiles.append(a)

        connected += 1

    return connected


# ── Visualization ─────────────────────────────────────────────────────────

TILE_PX = 48
PAD = 60
COLORS: dict[str, tuple[int, int, int]] = {
    "ti": (80, 140, 255),
    "ax": (255, 160, 40),
    "rax": (200, 130, 255),
    "foundry": (200, 50, 200),
}


def draw_network(
    network: Network,
    tile_commodity: dict[Pos, str],
    flow: dict[Pos, Flow],
    grid: MapGrid,
    out_path: str,
) -> None:
    iw = grid.w * TILE_PX + PAD * 2
    ih = grid.h * TILE_PX + PAD * 2
    img = Image.new("RGB", (iw, ih), (30, 25, 25))
    draw = ImageDraw.Draw(img)

    def txy(p: Pos) -> tuple[int, int]:
        return p[0] * TILE_PX + PAD, p[1] * TILE_PX + PAD

    def tcen(p: Pos) -> tuple[int, int]:
        return p[0] * TILE_PX + PAD + TILE_PX // 2, p[1] * TILE_PX + PAD + TILE_PX // 2

    # Background
    for y in range(grid.h):
        for x in range(grid.w):
            px, py = txy((x, y))
            if (x, y) in grid.walls:
                draw.rectangle([px, py, px + TILE_PX, py + TILE_PX], fill=(60, 45, 40))
            else:
                draw.rectangle(
                    [px, py, px + TILE_PX, py + TILE_PX],
                    fill=(35, 30, 28),
                    outline=(50, 45, 42),
                )

    # Transport tiles
    ct = core_3x3(grid.core, grid.w, grid.h)
    fp_set = {p for p, e in network.entities.items() if e.etype == EntityType.FOUNDRY}
    for pos in network.entities:
        if pos in grid.ore_set or pos in ct or pos in fp_set:
            continue
        c = COLORS.get(tile_commodity.get(pos, ""), (180, 180, 180))
        px, py = txy(pos)
        draw.rectangle([px + 2, py + 2, px + TILE_PX - 2, py + TILE_PX - 2], fill=c)

    # Bridge arcs
    for pos, ent in network.entities.items():
        if ent.etype == EntityType.BRIDGE and ent.bridge_target is not None:
            c = COLORS.get(tile_commodity.get(pos, ""), (180, 180, 180))
            draw.line([tcen(pos), tcen(ent.bridge_target)], fill=c, width=2)

    # Flow labels
    for pos, f in flow.items():
        total = sum(f)
        if total < 0.01:
            continue
        px, py = txy(pos)
        ti, ax, rax = f
        lines = []
        if ti > 0.001:
            lines.append(f"Ti{ti:.2f}")
        if ax > 0.001:
            lines.append(f"Ax{ax:.2f}")
        if rax > 0.001:
            lines.append(f"RAx{rax:.2f}")
        fc = (255, 80, 80) if total > CAPACITY else (220, 220, 220)
        for li, text in enumerate(lines):
            draw.text((px + 2, py + 2 + li * 12), text, fill=fc)

    # Ores
    for p in grid.ti_ores:
        px, py = txy(p)
        draw.rectangle(
            [px + 1, py + 1, px + TILE_PX - 1, py + TILE_PX - 1],
            fill=(40, 60, 120),
            outline=COLORS["ti"],
        )
        draw.text((px + TILE_PX // 4, py + TILE_PX // 3), "Ti", fill=(200, 220, 255))

    for p in grid.ax_ores:
        px, py = txy(p)
        draw.rectangle(
            [px + 1, py + 1, px + TILE_PX - 1, py + TILE_PX - 1],
            fill=(100, 60, 20),
            outline=COLORS["ax"],
        )
        draw.text((px + TILE_PX // 4, py + TILE_PX // 3), "Ax", fill=(255, 220, 180))

    # Foundries
    for pos, ent in network.entities.items():
        if ent.etype == EntityType.FOUNDRY:
            px, py = txy(pos)
            draw.rectangle(
                [px + 1, py + 1, px + TILE_PX - 1, py + TILE_PX - 1],
                fill=(120, 30, 120),
                outline=(200, 100, 200),
                width=2,
            )
            draw.text((px + 4, py + TILE_PX // 3), "Fnd", fill=(255, 200, 255))

    # Core
    for t in ct:
        px, py = txy(t)
        draw.rectangle(
            [px + 1, py + 1, px + TILE_PX - 1, py + TILE_PX - 1],
            fill=(30, 100, 50),
            outline=(80, 200, 100),
            width=2,
        )
    cx, cy = tcen(grid.core)
    draw.text((cx - 12, cy - 6), "Core", fill=(200, 255, 200))

    img.save(out_path)
    print(f"Saved to {out_path}")


# ── Validation ────────────────────────────────────────────────────────────


def validate(
    network: Network,
    tile_commodity: dict[Pos, str],
    flow: dict[Pos, Flow],
    grid: MapGrid,
) -> list[str]:
    errors: list[str] = []
    ct = core_3x3(grid.core, grid.w, grid.h)

    # 1. Congestion: no tile (except core) should exceed capacity
    for pos, f in flow.items():
        total = sum(f)
        if total > CAPACITY + 0.01 and pos not in ct:
            errors.append(f"CONGESTION: {pos} flow={total:.2f}")

    # 2. Leakage: no tile should receive incompatible commodity from a neighbour
    for pos, ent in network.entities.items():
        if ent.etype in (EntityType.FOUNDRY, EntityType.CORE):
            continue  # foundries and core accept all commodities
        my_commodity = tile_commodity.get(pos)
        if my_commodity is None:
            continue
        for target in network.output_targets(pos):
            target_ent = network.entities.get(target)
            if target_ent and target_ent.etype in (EntityType.FOUNDRY, EntityType.CORE):
                continue
            target_commodity = tile_commodity.get(target)
            if (
                target_commodity is not None
                and target_commodity != my_commodity
                and target in network.outputs(pos)
            ):
                errors.append(
                    f"LEAKAGE: {pos}({my_commodity}) -> {target}({target_commodity})",
                )

    # 3. Delivered flow
    ti_at_core = sum(flow.get(t, (0.0, 0.0, 0.0))[0] for t in ct)
    ax_at_core = sum(flow.get(t, (0.0, 0.0, 0.0))[1] for t in ct)
    rax_at_core = sum(flow.get(t, (0.0, 0.0, 0.0))[2] for t in ct)
    max_ti = len(grid.ti_ores) * 0.25
    max_ax = len(grid.ax_ores) * 0.25
    max_rax = min(max_ti, max_ax)

    errors.append(f"INFO: Ti at core = {ti_at_core:.2f} / {max_ti:.2f}")
    errors.append(f"INFO: RAx at core = {rax_at_core:.2f} / {max_rax:.2f}")
    if ax_at_core > 0.01:
        errors.append(f"WARNING: raw Ax at core = {ax_at_core:.2f} (destroyed)")

    return errors


# ── Build full network ────────────────────────────────────────────────────


def build_network(k_foundries: int, grid: MapGrid) -> tuple[Network, dict[Pos, str]]:
    n_ti = len(grid.ti_ores)
    n_ax = len(grid.ax_ores)

    network = Network(entities={})
    tile_commodity: dict[Pos, str] = {}

    # Place core
    ct = core_3x3(grid.core, grid.w, grid.h)
    for t in ct:
        network.entities[t] = Entity(etype=EntityType.CORE, pos=t)

    # Place harvesters
    for p in grid.ti_ores:
        network.entities[p] = Entity(etype=EntityType.HARVESTER_TI, pos=p)
        tile_commodity[p] = "ti"
    for p in grid.ax_ores:
        network.entities[p] = Entity(etype=EntityType.HARVESTER_AX, pos=p)
        tile_commodity[p] = "ax"

    occupied = frozenset(network.entities.keys())

    if k_foundries == 0 or n_ax == 0:
        connect_sources(grid, network, tile_commodity, list(grid.ti_ores), ct, "ti")
        return network, tile_commodity

    # Cluster Ax, assign Ti, place foundries
    k = min(k_foundries, n_ax)
    ax_assign, _centres = kmeans(
        list(grid.ax_ores),
        k,
        manhattan,
        pos_mean,
    )

    ax_groups: dict[int, list[int]] = {}
    for i, ci in enumerate(ax_assign):
        ax_groups.setdefault(ci, []).append(i)

    foundry_ax: list[list[int]] = []
    centres: list[Pos] = []
    for ci in range(k):
        members = ax_groups.get(ci, [])
        if not members:
            continue
        foundry_ax.append(members)
        centres.append(pos_mean([grid.ax_ores[i] for i in members]))

    actual_k = len(centres)
    if actual_k == 0:
        return build_network(0, grid)

    ti_used: set[int] = set()
    foundry_ti: list[list[int]] = []
    for fi in range(actual_k):
        need = len(foundry_ax[fi])
        cands = sorted(
            [
                (manhattan(grid.ti_ores[i], centres[fi]), i)
                for i in range(n_ti)
                if i not in ti_used
            ],
        )
        assigned = [idx for _, idx in cands[:need]]
        foundry_ti.append(assigned)
        ti_used.update(assigned)

    unpaired_ti = [i for i in range(n_ti) if i not in ti_used]

    foundry_positions: list[Pos] = []
    for fi in range(actual_k):
        ax_pts = [grid.ax_ores[i] for i in foundry_ax[fi]]
        ti_pts = [grid.ti_ores[i] for i in foundry_ti[fi]]
        fp = place_foundry(grid, ax_pts, ti_pts, occupied)
        if fp is None:
            return build_network(0, grid)
        foundry_positions.append(fp)
        network.entities[fp] = Entity(etype=EntityType.FOUNDRY, pos=fp)
        tile_commodity[fp] = "foundry"
        occupied = frozenset(network.entities.keys())

    # 1. Ti -> foundries
    for fi in range(actual_k):
        fp = foundry_positions[fi]
        ti_pts = [grid.ti_ores[i] for i in foundry_ti[fi]]
        connect_sources(grid, network, tile_commodity, ti_pts, frozenset({fp}), "ti")

    # 2. Ax -> foundries
    for fi in range(actual_k):
        fp = foundry_positions[fi]
        ax_pts = [grid.ax_ores[i] for i in foundry_ax[fi]]
        connect_sources(grid, network, tile_commodity, ax_pts, frozenset({fp}), "ax")

    # 3. RAx: foundries -> core
    connect_sources(
        grid,
        network,
        tile_commodity,
        foundry_positions,
        ct,
        "rax",
    )

    # 4. Unpaired Ti -> core
    unpaired_ti_pos = [grid.ti_ores[i] for i in unpaired_ti]
    connect_sources(grid, network, tile_commodity, unpaired_ti_pos, ct, "ti")

    return network, tile_commodity


def main() -> None:
    map_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "network.png"

    grid = load_map(map_file)
    n_ax = len(grid.ax_ores)
    print(f"Map: {grid.w}x{grid.h}, Ti={len(grid.ti_ores)}, Ax={n_ax}")

    best_network: Network | None = None
    best_commodity: dict[Pos, str] | None = None
    best_rax = -1.0
    best_cost = float("inf")

    for k in range(n_ax + 1):
        network, tile_commodity = build_network(k, grid)
        flow = compute_flow(network)
        ct = core_3x3(grid.core, grid.w, grid.h)

        rax = sum(flow.get(t, (0.0, 0.0, 0.0))[2] for t in ct)
        ti = sum(flow.get(t, (0.0, 0.0, 0.0))[0] for t in ct)
        n_conv = sum(
            1 for e in network.entities.values() if e.etype == EntityType.CONVEYOR
        )
        n_bridge = sum(
            1 for e in network.entities.values() if e.etype == EntityType.BRIDGE
        )
        n_foundry = sum(
            1 for e in network.entities.values() if e.etype == EntityType.FOUNDRY
        )
        cost = n_foundry * FOUNDRY_COST + n_conv * CONV_COST + n_bridge * BRIDGE_COST
        congestion = sum(
            1 for p, f in flow.items() if sum(f) > CAPACITY + 0.01 and p not in ct
        )

        print(
            f"k={k:2d}: RAx={rax:.2f} Ti={ti:.2f} cost={cost:8.1f} "
            f"conv={n_conv} bridge={n_bridge} congestion={congestion}",
        )

        if rax > best_rax or (rax == best_rax and cost < best_cost):
            best_rax = rax
            best_cost = cost
            best_network = network
            best_commodity = tile_commodity

    assert best_network is not None
    assert best_commodity is not None

    flow = compute_flow(best_network)
    errors = validate(best_network, best_commodity, flow, grid)
    for e in errors:
        print(e)

    draw_network(best_network, best_commodity, flow, grid, out_file)


if __name__ == "__main__":
    main()
