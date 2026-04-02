from __future__ import annotations

from pathlib import Path

from proto.cambc_pb2 import Map, Replay


def load_replay(path: str | Path) -> Replay:
    r = Replay()
    r.ParseFromString(Path(path).read_bytes())
    return r


def load_map(path: str | Path) -> Map:
    m = Map()
    m.ParseFromString(Path(path).read_bytes())
    return m
