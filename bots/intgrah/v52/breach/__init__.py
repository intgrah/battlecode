from __future__ import annotations

from typing import TYPE_CHECKING, override

from unit import StationaryUnit

if TYPE_CHECKING:
    from cambc import Controller

__all__ = ["Breach"]


class Breach(StationaryUnit):
    @override
    def run(self, ct: Controller) -> None:
        raise NotImplementedError
