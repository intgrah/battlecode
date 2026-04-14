from __future__ import annotations

from dataclasses import dataclass

from cambc import ResourceType

_ZERO_FLOW: tuple[int, int, int] = (0, 0, 0)
_LAZY_FLOW_TABLE: list[tuple[int, int, int]] = [_ZERO_FLOW] * 256

FLOW_TI = 0
FLOW_AX = 1
FLOW_RAX = 2


@dataclass(slots=True)
class Flow:
    recent_outgoing: int
    rid: int | None

    def update(self, rtype: ResourceType | None, rid: int | None) -> None:
        if rid == self.rid:
            rtype = None

        self.rid = rid

        flow_value = (
            1
            if rtype == ResourceType.TITANIUM
            else 2
            if rtype == ResourceType.RAW_AXIONITE
            else 3
            if rtype == ResourceType.REFINED_AXIONITE
            else 0
        )

        self.recent_outgoing = (self.recent_outgoing << 2) & 0xFF | flow_value

        if not self.has_flow() or any(self.get_flow()):
            return

        flow_new = [0, 0, 0, 0]
        history = self.recent_outgoing
        while history > 0:
            flow_new[history & 3] += 1
            history >>= 2

        _LAZY_FLOW_TABLE[self.recent_outgoing] = (flow_new[1], flow_new[2], flow_new[3])

    def has_flow(self) -> bool:
        return self.recent_outgoing > 0

    def get_flow(self) -> tuple[int, int, int]:
        return _LAZY_FLOW_TABLE[self.recent_outgoing]
