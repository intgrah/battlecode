from cambc import Controller, Direction, EntityType, Environment, Position

_TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    },
)

_CARDINAL_DELTAS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


class TileInfo:
    __slots__ = ("connected", "direction", "flow", "flow_ti", "flow_ax", "is_dead", "is_splitter")

    def __init__(self) -> None:
        self.connected: bool = False
        self.flow: float = 0.0
        self.flow_ti: float = 0.0
        self.flow_ax: float = 0.0
        self.is_splitter: bool = False
        self.is_dead: bool = False
        self.direction: Direction = Direction.CENTRE


class NetworkBelief:
    def __init__(self) -> None:
        self.tiles: dict[Position, TileInfo] = {}
        self.known_harvesters: dict[Position, bool] = {}

    def update(self, ct: Controller, core: Position) -> None:
        my = ct.get_team()
        cx, cy = core.x, core.y
        w, h = ct.get_map_width(), ct.get_map_height()

        visible_transport: list[tuple[Position, int]] = []

        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                self.tiles.pop(t, None)
                self.known_harvesters.pop(t, None)
                continue
            et = ct.get_entity_type(bid)
            if et == EntityType.HARVESTER:
                env = ct.get_tile_env(t)
                self.known_harvesters[t] = env == Environment.ORE_TITANIUM
                self.tiles.pop(t, None)
                continue
            if et not in _TRANSPORT:
                self.tiles.pop(t, None)
                continue
            info = self.tiles.get(t)
            if info is None:
                info = TileInfo()
                self.tiles[t] = info
            info.is_splitter = et == EntityType.SPLITTER
            info.direction = ct.get_direction(bid)
            visible_transport.append((t, bid))

        for t, _ in visible_transport:
            info = self.tiles[t]
            seen: set[tuple[int, int]] = set()
            chain: list[Position] = []
            result: bool = False

            px, py = t.x, t.y
            while (px, py) not in seen:
                if not (0 <= px < w and 0 <= py < h):
                    break
                seen.add((px, py))
                p = Position(px, py)
                chain.append(p)
                if abs(px - cx) <= 1 and abs(py - cy) <= 1:
                    result = True
                    break
                if ct.is_in_vision(p):
                    b = ct.get_tile_building_id(p)
                    if b is None or ct.get_team(b) != my:
                        result = False
                        break
                    bt = ct.get_entity_type(b)
                    if bt not in _TRANSPORT:
                        result = False
                        break
                    dx, dy = ct.get_direction(b).delta()
                    px, py = px + dx, py + dy
                else:
                    stored = self.tiles.get(p)
                    if stored is not None and stored.connected:
                        result = True
                        break
                    if stored is not None and stored.direction != Direction.CENTRE:
                        dx, dy = stored.direction.delta()
                        px, py = px + dx, py + dy
                    else:
                        break

            for p in chain:
                ti = self.tiles.get(p)
                if ti is not None:
                    ti.connected = result

        for t, _ in visible_transport:
            info = self.tiles[t]
            total, ti_f, ax_f = self._compute_flow(ct, t, my, w, h, set())
            info.flow = total
            info.flow_ti = ti_f
            info.flow_ax = ax_f
            info.is_dead = info.connected and info.flow == 0.0

    def _harvester_outputs(
        self,
        ct: Controller,
        hpos: Position,
        my: int,
        w: int,
        h: int,
    ) -> int:
        count = 0
        for dx, dy in _CARDINAL_DELTAS:
            nx, ny = hpos.x + dx, hpos.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            adj = Position(nx, ny)
            if ct.is_in_vision(adj):
                bid = ct.get_tile_building_id(adj)
                if bid is not None and ct.get_team(bid) == my:
                    count += 1
            elif adj in self.tiles:
                count += 1
        return max(count, 1)

    def _compute_flow(
        self,
        ct: Controller,
        pos: Position,
        my: int,
        w: int,
        h: int,
        seen: set[tuple[int, int]],
    ) -> tuple[float, float, float]:
        if (pos.x, pos.y) in seen:
            return 0.0, 0.0, 0.0
        seen.add((pos.x, pos.y))

        total = 0.0
        ti_total = 0.0
        ax_total = 0.0
        for dx, dy in _CARDINAL_DELTAS:
            nx, ny = pos.x + dx, pos.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            adj = Position(nx, ny)
            if adj in self.known_harvesters:
                outputs = self._harvester_outputs(ct, adj, my, w, h)
                contrib = 0.25 / outputs
                total += contrib
                if self.known_harvesters[adj]:
                    ti_total += contrib
                else:
                    ax_total += contrib
                continue
            if ct.is_in_vision(adj):
                bid = ct.get_tile_building_id(adj)
                if bid is None or ct.get_team(bid) != my:
                    continue
                et = ct.get_entity_type(bid)
                if et == EntityType.HARVESTER:
                    outputs = self._harvester_outputs(ct, adj, my, w, h)
                    contrib = 0.25 / outputs
                    total += contrib
                    env = ct.get_tile_env(adj)
                    if env == Environment.ORE_TITANIUM:
                        ti_total += contrib
                    else:
                        ax_total += contrib
                    continue
                if et not in _TRANSPORT:
                    continue
                out_dx, out_dy = ct.get_direction(bid).delta()
                if nx + out_dx == pos.x and ny + out_dy == pos.y:
                    up_t, up_ti, up_ax = self._compute_flow(ct, adj, my, w, h, seen)
                    if et == EntityType.SPLITTER:
                        up_t /= 3.0
                        up_ti /= 3.0
                        up_ax /= 3.0
                    total += up_t
                    ti_total += up_ti
                    ax_total += up_ax
            else:
                stored = self.tiles.get(adj)
                if stored is not None:
                    out_dx, out_dy = stored.direction.delta()
                    if nx + out_dx == pos.x and ny + out_dy == pos.y:
                        up_t, up_ti, up_ax = self._compute_flow(ct, adj, my, w, h, seen)
                        if stored.is_splitter:
                            up_t /= 3.0
                            up_ti /= 3.0
                            up_ax /= 3.0
                        total += up_t
                        ti_total += up_ti
                        ax_total += up_ax

        return total, ti_total, ax_total

    def get(self, pos: Position) -> TileInfo | None:
        return self.tiles.get(pos)

    def connected_tiles(self) -> list[Position]:
        return [p for p, info in self.tiles.items() if info.connected]

    def nearest_connected(
        self,
        pos: Position,
        max_flow: float = 999.0,
    ) -> Position | None:
        best: Position | None = None
        best_dist = 999999
        for p, info in self.tiles.items():
            if not info.connected:
                continue
            if info.flow > max_flow:
                continue
            d = pos.distance_squared(p)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def find_break(self, ct: Controller, core: Position) -> Position | None:
        my = ct.get_team()
        cx, cy = core.x, core.y
        w, h = ct.get_map_width(), ct.get_map_height()
        best: Position | None = None
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (
                EntityType.CONVEYOR,
                EntityType.ARMOURED_CONVEYOR,
                EntityType.SPLITTER,
            ):
                continue
            dx, dy = ct.get_direction(bid).delta()
            out = Position(t.x + dx, t.y + dy)
            if not (0 <= out.x < w and 0 <= out.y < h):
                continue
            if not ct.is_in_vision(out):
                continue
            out_bid = ct.get_tile_building_id(out)
            if out_bid is not None and ct.get_entity_type(out_bid) != EntityType.MARKER:
                continue
            if abs(out.x - cx) <= 1 and abs(out.y - cy) <= 1:
                continue
            info = self.tiles.get(t)
            flow = info.flow if info else 0.0
            if flow > 0.0:
                return out
            if best is None:
                best = out
        return best

    def most_congested(self, core: Position, threshold: float = 1.0) -> Position | None:
        best: Position | None = None
        best_dist = -1
        for p, info in self.tiles.items():
            if not (info.connected and info.flow > threshold and not info.is_splitter):
                continue
            d = p.distance_squared(core)
            if d > best_dist:
                best_dist = d
                best = p
        return best

    def dead_conveyor(self) -> Position | None:
        for p, info in self.tiles.items():
            if info.is_dead:
                return p
        return None

    def foundry_candidate(
        self, ct: Controller, min_flow: float = 0.25
    ) -> tuple[Position, Position, Position] | None:
        ti_tiles = []
        ax_tiles = []
        for p, info in self.tiles.items():
            if not info.connected:
                continue
            if info.flow_ti >= min_flow:
                ti_tiles.append(p)
            if info.flow_ax >= min_flow:
                ax_tiles.append(p)
        best: tuple[Position, Position, Position] | None = None
        best_dist = 999999
        for tp in ti_tiles:
            for ap in ax_tiles:
                d = tp.distance_squared(ap)
                if d >= best_dist or d > 9:
                    continue
                for dx, dy in _CARDINAL_DELTAS:
                    fp = Position(tp.x + dx, tp.y + dy)
                    if not ct.is_in_vision(fp):
                        continue
                    bid = ct.get_tile_building_id(fp)
                    if bid is None and fp.distance_squared(ap) <= 4:
                        best = (tp, ap, fp)
                        best_dist = d
        return best

    def defense_candidate(
        self, enemy_core: Position, min_flow: float = 0.25
    ) -> Position | None:
        best: Position | None = None
        best_score = -1.0
        for p, info in self.tiles.items():
            if not info.connected or info.flow < min_flow:
                continue
            enemy_dist = max(p.distance_squared(enemy_core), 1)
            score = info.flow / enemy_dist
            if score > best_score:
                best_score = score
                best = p
        return best

    def dump(self, path: str, turn: int, bot_id: int, bot_pos: tuple[int, int]) -> None:
        import json

        entry = {
            "turn": turn,
            "bot_id": bot_id,
            "bot_pos": list(bot_pos),
            "tiles": {
                f"{p.x},{p.y}": {
                    "connected": info.connected,
                    "flow": round(info.flow, 3),
                    "flow_ti": round(info.flow_ti, 3),
                    "flow_ax": round(info.flow_ax, 3),
                    "is_dead": info.is_dead,
                    "is_splitter": info.is_splitter,
                }
                for p, info in self.tiles.items()
            },
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
