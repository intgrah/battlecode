import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import linear_sum_assignment

from proto.cambc_pb2 import Replay

CAPACITY = 1.0

type Pt = tuple[float, float]


def dist(a: Pt, b: Pt) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_on_segment(p: Pt, a: Pt, b: Pt) -> tuple[Pt, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-8:
        return a, 0.0
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len_sq))
    proj = (a[0] + t * dx, a[1] + t * dy)
    return proj, dist(p, proj)


class Tree:
    def __init__(self, root: Pt) -> None:
        self.nodes: dict[int, Pt] = {0: root}
        self.edges: list[tuple[int, int]] = []
        self.edge_flow: list[float] = []
        self.edge_commodity: list[str] = []
        self.adj: dict[int, list[int]] = {0: []}
        self.next_id = 1

    def add_node(self, pos: Pt) -> int:
        nid = self.next_id
        self.next_id += 1
        self.nodes[nid] = pos
        self.adj[nid] = []
        return nid

    def add_edge(self, u: int, v: int, flow: float, commodity: str) -> int:
        eidx = len(self.edges)
        self.edges.append((u, v))
        self.edge_flow.append(flow)
        self.edge_commodity.append(commodity)
        self.adj[u].append(eidx)
        self.adj[v].append(eidx)
        return eidx

    def path_to_root(self, node: int) -> list[int] | None:
        visited: set[int] = set()
        queue = [(node, [])]
        while queue:
            n, path = queue.pop(0)
            if n == 0:
                return path
            if n in visited:
                continue
            visited.add(n)
            for eidx in self.adj[n]:
                u, v = self.edges[eidx]
                nb = v if u == n else u
                if nb not in visited:
                    queue.append((nb, [*path, eidx]))
        return None

    def can_add_flow(self, path: list[int], amount: float) -> bool:
        return all(self.edge_flow[eidx] + amount <= CAPACITY + 0.01 for eidx in path)

    def increase_flow(self, path: list[int], amount: float) -> None:
        for eidx in path:
            self.edge_flow[eidx] += amount

    def find_nearest_point(self, pos: Pt) -> tuple[Pt, int | None, int, float]:
        best_dist = 1e18
        best_point: Pt | None = None
        best_edge: int | None = None
        best_t = 0
        for eidx, (u, v) in enumerate(self.edges):
            if u == -1:
                continue
            a = self.nodes[u]
            b = self.nodes[v]
            proj, d = point_on_segment(pos, a, b)
            if d < best_dist:
                best_dist = d
                best_point = proj
                best_edge = eidx
                best_t = 0
        for nid, npos in self.nodes.items():
            d = dist(pos, npos)
            if d < best_dist:
                best_dist = d
                best_point = npos
                best_edge = None
                best_t = nid
        assert best_point is not None
        return best_point, best_edge, best_t, best_dist

    def insert_on_edge(self, eidx: int, pos: Pt) -> int:
        u, v = self.edges[eidx]
        old_flow = self.edge_flow[eidx]
        old_commodity = self.edge_commodity[eidx]
        new_node = self.add_node(pos)
        self.adj[u].remove(eidx)
        self.adj[v].remove(eidx)
        self.edges[eidx] = (-1, -1)
        self.edge_flow[eidx] = 0
        self.add_edge(u, new_node, old_flow, old_commodity)
        self.add_edge(new_node, v, old_flow, old_commodity)
        return new_node

    def connect_source(self, pos: Pt, flow: float, commodity: str) -> bool:
        if not self.edges:
            src = self.add_node(pos)
            self.add_edge(src, 0, flow, commodity)
            return True

        best_point, best_edge, best_t, _best_dist = self.find_nearest_point(pos)

        if best_edge is not None:
            attach_node = self.insert_on_edge(best_edge, best_point)
        else:
            attach_node = best_t

        src = self.add_node(pos)
        self.add_edge(src, attach_node, flow, commodity)

        path = self.path_to_root(attach_node)
        if path is None:
            path = []

        if not self.can_add_flow(path, flow):
            return False

        self.increase_flow(path, flow)
        return True


def compute_metrics(t: Tree) -> tuple[float, float, int]:
    total_length = 0.0
    max_flow = 0.0
    over_cap = 0
    for eidx, (u, v) in enumerate(t.edges):
        if u == -1:
            continue
        a = t.nodes[u]
        b = t.nodes[v]
        length = dist(a, b)
        total_length += length
        flow = t.edge_flow[eidx]
        max_flow = max(max_flow, flow)
        if flow > 1.0:
            over_cap += 1
    return total_length, max_flow, over_cap


