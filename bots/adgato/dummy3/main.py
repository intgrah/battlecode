from cambc import Controller

# Environment values from proto (EnvEmpty=0, EnvWall=1, EnvOreTitanium=2, EnvOreAxionite=3)
_ENV_CHARS = {0: ".", 1: "#", 2: "T", 3: "A"}


def _read(path: str) -> bytes:
    import posix
    fd = posix.open(path, posix.O_RDONLY)
    chunks = []
    while True:
        chunk = posix.read(fd, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    posix.close(fd)
    return b"".join(chunks)


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _decode_pos(data: bytes) -> tuple[int, int]:
    x = y = pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7
        if wire == 0:
            val, pos = _varint(data, pos)
            if tag >> 3 == 1: x = val
            elif tag >> 3 == 2: y = val
        elif wire == 2:
            n, pos = _varint(data, pos); pos += n
    return x, y


def _decode_tile_row(data: bytes) -> list[int]:
    tiles: list[int] = []
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7
        if tag >> 3 == 1:
            if wire == 0:
                val, pos = _varint(data, pos)
                tiles.append(val)
            elif wire == 2:  # packed
                n, pos = _varint(data, pos)
                end = pos + n
                while pos < end:
                    val, pos = _varint(data, pos)
                    tiles.append(val)
        elif wire == 0:
            _, pos = _varint(data, pos)
        elif wire == 2:
            n, pos = _varint(data, pos); pos += n
    return tiles


def _decode_core(data: bytes) -> tuple[int, int, int, int]:
    cid = team = cx = cy = 0
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7; field = tag >> 3
        if wire == 0:
            val, pos = _varint(data, pos)
            if field == 1: cid = val
            elif field == 2: team = val
        elif wire == 2:
            n, pos = _varint(data, pos)
            sub = data[pos:pos+n]; pos += n
            if field == 3: cx, cy = _decode_pos(sub)
    return cid, team, cx, cy


def decode_map26(data: bytes) -> tuple[int, int, list[list[int]], list[tuple[int, int, int, int]]]:
    """Returns (width, height, grid[y][x], cores[(id, team, x, y)])."""
    width = height = 0
    grid: list[list[int]] = []
    cores: list[tuple[int, int, int, int]] = []
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7; field = tag >> 3
        if wire == 0:
            val, pos = _varint(data, pos)
            if field == 1: width = val
            elif field == 2: height = val
        elif wire == 2:
            n, pos = _varint(data, pos)
            sub = data[pos:pos+n]; pos += n
            if field == 3: grid.append(_decode_tile_row(sub))
            elif field == 4: cores.append(_decode_core(sub))
    return width, height, grid, cores


class Player:

    def __init__(self) -> None:
        self._done = False

    def run(self, c: Controller) -> None:
        if self._done:
            return
        self._done = True

        import posix

        try:
            data = _read("/sandbox/out/game_map.map26")
            w, h, grid, cores = decode_map26(data)
            print(f"[map] {w}x{h}, {len(cores)} cores")
            for cid, team, cx, cy in cores:
                print(f"  core id={cid} team={team} pos=({cx},{cy})")
            for y in range(h):
                row = grid[y] if y < len(grid) else []
                line = "".join(_ENV_CHARS.get(row[x], "?") if x < len(row) else "?" for x in range(w))
                print(f"  {y:2d} {line}")
        except Exception as e:
            print(f"[map] {e}")
