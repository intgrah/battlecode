"""Sentinel fire control. Ported from v2."""

from collections import deque

from cambc import Controller, EntityType, Position
from unit import Unit

_IDLE_LIMIT = 25
_DIR4_DELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))
_TRANSPORT = frozenset(
    {
        EntityType.CONVEYOR,
        EntityType.ARMOURED_CONVEYOR,
        EntityType.SPLITTER,
        EntityType.BRIDGE,
    }
)


def _find_protected_buildings(ct: Controller, my_team: int) -> set[int]:
    """BFS backward from friendly turrets to find buildings feeding them."""
    protected: set[int] = set()
    queue: deque[int] = deque()
    w = ct.get_map_width()
    h = ct.get_map_height()

    for bid in ct.get_nearby_buildings():
        if ct.get_team(bid) != my_team:
            continue
        etype = ct.get_entity_type(bid)
        if etype in (EntityType.GUNNER, EntityType.SENTINEL, EntityType.BREACH):
            protected.add(bid)
            queue.append(bid)

    visited_tiles: set[tuple[int, int]] = set()
    while queue:
        bid = queue.popleft()
        bp = ct.get_position(bid)
        if (bp.x, bp.y) in visited_tiles:
            continue
        visited_tiles.add((bp.x, bp.y))

        for dx, dy in _DIR4_DELTA:
            nx, ny = bp.x + dx, bp.y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            npos = Position(nx, ny)
            if not ct.is_in_vision(npos):
                continue
            nbid = ct.get_tile_building_id(npos)
            if nbid is None or nbid in protected:
                continue
            ntype = ct.get_entity_type(nbid)

            delivers = False
            if ntype == EntityType.HARVESTER:
                delivers = True
            elif ntype in (EntityType.CONVEYOR, EntityType.ARMOURED_CONVEYOR):
                nd = ct.get_direction(nbid)
                ddx, ddy = nd.delta()
                if (nx + ddx, ny + ddy) == (bp.x, bp.y):
                    delivers = True
            elif ntype == EntityType.SPLITTER:
                nd = ct.get_direction(nbid)
                sdx, sdy = nd.delta()
                for odx, ody in [(sdx, sdy), (-sdy, sdx), (sdy, -sdx)]:
                    if (nx + odx, ny + ody) == (bp.x, bp.y):
                        delivers = True
                        break
            elif ntype == EntityType.BRIDGE:
                tgt = ct.get_bridge_target(nbid)
                if (tgt.x, tgt.y) == (bp.x, bp.y):
                    delivers = True

            if delivers:
                protected.add(nbid)
                queue.append(nbid)

    return protected


class Sentinel(Unit):
    def __init__(self, ct: Controller) -> None:
        self._idle_rounds = 0
        self._last_target_hp: int = 0

    def run(self, ct: Controller) -> None:
        my_team = ct.get_team()
        best_target: Position | None = None
        best_priority = -1

        protected = _find_protected_buildings(ct, my_team)

        # Track friendly bot positions to avoid friendly fire
        friendly_tiles: set[tuple[int, int]] = set()
        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                fp = ct.get_position(uid)
                friendly_tiles.add((fp.x, fp.y))

        for bid in ct.get_nearby_buildings():
            if ct.get_team(bid) == my_team:
                continue
            if bid in protected:
                continue
            etype = ct.get_entity_type(bid)
            bp = ct.get_position(bid)
            priority = _target_priority(etype)
            if priority <= best_priority:
                continue
            if etype == EntityType.CORE:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        tp = Position(bp.x + dx, bp.y + dy)
                        if (tp.x, tp.y) in friendly_tiles:
                            continue  # friendly bot there
                        if ct.can_fire(tp):
                            best_priority = priority
                            best_target = tp
            else:
                if (bp.x, bp.y) in friendly_tiles:
                    continue  # friendly bot on target
                if ct.can_fire(bp):
                    best_priority = priority
                    best_target = bp

        for uid in ct.get_nearby_units():
            if ct.get_team(uid) == my_team:
                continue
            up = ct.get_position(uid)
            if not ct.can_fire(up):
                continue
            priority = _target_priority(ct.get_entity_type(uid))
            if priority > best_priority:
                best_priority = priority
                best_target = up

        if best_target is not None:
            # Detect healed targets — if HP went up, stop wasting ammo
            bid = ct.get_tile_building_id(best_target)
            hp = ct.get_hp(bid) if bid is not None else 0
            if hp > self._last_target_hp and self._last_target_hp > 0:
                self._idle_rounds = _IDLE_LIMIT  # force idle
            else:
                self._idle_rounds = 0
                self._last_target_hp = hp - 18  # sentinel does 18 dmg
                ct.fire(best_target)
                return

        # Check if we have ANY attackable enemy tiles
        has_enemy_target = False
        for tile in ct.get_attackable_tiles():
            bid = ct.get_tile_building_id(tile)
            if bid is not None and ct.get_team(bid) != my_team:
                # Skip if friendly bot on tile (would hit our bot)
                if (tile.x, tile.y) not in friendly_tiles:
                    has_enemy_target = True
                    break
            bot_id = ct.get_tile_builder_bot_id(tile)
            if bot_id is not None and ct.get_team(bot_id) != my_team:
                has_enemy_target = True
                break

        if not has_enemy_target:
            self._idle_rounds += 1
        else:
            self._idle_rounds = 0

        if self._idle_rounds >= _IDLE_LIMIT:
            # Self-destruct: ally builder within Chebyshev 3, no enemy bot within r²≤20
            spos = ct.get_position()
            ally_nearby = False
            enemy_nearby = False
            for uid in ct.get_nearby_units():
                upos = ct.get_position(uid)
                if ct.get_team(uid) == my_team:
                    if ct.get_entity_type(uid) == EntityType.BUILDER_BOT:
                        if max(abs(spos.x - upos.x), abs(spos.y - upos.y)) <= 3:
                            ally_nearby = True
                else:
                    if spos.distance_squared(upos) <= 20:
                        enemy_nearby = True
            if ally_nearby and not enemy_nearby:
                ct.self_destruct()


def _target_priority(etype: EntityType) -> int:
    match etype:
        case (
            EntityType.GUNNER
            | EntityType.SENTINEL
            | EntityType.BREACH
            | EntityType.LAUNCHER
        ):
            return 7
        case EntityType.BUILDER_BOT:
            return 6
        case EntityType.HARVESTER:
            return 5
        case (
            EntityType.CONVEYOR
            | EntityType.SPLITTER
            | EntityType.ARMOURED_CONVEYOR
            | EntityType.BRIDGE
        ):
            return 4
        case EntityType.CORE:
            return 3
        case EntityType.BARRIER:
            return 2
        case EntityType.ROAD:
            return 1
        case _:
            return 0
