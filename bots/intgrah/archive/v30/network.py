from cambc import Controller, EntityType, Position, Team

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
    __slots__ = ("connected", "has_resource", "upstream_harvesters")

    def __init__(self) -> None:
        self.connected: bool | None = None
        self.upstream_harvesters: int = 0
        self.has_resource: bool = False


class NetworkBelief:
    def __init__(self) -> None:
        self.tiles: dict[Position, TileInfo] = {}

    def update(self, ct: Controller, core: Position) -> None:
        my = ct.get_team()
        cx, cy = core.x, core.y

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
            info.has_resource = ct.get_stored_resource(bid) is not None
            visible_transport.append((t, bid))

        for t, _ in visible_transport:
            info = self.tiles[t]
            x, y = t.x, t.y
            seen: set[tuple[int, int]] = set()
            chain: list[Position] = []
            result: bool | None = None

            px, py = x, y
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
            self._count_upstream(ct, t, my, set(), count_ref := [0])
            info.upstream_harvesters = count_ref[0]

    def _count_upstream(
        self,
        ct: Controller,
        pos: Position,
        my: Team,
        seen: set[tuple[int, int]],
        count_ref: list[int],
    ) -> None:
        if (pos.x, pos.y) in seen:
            return
        seen.add((pos.x, pos.y))

        w, h = ct.get_map_width(), ct.get_map_height()
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
                count_ref[0] += 1
                continue
            if et not in _TRANSPORT:
                continue
            out_dx, out_dy = ct.get_direction(bid).delta()
            if nx + out_dx == pos.x and ny + out_dy == pos.y:
                self._count_upstream(ct, adj, my, seen, count_ref)

    def get(self, pos: Position) -> TileInfo | None:
        return self.tiles.get(pos)

    def connected_tiles(self) -> list[Position]:
        return [p for p, info in self.tiles.items() if info.connected is True]

    def nearest_connected(
        self,
        pos: Position,
        max_upstream: int = 999,
    ) -> Position | None:
        best: Position | None = None
        best_dist = 999999
        for p, info in self.tiles.items():
            if info.connected is not True:
                continue
            if info.upstream_harvesters > max_upstream:
                continue
            d = pos.distance_squared(p)
            if d < best_dist:
                best_dist = d
                best = p
        return best

    def find_break(self, ct: Controller, core: Position) -> Position | None:
        my = ct.get_team()
        cx, cy = core.x, core.y
        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None or ct.get_team(bid) != my:
                continue
            et = ct.get_entity_type(bid)
            if et not in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                continue
            dx, dy = ct.get_direction(bid).delta()
            out = Position(t.x + dx, t.y + dy)
            if not ct.is_in_vision(out):
                continue
            if ct.get_tile_building_id(out) is not None:
                continue
            if abs(out.x - cx) <= 1 and abs(out.y - cy) <= 1:
                continue
            return out
        return None

    def congested_tiles(self, threshold: int = 4) -> list[Position]:
        return [
            p
            for p, info in self.tiles.items()
            if info.connected is True and info.upstream_harvesters > threshold
        ]
