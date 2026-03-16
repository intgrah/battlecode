default_map := "maps/default_large1.map26"

run a b map=default_map:
    cambc run {{a}} {{b}} {{map}}

watch a b map=default_map:
    cambc run {{a}} {{b}} {{map}} --watch

stats replay="replay.replay26":
    python scripts/replay_stats.py {{replay}}

economy replay="replay.replay26":
    python scripts/replay_economy.py {{replay}}

spatial replay="replay.replay26":
    python scripts/replay_spatial.py {{replay}}

map *args:
    python scripts/replay_map.py {{args}}

download match_id:
    python scripts/download_match.py {{match_id}}

match a b map=default_map:
    -cambc run {{a}} {{b}} {{map}} 2>&1 | grep -v "^Completed turn\|^Fatal\|^Python runtime\|^Update available\|^$"
    python scripts/replay_stats.py replay.replay26

proto:
    protoc --python_out=proto --proto_path=proto proto/cambc.proto

lint:
    ruff check --fix bots/ scripts/

fmt:
    ruff format bots/ scripts/

f: lint fmt

tournament *args:
    python scripts/tournament.py run {{args}}

snapshot:
    python scripts/tournament.py snapshot

latest:
    @python scripts/tournament.py latest

bots:
    @python scripts/tournament.py list

submit:
    #!/usr/bin/env bash
    bot=$(python scripts/tournament.py latest)
    echo "Submitting $bot"
    cambc submit "bots/$bot"

status:
    cambc status

docs:
    #!/usr/bin/env bash
    set -euo pipefail
    cd docs
    curl -s https://docs.battlecode.cam/llms.txt -o llms.txt
    grep -oP 'https://docs\.battlecode\.cam/\S+\.md' llms.txt | while read -r url; do
        path="${url#https://docs.battlecode.cam/}"
        mkdir -p "$(dirname "$path")"
        curl -s "$url" -o "$path"
        echo "$path"
    done
