from cambc import Controller, EntityType, Position

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
    __slots__ = ("connected", "flow", "is_dead", "is_splitter")

    def __init__(self) -> None:
        self.connected: bool | None = None
        self.flow: float = 0.0
        self.is_splitter: bool = False
        self.is_dead: bool = False


class NetworkBelief:
    def __init__(self) -> None:
        self.tiles: dict[Position, TileInfo] = {}

    def update(self, ct: Controller, core: Position) -> None:
        my = ct.get_team()
        cx, cy = core.x, core.y
        w, h = ct.get_map_width(), ct.get_map_height()

        visible_transport: list[tuple[Position, int]] = []

        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                self.tiles.pop(t, None)
                continue
            et = ct.get_entity_type(bid)
            if et not in _TRANSPORT:
                self.tiles.pop(t, None)
                continue
            info = self.tiles.get(t)
            if info is None:
                info = TileInfo()
                self.tiles[t] = info
            info.is_splitter = et == EntityType.SPLITTER
            visible_transport.append((t, bid))

        for t, _ in visible_transport:
            info = self.tiles[t]
            seen: set[tuple[int, int]] = set()
            chain: list[Position] = []
            result: bool | None = None

            px, py = t.x, t.y
            while (px, py) not in seen:
                seen.add((px, py))
                p = Position(px, py)
                chain.append(p)
                if abs(px - cx) <= 1 and abs(py - cy) <= 1:
                    result = True
                    break
                if not ct.is_in_vision(p):
                    break
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

            if result is not None:
                for p in chain:
                    ti = self.tiles.get(p)
                    if ti is not None:
                        ti.connected = result

        for t, _ in visible_transport:
            info = self.tiles[t]
            info.flow = self._compute_flow(ct, t, my, w, h, set())
            info.is_dead = info.connected is True and info.flow == 0.0

    def _compute_flow(
        self,
        ct: Controller,
        pos: Position,
        my: int,
        w: int,
        h: int,
        seen: set[tuple[int, int]],
    ) -> float:
        if (pos.x, pos.y) in seen:
            return 0.0
        seen.add((pos.x, pos.y))

        total = 0.0
        for dx, dy in _CARDINAL_DELTAS:
            nx, ny = pos.x + dx, pos.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            adj = Position(nx, ny)
            if not ct.is_in_vision(adj):
                continue
            bid = ct.get_tile_building_id(adj)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et == EntityType.HARVESTER:
                total += 0.25
                continue
            if et not in _TRANSPORT:
                continue
            out_dx, out_dy = ct.get_direction(bid).delta()
            if nx + out_dx == pos.x and ny + out_dy == pos.y:
                upstream = self._compute_flow(ct, adj, my, w, h, seen)
                if et == EntityType.SPLITTER:
                    upstream /= 3.0
                total += upstream

        return total

    def get(self, pos: Position) -> TileInfo | None:
        return self.tiles.get(pos)

    def connected_tiles(self) -> list[Position]:
        return [p for p, info in self.tiles.items() if info.connected is True]

    def nearest_connected(
        self,
        pos: Position,
        max_flow: float = 999.0,
    ) -> Position | None:
        best: Position | None = None
        best_dist = 999999
        for p, info in self.tiles.items():
            if info.connected is not True:
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
            if not (
                info.connected is True
                and info.flow > threshold
                and not info.is_splitter
            ):
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
                    "is_dead": info.is_dead,
                    "is_splitter": info.is_splitter,
                }
                for p, info in self.tiles.items()
            },
        }
        with open(path, "a") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
