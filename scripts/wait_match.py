import sys
import time

from cambc.api import api_get


def wait(match_id: str) -> None:
    while True:
        data = api_get(f"/api/matches/{match_id}")
        m = data["match"]
        status = m.get("status", "?")
        games = data.get("games", [])
        if status in {"complete", "error"}:
            score = f"{m.get('scoreA', 0)}-{m.get('scoreB', 0)}"
            print(f"{status} {score} ({len(games)} games)")
            break
        stage = m.get("stage", "")
        print(f"{status} {stage}", end="\r", flush=True)
        time.sleep(3)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <match_id>")
        sys.exit(1)
    wait(sys.argv[1])


if __name__ == "__main__":
    main()