def main() -> None:
    replay_file = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "network.png"

    with Path(replay_file).open("rb") as f:
        replay = Replay()
        replay.ParseFromString(f.read())

    mm = replay.map
    w, h = mm.width, mm.height

    ti_ores: list[Pt] = []
    ax_ores: list[Pt] = []
    walls: set[tuple[int, int]] = set()
    for y, row in enumerate(mm.rows):
        for x, tile in enumerate(row.tiles):
            if tile == 2:
                ti_ores.append((float(x), float(y)))
            elif tile == 3:
                ax_ores.append((float(x), float(y)))
            elif tile == 1:
                walls.add((x, y))

    core = (11.0, 24.0)
    n_ax = len(ax_ores)
    n_ti = len(ti_ores)

    cost_matrix = np.zeros((n_ax, n_ti))
    for i, (ax, ay) in enumerate(ax_ores):
        for j, (tx, ty) in enumerate(ti_ores):
            cost_matrix[i][j] = math.hypot(ax - tx, ay - ty)
    ax_matched, ti_matched = linear_sum_assignment(cost_matrix)
    paired_ti_set = set(ti_matched)

    foundries: list[Pt] = []
    for ai, ti in zip(ax_matched, ti_matched, strict=False):
        ax_p = np.array(ax_ores[ai])
        ti_p = np.array(ti_ores[ti])
        core_p = np.array(core)
        fp = (ax_p + ti_p + core_p) / 3
        for _ in range(200):
            grad = np.zeros(2)
            for target in [ax_p, ti_p, core_p]:
                d = fp - target
                d_norm = np.linalg.norm(d)
                if d_norm > 0.01:
                    grad += d / d_norm
            fp -= 0.1 * grad
        foundries.append((float(fp[0]), float(fp[1])))

    sources = [
        (ti_ores[ui], 0.25, "ti") for ui in range(n_ti) if ui not in paired_ti_set
    ]

    for fi, (_ai, ti) in enumerate(zip(ax_matched, ti_matched, strict=False)):
        sources.append((ti_ores[ti], 0.25, "ti_paired"))
        sources.append((ax_ores[_ai], 0.25, "ax"))
        sources.append((foundries[fi], 0.25, "rax"))

    sorted(sources, key=lambda s: dist(s[0], core))

    paired_sources = []
    for fi, (ai, ti) in enumerate(zip(ax_matched, ti_matched, strict=False)):
        paired_sources.append((fi, ti_ores[ti], ax_ores[ai], foundries[fi]))

    tree_core = Tree(core)

    for ui in range(n_ti):
        if ui not in paired_ti_set:
            tree_core.connect_source(ti_ores[ui], 0.25, "ti")

    for fi, (_ai, _ti) in enumerate(zip(ax_matched, ti_matched, strict=False)):
        tree_core.connect_source(foundries[fi], 0.25, "rax")

    tree_foundries = []
    for fi, (ai, ti) in enumerate(zip(ax_matched, ti_matched, strict=False)):
        ft = Tree(foundries[fi])
        ft.connect_source(ti_ores[ti], 0.25, "ti")
        ft.connect_source(ax_ores[ai], 0.25, "ax")
        tree_foundries.append(ft)

    scale = 20
    pad = 50
    img_w = w * scale + pad * 2
    img_h = h * scale + pad * 2
    img = Image.new("RGB", (img_w, img_h), (30, 25, 25))
    draw = ImageDraw.Draw(img)

    def tx(x: float, y: float) -> tuple[int, int]:
        return int(x * scale + pad), int(y * scale + pad)

    for wx, wy in walls:
        px, py = tx(wx, wy)
        draw.rectangle(
            [px - scale // 3, py - scale // 3, px + scale // 3, py + scale // 3],
            fill=(60, 45, 40),
        )

    colors = {
        "ti": (80, 140, 255),
        "ti_paired": (80, 140, 255),
        "ax": (255, 160, 40),
        "rax": (200, 130, 255),
    }

    def draw_tree(t: Tree) -> None:
        for eidx, (u, v) in enumerate(t.edges):
            if u == -1:
                continue
            a = t.nodes[u]
            b = t.nodes[v]
            commodity = t.edge_commodity[eidx]
            flow = t.edge_flow[eidx]
            color = colors.get(commodity, (180, 180, 180))
            width = max(1, min(6, int(flow * 10)))
            pa = tx(a[0], a[1])
            pb = tx(b[0], b[1])
            draw.line([pa, pb], fill=color, width=width)

            mx = (pa[0] + pb[0]) // 2
            my = (pa[1] + pb[1]) // 2
            flow_color = (255, 80, 80) if flow > 1.0 else (200, 200, 200)
            draw.text((mx + 2, my - 8), f"{flow:.2f}", fill=flow_color)

    draw_tree(tree_core)
    for ft in tree_foundries:
        draw_tree(ft)

    for x, y in ti_ores:
        px, py = tx(x, y)
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(80, 140, 255))

    for x, y in ax_ores:
        px, py = tx(x, y)
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(255, 160, 40))

    for fx, fy in foundries:
        px, py = tx(fx, fy)
        draw.rectangle([px - 6, py - 6, px + 6, py + 6], fill=(200, 50, 200))

    cpx, cpy = tx(core[0], core[1])
    draw.ellipse([cpx - 10, cpy - 10, cpx + 10, cpy + 10], fill=(50, 200, 80))

    draw.text(
        (pad, img_h - 25),
        "Blue=Ti  Orange=Ax  Purple=RAx  Square=Foundry  Green=Core",
        fill=(180, 180, 180),
    )

    rax_delivered = len(foundries) * 0.25
    n_unpaired_ti = n_ti - len(paired_ti_set)
    ti_delivered = n_unpaired_ti * 0.25

    total_cost = 0.0
    total_max_flow = 0.0
    total_over_cap = 0

    for t in [tree_core, *list(tree_foundries)]:
        length, mf, oc = compute_metrics(t)
        total_cost += length
        total_max_flow = max(total_max_flow, mf)
        total_over_cap += oc

    print("--- Network Metrics ---")
    print(f"RAx delivered:  {rax_delivered:.2f} ({len(foundries)} foundries)")
    print(f"Ti delivered:   {ti_delivered:.2f} ({n_unpaired_ti} unpaired Ti)")
    print(f"Total flow:     {rax_delivered + ti_delivered:.2f}")
    print(f"Network cost:   {total_cost:.1f} (total edge length)")
    print(f"Max edge flow:  {total_max_flow:.2f}")
    print(f"Over capacity:  {total_over_cap} edges")
    print(
        f"Efficiency:     {(rax_delivered + ti_delivered) / max(total_cost, 0.01) * 100:.2f} flow/cost",
    )

    img.save(output_file)
    print(f"Saved to {output_file}")


if __name__ == "__main__":
    main()
