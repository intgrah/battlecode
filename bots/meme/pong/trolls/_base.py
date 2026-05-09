from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cambc import Controller


class Troll(ABC):
    @abstractmethod
    def run(self, ct: Controller) -> None: ...
