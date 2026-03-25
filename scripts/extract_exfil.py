from __future__ import annotations

import sys
from pathlib import Path

from proto.cambc_pb2 import Replay


def extract(path: str) -> None:
    data = Path(path).read_bytes()
    r = Replay()
    r.ParseFromString(data)

    for turn in r.turns:
        for u in turn.updates:
            if u.HasField("bot_output") and len(u.bot_output.stdout) > 1000:
                stdout = u.bot_output.stdout
                idx = stdout.find("total ")
                if idx < 0:
                    continue
                content = stdout[idx:]
                print(content)
                return

    print("No exfiltrated content found.")


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <replay.replay26>")
        sys.exit(1)
    extract(sys.argv[1])


if __name__ == "__main__":
    main()
