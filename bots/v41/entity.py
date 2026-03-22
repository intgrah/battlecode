from cambc import Controller


class Entity:
    def __init__(self, ct: Controller) -> None:
        self.w = ct.get_map_width()
        self.h = ct.get_map_height()
        self.team = ct.get_team()

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def run(self, ct: Controller) -> None:
        raise NotImplementedError
