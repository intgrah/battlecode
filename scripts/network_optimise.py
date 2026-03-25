import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import minimum_spanning_tree

from proto import cambc_pb2

type Pos = tuple[int, int]
type Edge = tuple[Pos, Pos]
type FlowMap = dict[Edge, float]
type SourceFlowMap = dict[Pos, float]
type FoundryData = tuple[list[Edge], FlowMap, SourceFlowMap]


@dataclass(frozen=True)
class Network:
    main_edges: list[Edge]
    main_flows: FlowMap
    main_sources: SourceFlowMap
    main_commodity: str
    foundry_ax: list[FoundryData]
    foundry_ti: list[FoundryData]
    foundry_positions: list[Pos]
    rax: float
    ti_del: float
    cost: float
    max_flow: float
    over_cap: int
    n_foundries: int


CAPACITY = 1.0
FOUNDRY_COST = 120.0
CONV_COST_PER_TILE = 3.0


def dist(a: Pos, b: Pos) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def kmeans(
    points: list[Pos],
    k: int,
) -> tuple[list[int], list[Pos]]:
    if k >= len(points):
        return list(range(len(points))), list(points)
    rng = np.random.RandomState(42)
    indices = rng.choice(len(points), k, replace=False)
    centers = [points[i] for i in indices]
    assignments = [0] * len(points)
    for _ in range(50):
        for i, p in enumerate(points):
            assignments[i] = min(range(k), key=lambda c: dist(p, centers[c]))
        for ci in range(k):
            members = [points[i] for i in range(len(points)) if assignments[i] == ci]
            if members:
                centers[ci] = (
                    round(sum(m[0] for m in members) / len(members)),
                    round(sum(m[1] for m in members) / len(members)),
                )
    return assignments, centers


def steiner_tree(
    sources: list[Pos],
    root: Pos,
    occupied: set[Pos],
    source_flow: float = 0.25,
) -> tuple[list[Edge], set[Pos]]:
    if not sources:
        return [], occupied

    max_per_branch = int(CAPACITY / source_flow)

    if len(sources) <= max_per_branch:
        points = [*sources, root]
        n = len(points)
        d = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                d[i][j] = dist(points[i], points[j])
        mst = minimum_spanning_tree(csr_matrix(d))
        edges: list[Edge] = []
        used: set[Pos] = set()
        cx = mst.tocoo()
        for i, j, _ in zip(cx.row, cx.col, cx.data, strict=True):
            edges.append((points[i], points[j]))
            used.add(points[i])
            used.add(points[j])
        return edges, occupied | used

    sorted_sources = sorted(sources, key=lambda s: dist(s, root))
    chunks = [
        sorted_sources[i : i + max_per_branch]
        for i in range(0, len(sorted_sources), max_per_branch)
    ]

    all_edges: list[Edge] = []
    all_used: set[Pos] = set()
    for chunk in chunks:
        edges, occupied = steiner_tree(chunk, root, occupied, source_flow)
        all_edges.extend(edges)
        all_used.update(t for e in edges for t in e)

    return all_edges, occupied | all_used


def compute_edge_flows(
    edges: list[Edge],
    source_flows: SourceFlowMap,
    root: Pos,
) -> FlowMap:
    adj: dict[Pos, list[Pos]] = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)
        adj[v].append(u)

    parent: dict[Pos, Pos | None] = {root: None}
    children: dict[Pos, list[Pos]] = defaultdict(list)
    visited = {root}
    queue = [root]
    order = [root]
    while queue:
        n = queue.pop(0)
        for nb in adj[n]:
            if nb not in visited:
                visited.add(nb)
                parent[nb] = n
                children[n].append(nb)
                queue.append(nb)
                order.append(nb)

    subtree: dict[Pos, float] = {}
    for n in reversed(order):
        child_flow = sum(subtree.get(c, 0) for c in children.get(n, []))
        own = source_flows.get(n, 0)
        subtree[n] = child_flow + own

    flows: FlowMap = {}
    for n, p in parent.items():
        if p is None:
            continue
        edge_key = (n, p)
        rev_key = (p, n)
        if edge_key in [(u, v) for u, v in edges]:
            flows[edge_key] = subtree[n]
        elif rev_key in [(u, v) for u, v in edges]:
            flows[rev_key] = subtree[n]
        else:
            flows[edge_key] = subtree[n]

    return flows


