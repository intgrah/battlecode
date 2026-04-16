from abc import ABC, abstractmethod

from cambc import Controller

__all__ = ["Unit"]


class Unit(ABC):
    @abstractmethod
    def run(self, ct: Controller) -> None: ...
