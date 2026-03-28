from cambc import Controller, Direction, EntityType, Environment, Position
from unit import Unit
from util import INF

DIRECTIONS = [d for d in Direction if d != Direction.CENTRE]


class Core(Unit):
    def __init__(self, ct: Controller) -> None:
        self.spawned = 0
        self.core_pos: Position = ct.get_position()
        self.nearest_bridge_id: int | None = None
        self.last_resource_turn: int = 0
        self.expansion_cooldown: int = 0

    def run(self, ct: Controller) -> None:
        rnd = ct.get_current_round()
        pos = self.core_pos
        my_team = ct.get_team()
        ti, _ = ct.get_global_resources()
        cost, _ = ct.get_builder_bot_cost()

        # Track nearest friendly bridge and resource delivery
        best_bridge = None
        best_bridge_dist = INF
        for bid in ct.get_nearby_buildings():
            if (
                ct.get_entity_type(bid) != EntityType.BRIDGE
                or ct.get_team(bid) != my_team
            ):
                continue
            bp = ct.get_position(bid)
            d = max(abs(bp.x - pos.x), abs(bp.y - pos.y))
            if d < best_bridge_dist:
                best_bridge_dist = d
                best_bridge = bid

        if best_bridge is not None:
            self.nearest_bridge_id = best_bridge
            if ct.get_stored_resource(best_bridge) is not None:
                self.last_resource_turn = rnd

        bridge_destroyed = self.nearest_bridge_id is not None and best_bridge is None
        bridge_starved = (
            self.nearest_bridge_id is not None and rnd - self.last_resource_turn >= 5
        )

        # Emergency spawn: bridge destroyed or starved (only after economy established)
        if rnd > 50 and (bridge_starved or bridge_destroyed) and ti >= cost:
            sp = _best_spawn_pos(ct, pos)
            if sp is not None:
                ct.spawn_builder(sp)
                self.spawned += 1
                self.last_resource_turn = rnd
                return

        # Imminent need: fewer than 2 builders or core is damaged
        if (self.spawned < 2 or ct.get_hp() < ct.get_max_hp()) and ti >= cost:
            sp = _best_spawn_pos(ct, pos)
            if sp is not None:
                ct.spawn_builder(sp)
                self.spawned += 1
                return

        # Expansion: after round 50, with economy buffer
        h_cost, _ = ct.get_harvester_cost()
        can_afford = ti > cost * 2 + h_cost + 100

        if can_afford and rnd > 50:
            has_delivering_bridge = False
            for bid in ct.get_nearby_buildings():
                if (
                    ct.get_entity_type(bid) != EntityType.BRIDGE
                    or ct.get_team(bid) != my_team
                ):
                    continue
                bt = ct.get_bridge_target(bid)
                if bt.distance_squared(pos) <= 2:
                    has_delivering_bridge = True
                    break

            if has_delivering_bridge:
                self.expansion_cooldown += 1
                if self.expansion_cooldown > 5:
                    sp = _best_spawn_pos(ct, pos)
                    if sp is not None:
                        ct.spawn_builder(sp)
                        self.spawned += 1
                        self.expansion_cooldown = 0
                        return


def _best_spawn_pos(ct: Controller, pos: Position) -> Position | None:
    """Pick best spawnable tile: prefer toward visible ore, else toward map centre."""
    ore_positions: list[Position] = []
    for t in ct.get_nearby_tiles():
        if not ct.is_in_vision(t):
            continue
        if ct.get_tile_env(t) != Environment.ORE_TITANIUM:
            continue
        bid = ct.get_tile_building_id(t)
        if bid is not None and ct.get_entity_type(bid) == EntityType.HARVESTER:
            continue
        ore_positions.append(t)

    if ore_positions:
        pos.direction_to(ore_positions[0])
    else:
        cx = ct.get_map_width() // 2
        cy = ct.get_map_height() // 2
        pos.direction_to(Position(cx, cy))

    for d in DIRECTIONS:
        sp = pos.add(d)
        if ct.can_spawn(sp):
            return sp
    return None
