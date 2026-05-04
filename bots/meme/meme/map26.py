import posix


def read(path: str) -> bytes:
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
        b = data[pos]
        pos += 1
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
            if tag >> 3 == 1:
                x = val
            elif tag >> 3 == 2:
                y = val
        elif wire == 2:
            n, pos = _varint(data, pos)
            pos += n
    return x, y


def _decode_core(data: bytes) -> tuple[int, int, int, int]:
    cid = team = cx = cy = 0
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7
        field = tag >> 3
        if wire == 0:
            val, pos = _varint(data, pos)
            if field == 1:
                cid = val
            elif field == 2:
                team = val
        elif wire == 2:
            n, pos = _varint(data, pos)
            sub = data[pos : pos + n]
            pos += n
            if field == 3:
                cx, cy = _decode_pos(sub)
    return cid, team, cx, cy


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
            n, pos = _varint(data, pos)
            pos += n
    return tiles


def decode(
    data: bytes,
) -> tuple[int, int, list[list[int]], list[tuple[int, int, int, int]]]:
    width = height = 0
    grid: list[list[int]] = []
    cores: list[tuple[int, int, int, int]] = []
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        wire = tag & 7
        field = tag >> 3
        if wire == 0:
            val, pos = _varint(data, pos)
            if field == 1:
                width = val
            elif field == 2:
                height = val
        elif wire == 2:
            n, pos = _varint(data, pos)
            sub = data[pos : pos + n]
            pos += n
            if field == 3:
                grid.append(_decode_tile_row(sub))
            elif field == 4:
                cores.append(_decode_core(sub))
    return width, height, grid, cores
