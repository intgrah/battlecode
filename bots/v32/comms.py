from __future__ import annotations

from cambc import Controller, EntityType, Position
from marker import (
    BreakAlert,
    Marker,
    OreClaim,
    PressureSummary,
    Threat,
    decode,
    is_stale,
)
from params import BREAK_TTL, CLAIM_TTL, PRESSURE_TTL, THREAT_TTL
from util import DIRS


class MarkerReader:
    """Scans visible markers and categorizes them."""

    def __init__(self) -> None:
        self.claims: list[tuple[Position, OreClaim]] = []
        self.threats: list[tuple[Position, Threat]] = []
        self.pressure: list[tuple[Position, PressureSummary]] = []
        self.breaks: list[tuple[Position, BreakAlert]] = []

    def scan(self, ct: Controller) -> None:
        self.claims.clear()
        self.threats.clear()
        self.pressure.clear()
        self.breaks.clear()

        my = ct.get_team()
        rnd = ct.get_current_round()

        for t in ct.get_nearby_tiles():
            bid = ct.get_tile_building_id(t)
            if bid is None:
                continue
            if ct.get_entity_type(bid) != EntityType.MARKER:
                continue
            if ct.get_team(bid) != my:
                continue
            m = decode(ct.get_marker_value(bid))
            match m:
                case OreClaim() if not is_stale(m.freshness, rnd, CLAIM_TTL):
                    self.claims.append((t, m))
                case Threat() if not is_stale(m.freshness, rnd, THREAT_TTL):
                    self.threats.append((t, m))
                case PressureSummary() if not is_stale(m.freshness, rnd, PRESSURE_TTL):
                    self.pressure.append((t, m))
                case BreakAlert() if not is_stale(m.freshness, rnd, BREAK_TTL):
                    self.breaks.append((t, m))

    def is_ore_claimed(self, ore: Position) -> bool:
        for _, claim in self.claims:
            if claim.ore_x == ore.x and claim.ore_y == ore.y and claim.state != 3:
                return True
        return False


class MarkerWriter:
    """Decides which marker to write each turn."""

    def __init__(self) -> None:
        self._pending: tuple[Position, int] | None = None

    def propose(self, pos: Position, marker: Marker, priority: int) -> None:
        encoded = marker.encode()
        if self._pending is None or priority > self._pending[2]:
            self._pending = (pos, encoded, priority)

    def _safe_to_mark(self, ct: Controller, pos: Position) -> bool:
        bid = ct.get_tile_building_id(pos)
        if bid is None:
            return ct.can_place_marker(pos)
        et = ct.get_entity_type(bid)
        if et == EntityType.MARKER:
            return ct.can_place_marker(pos)
        return False

    def flush(self, ct: Controller) -> None:
        if self._pending is None:
            return
        pos, val, _ = self._pending
        if self._safe_to_mark(ct, pos):
            ct.place_marker(pos, val)
        else:
            for d in DIRS:
                adj = pos.add(d)
                if self._safe_to_mark(ct, adj):
                    ct.place_marker(adj, val)
                    break
        self._pending = None