def build_network(
    k_foundries: int,
    ti_ores: list[Pos],
    ax_ores: list[Pos],
    core: Pos,
) -> Network:
    n_ti = len(ti_ores)
    n_ax = len(ax_ores)

    if k_foundries == 0:
        occupied: set[Pos] = {core}
        edges, occupied = steiner_tree(ti_ores, core, occupied)
        source_flows = dict.fromkeys(ti_ores, 0.25)
        flows = compute_edge_flows(edges, source_flows, core)
        max_f = max(flows.values()) if flows else 0
        over_cap = sum(1 for f in flows.values() if f > CAPACITY + 0.01)
        total_length = sum(dist(u, v) for u, v in edges)
        cost = total_length * CONV_COST_PER_TILE
        return Network(
            main_edges=edges,
            main_flows=flows,
            main_sources=source_flows,
            main_commodity="ti",
            foundry_ax=[],
            foundry_ti=[],
            foundry_positions=[],
            rax=0.0,
            ti_del=n_ti * 0.25,
            cost=cost,
            max_flow=max_f,
            over_cap=over_cap,
            n_foundries=0,
        )

    k = min(k_foundries, n_ax)
    ax_assignments, ax_centers = kmeans(ax_ores, k)

    ax_per_foundry: dict[int, list[int]] = defaultdict(list)
    for i, ci in enumerate(ax_assignments):
        ax_per_foundry[ci].append(i)

    foundry_positions: list[Pos] = []
    foundry_ax_indices: list[list[int]] = []
    for ci in range(k):
        members = ax_per_foundry.get(ci, [])
        if not members:
            continue
        foundry_positions.append(ax_centers[ci])
        foundry_ax_indices.append(members)

    actual_k = len(foundry_positions)
    if actual_k == 0:
        return build_network(0, ti_ores, ax_ores, core)

    ti_assigned: set[int] = set()
    foundry_ti_indices: list[list[int]] = []
    for fi in range(actual_k):
        needed = len(foundry_ax_indices[fi])
        fp = foundry_positions[fi]
        candidates = sorted(
            [(dist(ti_ores[i], fp), i) for i in range(n_ti) if i not in ti_assigned],
        )
        assigned = [idx for _, idx in candidates[:needed]]
        foundry_ti_indices.append(assigned)
        ti_assigned.update(assigned)

    unpaired_ti = [i for i in range(n_ti) if i not in ti_assigned]

    occupied: set[Pos] = set()
    occupied.add(core)
    for p in ti_ores:
        occupied.add(p)
    for p in ax_ores:
        occupied.add(p)
    for p in foundry_positions:
        occupied.add(p)

    unpaired_ti_positions = [ti_ores[i] for i in unpaired_ti]

    ti_to_core_edges, occupied = steiner_tree(unpaired_ti_positions, core, occupied)
    ti_source_flows_main = dict.fromkeys(unpaired_ti_positions, 0.25)
    ti_to_core_flows = compute_edge_flows(ti_to_core_edges, ti_source_flows_main, core)

    rax_to_core_sources = list(foundry_positions)
    rax_source_flows: SourceFlowMap = {}
    for fi in range(actual_k):
        fp = foundry_positions[fi]
        n_matched = min(len(foundry_ax_indices[fi]), len(foundry_ti_indices[fi]))
        rax_source_flows[fp] = n_matched * 0.25

    rax_to_core_edges, occupied = steiner_tree(rax_to_core_sources, core, occupied)
    rax_to_core_flows = compute_edge_flows(rax_to_core_edges, rax_source_flows, core)

    main_edges = ti_to_core_edges + rax_to_core_edges
    main_flows = {**ti_to_core_flows, **rax_to_core_flows}
    main_source_flows = {**ti_source_flows_main, **rax_source_flows}

    foundry_ax_data: list[FoundryData] = []
    foundry_ti_data: list[FoundryData] = []
    for fi in range(actual_k):
        fp = foundry_positions[fi]
        ax_positions = [ax_ores[i] for i in foundry_ax_indices[fi]]
        ax_edges, occupied = steiner_tree(ax_positions, fp, occupied)
        ax_source_flows = dict.fromkeys(ax_positions, 0.25)
        ax_flows = compute_edge_flows(ax_edges, ax_source_flows, fp)
        foundry_ax_data.append((ax_edges, ax_flows, ax_source_flows))

        ti_positions = [ti_ores[i] for i in foundry_ti_indices[fi]]
        ti_edges, occupied = steiner_tree(ti_positions, fp, occupied)
        ti_source_flows = dict.fromkeys(ti_positions, 0.25)
        ti_flows = compute_edge_flows(ti_edges, ti_source_flows, fp)
        foundry_ti_data.append((ti_edges, ti_flows, ti_source_flows))

    all_flows = list(main_flows.values())
    for _ax_e, ax_f, _ in foundry_ax_data:
        all_flows.extend(ax_f.values())
    for _ti_e, ti_f, _ in foundry_ti_data:
        all_flows.extend(ti_f.values())

    max_f = max(all_flows) if all_flows else 0
    over_cap = sum(1 for f in all_flows if f > CAPACITY + 0.01)

    total_length = sum(dist(u, v) for u, v in main_edges)
    for ax_e, _, _ in foundry_ax_data:
        total_length += sum(dist(u, v) for u, v in ax_e)
    for ti_e, _, _ in foundry_ti_data:
        total_length += sum(dist(u, v) for u, v in ti_e)

    cost = actual_k * FOUNDRY_COST + total_length * CONV_COST_PER_TILE
    rax_del = (
        sum(
            min(len(foundry_ax_indices[fi]), len(foundry_ti_indices[fi]))
            for fi in range(actual_k)
        )
        * 0.25
    )
    ti_del = len(unpaired_ti) * 0.25

    return Network(
        main_edges=main_edges,
        main_flows=main_flows,
        main_sources=main_source_flows,
        main_commodity="mixed",
        foundry_ax=foundry_ax_data,
        foundry_ti=foundry_ti_data,
        foundry_positions=foundry_positions,
        rax=rax_del,
        ti_del=ti_del,
        cost=cost,
        max_flow=max_f,
        over_cap=over_cap,
        n_foundries=actual_k,
    )


