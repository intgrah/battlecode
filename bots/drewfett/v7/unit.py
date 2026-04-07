from abc import ABC, abstractmethod

from cambc import Controller


class Unit(ABC):
    @abstractmethod
    def __init__(self, ct: Controller) -> None: ...

    @abstractmethod
    def run(self, ct: Controller) -> None: ...
