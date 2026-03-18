"""Scan replay files for exfiltrated data.

Checks:
1. BotOutput.stdout fields via protobuf parsing
2. Raw byte search for known markers (bbbbbbbb, aaaaaaaa, /sandbox/, etc.)
3. Looks for injected data that breaks protobuf (dd-style injection)
"""

import sys
from pathlib import Path

from google.protobuf.message import DecodeError

from proto import cambc_pb2

MARKERS = [
    b"bbbbbbbb",
    b"aaaaaaaa",
    b"XXXX_PAYLOAD",
    b"/sandbox/",
    b"/bot_b/",
    b"/bot_a/",
    b"success",
    b"def run(",
    b"import ",
    b"from cambc",
    b"class Player",
]


def scan_protobuf(path: str) -> list[dict]:
    with Path(path).open("rb") as f:
        data = f.read()
    r = cambc_pb2.Replay()
    try:
        r.ParseFromString(data)
    except DecodeError as e:
        return [{"type": "parse_error", "error": str(e), "size": len(data)}]

    results = []
    for i, turn in enumerate(r.turns):
        for u in turn.updates:
            if u.HasField("bot_output"):
                bo = u.bot_output
                if not bo.stdout:
                    continue
                entry = {
                    "type": "stdout",
                    "turn": i + 1,
                    "entity_id": bo.id,
                    "length": len(bo.stdout),
                    "tled": bo.tled,
                    "exec_us": bo.exec_time_us,
                }
                suspicious = False
                for m in MARKERS:
                    if m in bo.stdout.encode():
                        suspicious = True
                        break
                if suspicious or len(bo.stdout) > 1000:
                    entry["preview"] = bo.stdout[:500]
                    entry["suspicious"] = True
                    results.append(entry)
    return results


def scan_raw(path: str) -> list[dict]:
    with Path(path).open("rb") as f:
        data = f.read()
    results = []
    for m in MARKERS:
        idx = 0
        while True:
            idx = data.find(m, idx)
            if idx == -1:
                break
            context = data[max(0, idx - 20) : idx + len(m) + 80]
            results.append(
                {
                    "type": "raw_marker",
                    "marker": m.decode("utf-8", errors="replace"),
                    "offset": idx,
                    "context": repr(context),
                },
            )
            idx += len(m)
    return results


def scan_trailing(path: str) -> list[dict]:
    with Path(path).open("rb") as f:
        data = f.read()
    r = cambc_pb2.Replay()
    try:
        consumed = r.ParseFromString(data)
    except DecodeError:
        return []
    if consumed and consumed < len(data):
        trailing = data[consumed:]
        return [
            {
                "type": "trailing_data",
                "offset": consumed,
                "length": len(trailing),
                "preview": repr(trailing[:200]),
            },
        ]
    return []


def scan_file(path: str) -> bool:
    p = Path(path)
    print(f"\n{'=' * 60}")
    print(f"  {p.name}  ({p.stat().st_size} bytes)")
    print(f"{'=' * 60}")

    pb = scan_protobuf(path)
    raw = scan_raw(path)
    trail = scan_trailing(path)

    findings = pb + raw + trail
    if not findings:
        print("  No exfiltration detected.")
        return False

    for f in findings:
        t = f["type"]
        if t == "parse_error":
            print(f"  PROTOBUF PARSE ERROR: {f['error']}")
            print(f"    File size: {f['size']}")
        elif t == "stdout":
            print(
                f"  STDOUT t={f['turn']} id={f['entity_id']} len={f['length']} tled={f['tled']}",
            )
            if f.get("preview"):
                for line in f["preview"].split("\n")[:10]:
                    print(f"    | {line}")
                if len(f["preview"]) >= 500:
                    print("    | ... (truncated)")
        elif t == "raw_marker":
            print(f"  RAW MARKER '{f['marker']}' at offset {f['offset']}")
            print(f"    {f['context']}")
        elif t == "trailing_data":
            print(f"  TRAILING DATA at offset {f['offset']} ({f['length']} bytes)")
            print(f"    {f['preview']}")

    return True


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <replay_file_or_directory> [...]")
        sys.exit(1)

    paths: list[str] = []
    for arg in sys.argv[1:]:
        if Path(arg).is_dir():
            paths.extend(
                str(entry)
                for entry in sorted(Path(arg).iterdir())
                if entry.name.endswith(".replay26")
            )
        else:
            paths.append(arg)

    found = 0
    for p in paths:
        if scan_file(p):
            found += 1

    print(f"\n--- {found}/{len(paths)} files with findings ---")


if __name__ == "__main__":
    main()
