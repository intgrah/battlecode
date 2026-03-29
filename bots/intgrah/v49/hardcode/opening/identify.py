from cambc import Controller, GameConstants, Position
from hardcode.known import KnownMap
from hardcode.map import CANDIDATES, CORE_B, DIMENSIONS, TILES, decode


def identify_map(ct: Controller, core_pos: Position) -> KnownMap | None:
    w = ct.get_map_width()
    h = ct.get_map_height()

    key_a = (w, h, core_pos)
    candidates = CANDIDATES.get(key_a)

    if candidates is None:
        candidates = _candidates_for_core_b(w, h, core_pos)

    if candidates is None:
        return None

    for km in candidates:
        if _verify_vision(ct, km, w, h):
            return km
    return None


def _candidates_for_core_b(w: int, h: int, core_pos: Position) -> list[KnownMap] | None:
    result: list[KnownMap] = []
    for km, cb in CORE_B.items():
        dw, dh = DIMENSIONS[km]
        if dw == w and dh == h and cb == core_pos:
            result.append(km)
    return result or None


def _verify_vision(
    ct: Controller,
    km: KnownMap,
    w: int,
    h: int,
) -> bool:
    n = w * h
    dw, dh = DIMENSIONS[km]
    if dw != w or dh != h:
        return False

    tiles = decode(TILES[km](), n)

    for t in ct.get_nearby_tiles(GameConstants.CORE_VISION_RADIUS_SQ):
        i = t.y * w + t.x
        expected = tiles[i]
        actual = ct.get_tile_env(t)
        if actual != expected:
            return False
    return True
