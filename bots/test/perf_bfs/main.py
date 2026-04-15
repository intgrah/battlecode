from cambc import Controller, Direction, EntityType


class Player:
    def __init__(self) -> None:
        self.done = False

    def run(self, ct: Controller) -> None:
        match ct.get_entity_type():
            case EntityType.CORE:
                if not self.done:
                    pos = ct.get_position()
                    target = pos.add(Direction.SOUTH)
                    if ct.can_spawn(target):
                        ct.spawn_builder(target)
                        self.done = True
            case EntityType.BUILDER_BOT:
                w = ct.get_map_width()
                h = ct.get_map_height()
                n = w * h
                INF = 1_000_000
                DIR8_DELTA = (
                    (1, 0),
                    (-1, 0),
                    (0, 1),
                    (0, -1),
                    (1, 1),
                    (1, -1),
                    (-1, 1),
                    (-1, -1),
                )

                offsets = [dy * w + dx for dx, dy in DIR8_DELTA]
                pnb = [[] for _ in range(n)]
                for cy in range(1, h - 1):
                    row = cy * w
                    for cx in range(1, w - 1):
                        i = row + cx
                        pnb[i] = [i + o for o in offsets]
                for cy in range(h):
                    row = cy * w
                    for cx in range(w):
                        if 1 <= cx < w - 1 and 1 <= cy < h - 1:
                            continue
                        i = row + cx
                        pnb[i] = [
                            ny * w + nx
                            for dx, dy in DIR8_DELTA
                            if 0 <= (nx := cx + dx) < w and 0 <= (ny := cy + dy) < h
                        ]

                dist = [INF] * n
                pos = ct.get_position()
                si = pos.y * w + pos.x

                # Simulate vision-like work: touch lots of memory
                env = [None] * n
                buildings = [None] * n
                hp = [0] * n
                max_hp = [0] * n
                pad = 3
                pw = w + 2 * pad
                ph = h + 2 * pad
                pn = pw * ph
                cost_grid = [1] * pn
                conv_cost = [5] * pn
                for p in ct.get_nearby_tiles():
                    i2 = p.y * w + p.x
                    env[i2] = ct.get_tile_env(p)
                    bid = ct.get_tile_building_id(p)
                    if bid is not None:
                        buildings[i2] = ct.get_entity_type(bid)
                        hp[i2] = ct.get_hp(bid)
                        max_hp[i2] = ct.get_max_hp(bid)
                    pi = (p.y + pad) * pw + (p.x + pad)
                    cost_grid[pi] = 1
                    conv_cost[pi] = 1

                t0 = ct.get_cpu_time_elapsed()
                for i in range(n):
                    dist[i] = INF
                dist[si] = 0
                q = [si]
                append = q.append
                for node in q:
                    d1 = dist[node] + 1
                    for ni in pnb[node]:
                        if dist[ni] == INF:
                            dist[ni] = d1
                            append(ni)
                t1 = ct.get_cpu_time_elapsed()

                visited = len(q)
                ct.resign(f"n={n} visited={visited} bfs_after_vision={t1 - t0}us")