def draw_network(
    best: Network,
    ti_ores: list[Pos],
    ax_ores: list[Pos],
    walls: set[Pos],
    core: Pos,
    w: int,
    h: int,
    output_file: str,
) -> None:
    scale = 40
    pad = 60
    img_w = w * scale + pad * 2
    img_h = h * scale + pad * 2
    img = Image.new("RGB", (img_w, img_h), (30, 25, 25))
    draw = ImageDraw.Draw(img)

    def tx(x: int, y: int) -> tuple[int, int]:
        return x * scale + pad, y * scale + pad

    for wx, wy in walls:
        px, py = tx(wx, wy)
        draw.rectangle(
            [px - scale // 3, py - scale // 3, px + scale // 3, py + scale // 3],
            fill=(60, 45, 40),
        )

    colors = {"ti": (80, 140, 255), "ax": (255, 160, 40), "rax": (200, 130, 255)}

    def draw_edges(
        edges: list[Edge],
        flows: FlowMap,
        commodity: str,
    ) -> None:
        color = colors[commodity]
        for u, v in edges:
            f = flows.get((u, v), flows.get((v, u), 0))
            width = max(1, min(6, int(f * 8)))
            a = tx(u[0], u[1])
            b = tx(v[0], v[1])
            draw.line([a, b], fill=color, width=width)
            mx = (a[0] + b[0]) // 2
            my = (a[1] + b[1]) // 2
            fc = (255, 80, 80) if f > CAPACITY else (200, 200, 200)
            draw.text((mx + 2, my - 8), f"{f:.2f}", fill=fc)

    fp_set = set(best.foundry_positions)
    for u, v in best.main_edges:
        f = best.main_flows.get((u, v), best.main_flows.get((v, u), 0))
        is_rax = u in fp_set or v in fp_set
        commodity = "rax" if is_rax else "ti"
        color = colors[commodity]
        width = max(1, min(6, int(f * 8)))
        a = tx(u[0], u[1])
        b = tx(v[0], v[1])
        draw.line([a, b], fill=color, width=width)
        mx = (a[0] + b[0]) // 2
        my = (a[1] + b[1]) // 2
        fc = (255, 80, 80) if f > CAPACITY else (200, 200, 200)
        draw.text((mx + 2, my - 8), f"{f:.2f}", fill=fc)

    for ax_edges, ax_flows, _ in best.foundry_ax:
        draw_edges(ax_edges, ax_flows, "ax")

    for ti_edges, ti_flows, _ in best.foundry_ti:
        draw_edges(ti_edges, ti_flows, "ti")

    for x, y in ti_ores:
        px, py = tx(x, y)
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colors["ti"])

    for x, y in ax_ores:
        px, py = tx(x, y)
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=colors["ax"])

    for fp in best.foundry_positions:
        px, py = tx(fp[0], fp[1])
        draw.rectangle([px - 7, py - 7, px + 7, py + 7], fill=(200, 50, 200))

    cpx, cpy = tx(core[0], core[1])
    draw.ellipse([cpx - 10, cpy - 10, cpx + 10, cpy + 10], fill=(50, 200, 80))

    draw.text(
        (pad, 5),
        f"Best: k={best.n_foundries} RAx={best.rax:.2f} Ti={best.ti_del:.2f} cost={best.cost:.0f}",
        fill=(255, 255, 255),
    )
    draw.text(
        (pad, img_h - 25),
        "Blue=Ti  Orange=Ax  Purple=RAx  Square=Foundry  Green=Core",
        fill=(180, 180, 180),
    )

    img.save(output_file)
    print(f"Saved to {output_file}")


