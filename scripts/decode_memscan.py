import sys
from pathlib import Path

from proto.cambc_pb2 import Replay


def decode(replay_path: str) -> bytes:
    r = Replay()
    r.ParseFromString(Path(replay_path).read_bytes())

    # Track per-entity streams: eid -> (file_size, [u32 values])
    streams: dict[int, tuple[int, list[int]]] = {}

    for turn in r.turns:
        for update in turn.updates:
            for fd, val in update.ListFields():
                if fd.name != "place_entity":
                    continue
                e = val.entity
                if not e.HasField("marker") or e.team != 0:
                    continue
                eid = e.id
                v = e.marker.value

                if (v >> 16) == 0xBEEF:
                    file_size = v & 0xFFFF
                    if eid not in streams:
                        streams[eid] = (file_size, [])
                elif eid in streams:
                    streams[eid][1].append(v)

    if not streams:
        return b""

    # Use the longest stream (most data)
    best_eid = max(streams, key=lambda e: len(streams[e][1]))
    file_size, values = streams[best_eid]

    data = b""
    for v in values:
        data += v.to_bytes(4, "little")
    data = data[:file_size]

    n_streams = len(streams)
    print(
        f"file_size={file_size} streams={n_streams} "
        f"best_eid={best_eid} values={len(values)} "
        f"coverage={min(len(values) * 4, file_size)}/{file_size}",
        file=sys.stderr,
    )
    return data


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <replay...>")
        return

    for path in sys.argv[1:]:
        data = decode(path)
        if data:
            print(f"  {path}: {len(data)} bytes", file=sys.stderr)
            sys.stdout.buffer.write(data)
            if len(data) >= int.from_bytes(data[:2], "little") if len(data) >= 2 else 0:
                break


if __name__ == "__main__":
    main()
