"""Base unit ABC."""

from abc import ABC, abstractmethod

from cambc import Controller


class Unit(ABC):
    @abstractmethod
    def run(self, ct: Controller) -> None: ...