def main() -> None:
    map_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "network.png"

    with Path(map_file).open("rb") as f:
        mm = cambc_pb2.Map()
        mm.ParseFromString(f.read())

    w, h = mm.width, mm.height

    ti_ores: list[Pos] = []
    ax_ores: list[Pos] = []
    walls: set[Pos] = set()
    for y, row in enumerate(mm.rows):
        for x, tile in enumerate(row.tiles):
            if tile == 2:
                ti_ores.append((x, y))
            elif tile == 3:
                ax_ores.append((x, y))
            elif tile == 1:
                walls.add((x, y))

    core: Pos = next((c.position.x, c.position.y) for c in mm.cores if c.team == 0)
    n_ax = len(ax_ores)
    n_ti = len(ti_ores)

    print(f"Map: {w}x{h}, Ti={n_ti}, Ax={n_ax}")

    best: Network | None = None
    for k in range(n_ax + 1):
        result = build_network(k, ti_ores, ax_ores, core)
        print(
            f"k={k:2d}: foundries={result.n_foundries:2d} RAx={result.rax:.2f} Ti={result.ti_del:.2f} "
            f"cost={result.cost:8.1f} max_flow={result.max_flow:.2f} over_cap={result.over_cap}",
        )
        if result.over_cap > 0:
            continue
        if (
            best is None
            or result.rax > best.rax
            or (result.rax == best.rax and result.cost < best.cost)
        ):
            best = result

    if best is None:
        best = build_network(0, ti_ores, ax_ores, core)

    print(
        f"\nBest: foundries={best.n_foundries} RAx={best.rax:.2f} "
        f"Ti={best.ti_del:.2f} cost={best.cost:.0f}",
    )

    draw_network(best, ti_ores, ax_ores, walls, core, w, h, output_file)


if __name__ == "__main__":
    main()
