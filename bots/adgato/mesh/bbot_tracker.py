"""Track last-known positions of enemy builder bots."""

from __future__ import annotations

from cambc import Controller, EntityType, Position


class BbotTracker:
    """Maintains a dict of enemy builder bot id -> last seen tile index.

    Each round, call ``update`` to refresh from vision. Bots currently
    visible are updated; tiles in vision that no longer have a bot are
    pruned.
    """

    def __init__(self, w: int, friendly: bool) -> None:
        self.w = w
        self.positions: dict[int, int] = {}  # bot id -> tile index
        self.friendly = friendly
        self._changed: bool = False

    def take_changed(self) -> bool:
        """Return whether the tracked set changed, and reset the flag."""
        changed = self._changed
        self._changed = False
        return changed

    def update(self, ct: Controller) -> None:
        """Refresh from nearby units. Prune ids whose last-known tile is in
        vision but no longer occupied by that bot."""
        w = self.w
        my_team = ct.get_team()
        mid = ct.get_id()
        friendly = self.friendly
        old = self.positions.copy()


        # Update visible enemy builder bots
        seen_ids: set[int] = set()
        for uid in ct.get_nearby_units():
            if mid == uid:
                continue
            if ct.get_entity_type(uid) != EntityType.BUILDER_BOT:
                continue
            if (ct.get_team(uid) == my_team) != friendly:
                continue
            seen_ids.add(uid)
            pos = ct.get_position(uid)
            idx = pos.y * w + pos.x
            self.positions[uid] = idx

        # Prune: if a bot's last-known tile is in vision but the bot
        # wasn't seen there, remove it
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
        """Return last-known positions as ``Position`` objects."""
        w = self.w
        return [Position(i % w, i // w) for i in self.positions.values()]

    def as_indices(self) -> set[int]:
        """Return last-known tile indices."""
        return set(self.positions.values())

    def draw_tracked(self, ct: Controller, r: int, g: int, b: int) -> None:
        """Draw an indicator dot on each last-known position."""
        w = self.w
        for i in self.positions.values():
            ct.draw_indicator_dot(Position(i % w, i // w), r, g, b)
