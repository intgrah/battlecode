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

network replay="replay.replay26":
    python scripts/replay_network.py {{replay}}

combat replay="replay.replay26":
    python scripts/replay_combat.py {{replay}}

health replay="replay.replay26":
    python scripts/replay_health.py {{replay}}

deep replay="replay.replay26":
    python scripts/replay_deep.py {{replay}}

flow replay="replay.replay26":
    python scripts/replay_flow.py {{replay}}

graph replay="replay.replay26":
    python scripts/replay_graph.py {{replay}}

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

submit bot="":
    #!/usr/bin/env bash
    if [ -z "{{bot}}" ]; then
        bot=$(python scripts/tournament.py latest)
    else
        bot="{{bot}}"
    fi
    echo "Submitting $bot"
    cambc submit "bots/$bot"

challenge bot opponent:
    #!/usr/bin/env bash
    ranked="${RANKED:-v21}"
    echo "Submitting {{bot}}"
    cambc submit "bots/{{bot}}"
    echo "Challenging {{opponent}}"
    cambc unrated "{{opponent}}"
    echo "Restoring $ranked"
    cambc submit "bots/$ranked"

challenge-all bot:
    #!/usr/bin/env bash
    ranked="${RANKED:-v21}"
    echo "Submitting {{bot}}"
    cambc submit "bots/{{bot}}"
    cambc unrated "87ee9a96-2175-4a03-afbb-a1ed3b67bb84" || true
    cambc unrated "05a96b0d-3ce5-4be8-921b-570dd973994a" || true
    echo "Restoring $ranked"
    cambc submit "bots/$ranked"

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
