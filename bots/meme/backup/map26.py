from __future__ import annotations

import posix
from dataclasses import dataclass
from typing import Final

from cambc import Environment, Team

_ENV_FROM_INT: tuple[Environment, ...] = tuple(Environment)
_TEAM_FROM_INT: tuple[Team, ...] = tuple(Team)


@dataclass(frozen=True)
class Core:
    id: int
    team: Team
    x: int
    y: int


class Map26:
    PATH: Final = "/sandbox/out/game_map.map26"

    def __init__(
        self,
        width: int,
        height: int,
        grid: list[Environment],
        cores: list[Core],
    ) -> None:
        self.width: Final = width
        self.height: Final = height
        self.cores: Final = cores
        self.grid: Final = grid

    def tile(self, x: int, y: int) -> Environment:
        return self.grid[y * self.width + x]

    @staticmethod
    def read(path: str = PATH) -> Map26:
        fd = posix.open(path, posix.O_RDONLY)
        chunks = []
        while True:
            chunk = posix.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        posix.close(fd)
        return Map26._decode(b"".join(chunks))

    @staticmethod
    def _varint(data: bytes, pos: int) -> tuple[int, int]:
        result = shift = 0
        while True:
            b = data[pos]
            pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result, pos
            shift += 7

    @staticmethod
    def _decode_pos(data: bytes) -> tuple[int, int]:
        x = y = pos = 0
        while pos < len(data):
            tag, pos = Map26._varint(data, pos)
            wire = tag & 7
            if wire == 0:
                val, pos = Map26._varint(data, pos)
                if tag >> 3 == 1:
                    x = val
                elif tag >> 3 == 2:
                    y = val
            elif wire == 2:
                n, pos = Map26._varint(data, pos)
                pos += n
        return x, y

    @staticmethod
    def _decode_core(data: bytes) -> Core:
        cid = team = cx = cy = 0
        pos = 0
        while pos < len(data):
            tag, pos = Map26._varint(data, pos)
            wire = tag & 7
            field = tag >> 3
            if wire == 0:
                val, pos = Map26._varint(data, pos)
                if field == 1:
                    cid = val
                elif field == 2:
                    team = val
            elif wire == 2:
                n, pos = Map26._varint(data, pos)
                sub = data[pos : pos + n]
                pos += n
                if field == 3:
                    cx, cy = Map26._decode_pos(sub)
        return Core(id=cid, team=_TEAM_FROM_INT[team], x=cx, y=cy)

    @staticmethod
    def _decode_tile_row(data: bytes) -> list[int]:
        tiles: list[int] = []
        pos = 0
        while pos < len(data):
            tag, pos = Map26._varint(data, pos)
            wire = tag & 7
            if tag >> 3 == 1:
                if wire == 0:
                    val, pos = Map26._varint(data, pos)
                    tiles.append(val)
                elif wire == 2:
                    n, pos = Map26._varint(data, pos)
                    end = pos + n
                    while pos < end:
                        val, pos = Map26._varint(data, pos)
                        tiles.append(val)
            elif wire == 0:
                _, pos = Map26._varint(data, pos)
            elif wire == 2:
                n, pos = Map26._varint(data, pos)
                pos += n
        return tiles

    @staticmethod
    def _decode(data: bytes) -> Map26:
        width = height = 0
        rows: list[list[int]] = []
        cores: list[Core] = []
        pos = 0
        while pos < len(data):
            tag, pos = Map26._varint(data, pos)
            wire = tag & 7
            field = tag >> 3
            if wire == 0:
                val, pos = Map26._varint(data, pos)
                if field == 1:
                    width = val
                elif field == 2:
                    height = val
            elif wire == 2:
                n, pos = Map26._varint(data, pos)
                sub = data[pos : pos + n]
                pos += n
                if field == 3:
                    rows.append(Map26._decode_tile_row(sub))
                elif field == 4:
                    cores.append(Map26._decode_core(sub))
        grid = [_ENV_FROM_INT[v] for row in rows for v in row]
        return Map26(width, height, grid, cores)
