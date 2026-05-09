from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Generator

from cambc import EntityType, Position, ResourceType
from rust import EntityBridge, GameDiffPlaceEntity
from god_mode import GodMode
import random

if TYPE_CHECKING:
    from main import Player

_DELTAS: tuple[tuple[int, int], ...] = (
    (-1, -1), (0, -1), (1, -1),
    (-1,  0),          (1,  0),
    (-1,  1), (0,  1), (1,  1),
)


def long_bridge(p: Player) -> Generator:

    core_pos = [Position(core.x, core.y) for core in p.map.cores]
    friendly_core, enemy_core = (core_pos[0], core_pos[1]) if p.map.cores[0].team == p.team else (core_pos[1], core_pos[0])

    new_queue: deque[tuple[int, int]] = deque()
    for bid, age in p.bridge_queue:
        new_age = age + 1
        if new_age == 1:
            if bid in p.g.entities:
                bridge = p.g.entities[bid].as_variant
                assert isinstance(bridge, EntityBridge)
                target = Position(enemy_core.x + random.randint(-1, 1), enemy_core.y + random.randint(-1, 1))
                bridge.target = target
                GodMode.draw_line(p, bridge.base.position, target)
                GodMode.attack(p, enemy_core)

            new_queue.append((bid, new_age))
        elif new_age == 2:
            GodMode.destroy(p, bid)
            yield
        else:
            new_queue.append((bid, new_age))
    p.bridge_queue = new_queue

    w, h = p.map.width, p.map.height
    dx, dy = _DELTAS[p.bridge_pos_idx]
    p.bridge_pos_idx = (p.bridge_pos_idx + 1) % 8
    bridge_pos = Position(friendly_core.x + dx, friendly_core.y + dy)
    target = bridge_pos.add(friendly_core.direction_to(bridge_pos))

    bid: int | None = None
    if 0 <= target.x < w and 0 <= target.y < h:
        bid = GodMode.build(p, EntityType.BRIDGE, bridge_pos, target)
    if bid is not None:
        bridge = p.g.entities[bid].as_variant
        assert isinstance(bridge, EntityBridge)
        bridge.stored = ResourceType.RAW_AXIONITE
        bridge_place = p.g.replay_recorder.last_place_entity.as_variant
        assert isinstance(bridge_place, GameDiffPlaceEntity)
        bridge_replay = bridge_place.entity.as_variant
        assert isinstance(bridge_replay, EntityBridge)
        bridge_replay.stored = ResourceType.RAW_AXIONITE
        p.bridge_queue.append((bid, 0))

    yield
