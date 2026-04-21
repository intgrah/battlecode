import gc

from cambc import Controller, EntityType

_OBJECT_SIZES: tuple[int, ...] = (8, 16, 24, 32, 40, 48)
_BREAK_SIZES: tuple[int, ...] = (56, 64)
_MAX_SIZE: int = 500_000_000
_SPACING: int = 2000
_POOL_SIZE: int = 4000


class Player:
    def __init__(self) -> None:
        self._sprayed = False
        self._fragments: list[list[bytearray]] = []

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        if self._sprayed:
            return
        self._sprayed = True

        for size in _OBJECT_SIZES:
            batch = [bytearray(size) for _ in range(_MAX_SIZE // size)]
            self._fragments.append(batch[::_SPACING])
            gc.collect()

        for size in _BREAK_SIZES:
            batch = [bytearray(size) for _ in range(_POOL_SIZE // size)]
            self._fragments.append(batch)
