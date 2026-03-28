"""Decode exfiltrated opponent source from replay markers (multi-unit).

Usage: python scripts/decode_source.py <match_id> [out_file]
"""

import json
import sys
import urllib.request
from pathlib import Path

from cambc.api import api_get
from cambc.auth import get_api_url, get_token

from proto.cambc_pb2 import Replay

STRIDE = 256


def extract(replay_data: bytes) -> tuple[bytes, int, int, int] | None:
    r = Replay()
    r.ParseFromString(replay_data)

    streams: dict[int, tuple[int, list[int]]] = {}

    for turn in r.turns:
        for update in turn.updates:
            for fd, val in update.ListFields():
                if fd.name != "place_entity":
                    continue
                e = val.entity
                if not e.HasField("marker") or e.team != 0:
                    continue
                v = e.marker.value
                eid = e.id

                if (v >> 16) == 0xBEEF:
                    file_size = v & 0xFFFF
                    if file_size == 0:
                        file_size = 0x10000
                    if eid not in streams:
                        streams[eid] = (file_size, [])
                elif eid in streams:
                    streams[eid][1].append(v)

    if not streams:
        return None

    best_eid = max(streams, key=lambda e: len(streams[e][1]))
    file_size, values = streams[best_eid]

    data = b""
    for v in values:
        data += v.to_bytes(4, "little")
    data = data[:file_size]

    return data, file_size, len(values), len(streams)


def download_replay(match_id: str, game: int) -> bytes:
    api_url = get_api_url()
    token = get_token()
    req = urllib.request.Request(
        f"{api_url}/api/matches/replay?matchId={match_id}&game={game}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return urllib.request.urlopen(resp["url"]).read()


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <match_id> [out_file]")
        return

    match_id = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else None

    match_data = api_get(f"/api/matches/{match_id}")
    games = match_data.get("games", [])

    best = b""
    best_info = ""

    for g in games:
        gn = g["gameNumber"]
        if not g.get("replayS3Key"):
            print(f"Game {gn}: no replay", file=sys.stderr)
            continue

        replay = download_replay(match_id, gn)
        result = extract(replay)
        if not result:
            print(f"Game {gn}: no exfil data", file=sys.stderr)
            continue

        data, file_size, n_values, n_units = result
        print(
            f"Game {gn}: {len(data)}/{file_size}b, {n_values} values, {n_units} units",
            file=sys.stderr,
        )

        if len(data) > len(best):
            best = data
            best_info = f"game {gn}"

    if not best:
        print("No exfil data found", file=sys.stderr)
        return

    text = best.decode("utf8", errors="replace")

    idx = text.find("class Player")
    if idx < 0:
        print("No class Player found", file=sys.stderr)
        if out_file:
            Path(out_file).write_bytes(best)
        return

    imp = max(text.rfind("import ", 0, idx), text.rfind("from ", 0, idx), 0)
    end = text.find("\x00", idx)
    if end < 0:
        end = len(text)

    source = text[imp:end].rstrip()
    print(f"Source: {len(source)} bytes from {best_info}", file=sys.stderr)

    if out_file:
        Path(out_file).write_text(source)
        print(f"Wrote to {out_file}", file=sys.stderr)
    else:
        print(source)


if __name__ == "__main__":
    main()
