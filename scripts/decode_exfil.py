import base64
import sys
from pathlib import Path

from proto import cambc_pb2


def extract_markers(replay_path: str) -> list[int]:
    r = cambc_pb2.Replay()
    r.ParseFromString(Path(replay_path).read_bytes())

    markers = []
    for turn in r.turns:
        for update in turn.updates:
            for fd, val in update.ListFields():
                if fd.name == "place_entity":
                    e = val.entity
                    if e.HasField("marker") and e.team == 0:
                        markers.append(e.marker.value)
    return markers


def decode_u32s(markers: list[int]) -> bytes:
    raw = b""
    for val in markers:
        raw += val.to_bytes(4, "little")

    length_str = raw[:8].decode("ascii")
    b64_len = int(length_str, 16)
    b64_data = raw[8 : 8 + b64_len]

    if len(b64_data) < b64_len:
        print(
            f"Warning: incomplete data ({len(b64_data)}/{b64_len} b64 chars)",
            file=sys.stderr,
        )

    return base64.b64decode(b64_data)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: decode_exfil.py <replay> [out_path]")
        return

    markers = extract_markers(sys.argv[1])
    print(f"Found {len(markers)} markers", file=sys.stderr)

    data = decode_u32s(markers)
    print(f"Decoded {len(data)} bytes", file=sys.stderr)

    parts = data.split(b"\x00")
    i = 0
    while i < len(parts) - 1:
        fname = parts[i].decode("utf8", errors="replace")
        fdata = parts[i + 1]
        if fname:
            print(f"\n=== {fname} ({len(fdata)} bytes) ===")
            print(fdata.decode("utf8", errors="replace"))
        i += 2

    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_bytes(data)
        print(f"\nRaw data written to {sys.argv[2]}", file=sys.stderr)


if __name__ == "__main__":
    main()
