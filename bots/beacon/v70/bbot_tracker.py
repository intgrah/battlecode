"""Track last-known positions of friendly builder bots. From adgato/mesh."""

from __future__ import annotations

from cambc import Controller, EntityType, Position


class BbotTracker:
    def __init__(self, w: int) -> None:
        self.w = w
        self.positions: dict[int, int] = {}
        self._changed: bool = False

    def take_changed(self) -> bool:
        changed = self._changed
        self._changed = False
        return changed

    def update(self, ct: Controller) -> None:
        w = self.w
        my_team = ct.get_team()
        mid = ct.get_id()

        seen_ids: set[int] = set()
        for uid in ct.get_nearby_units():
            if mid == uid:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if ct.get_team(uid) != my_team:
                continue
            seen_ids.add(uid)
            pos = ct.get_position(uid)
            self.positions[uid] = pos.y * w + pos.x

        to_remove: list[int] = []
        for uid, idx in self.positions.items():
            if uid in seen_ids:
                continue
            tile = Position(idx % w, idx // w)
            if ct.is_in_vision(tile):
                to_remove.append(uid)
        for uid in to_remove:
            del self.positions[uid]

        self._changed = bool(seen_ids) or bool(to_remove)

    def as_positions(self) -> list[Position]:
        w = self.w
        return [Position(i % w, i // w) for i in self.positions.values()]
