default_map := "maps/default_large1.map26"

run a b map=default_map:
    .venv/bin/cambc run {{a}} {{b}} {{map}}

watch a b map=default_map:
    .venv/bin/cambc run {{a}} {{b}} {{map}} --watch

stats replay="replay.replay26":
    .venv/bin/python scripts/replay_stats.py {{replay}}

match a b map=default_map:
    .venv/bin/cambc run {{a}} {{b}} {{map}}
    .venv/bin/python scripts/replay_stats.py replay.replay26

proto:
    protoc --python_out=proto --proto_path=proto proto/cambc.proto

lint:
    .venv/bin/ruff check bots/ scripts/

fmt:
    .venv/bin/ruff format bots/ scripts/

tournament *args:
    .venv/bin/python scripts/tournament.py run {{args}}

snapshot:
    .venv/bin/python scripts/tournament.py snapshot

latest:
    @.venv/bin/python scripts/tournament.py latest

bots:
    @.venv/bin/python scripts/tournament.py list

submit:
    #!/usr/bin/env bash
    bot=$(.venv/bin/python scripts/tournament.py latest)
    echo "Submitting $bot"
    .venv/bin/cambc submit "bots/$bot"

status:
    .venv/bin/cambc status

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
