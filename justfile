default_map := "maps/default_large1.map26"
small_map := "maps/default_small1.map26"
_analysis := "cd scripts && python -m analysis"

run a b map=default_map:
    cambc run {{a}} {{b}} {{map}}

w replay="replay.replay26":
    cambc watch {{replay}}

flow replay="replay.replay26":
    python scripts/flow_visualize.py {{replay}}

watch a b map=default_map:
    cambc run {{a}} {{b}} {{map}} --watch

analyze replay="replay.replay26" *args="":
    {{_analysis}} ../{{replay}} {{args}}

stats replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s summary

economy replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s economy

network replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s network

spatial replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s spatial

defense replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s defense

combat replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s combat

bots replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s bots

compare replay="replay.replay26":
    {{_analysis}} ../{{replay}} -s compare

full replay="replay.replay26":
    python scripts/replay_full.py {{replay}}

debug replay="replay.replay26" *args="":
    python scripts/replay_debug.py {{replay}} {{args}}

debug-team replay="replay.replay26" team="A" *args="":
    python scripts/replay_debug.py {{replay}} --team {{team}} {{args}}

debug-entity replay="replay.replay26" entity="" *args="":
    python scripts/replay_debug.py {{replay}} --entity {{entity}} {{args}}

explain replay="replay.replay26" *args="":
    python scripts/replay_debug.py {{replay}} --min-priority 40 --no-map {{args}}

map *args:
    python scripts/replay_map.py {{args}}

download match_id:
    python scripts/download_match.py {{match_id}}

match a b map=default_map:
    -cambc run {{a}} {{b}} {{map}} 2>&1 | grep -v "^Completed turn\|^Fatal\|^Python runtime\|^Update available\|^$"
    {{_analysis}} ../replay.replay26 -s summary

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

bots-list:
    @python scripts/tournament.py list

submit bot="":
    #!/usr/bin/env bash
    if [ -z "{{bot}}" ]; then
        bot=$(python scripts/tournament.py latest)
    else
        bot="{{bot}}"
    fi
    find "bots/$bot" -type d -name __pycache__ -exec rm -rf {} +
    echo "Submitting $bot"
    cambc submit "bots/$bot"

challenge bot opponent:
    #!/usr/bin/env bash
    ranked="${RANKED:-v21}"
    find "bots/{{bot}}" -type d -name __pycache__ -exec rm -rf {} +
    echo "Submitting {{bot}}"
    cambc submit "bots/{{bot}}"
    echo "Challenging {{opponent}}"
    cambc unrated "{{opponent}}"
    echo "Restoring $ranked"
    cambc submit "bots/$ranked"

challenge-all bot:
    #!/usr/bin/env bash
    ranked="${RANKED:-v21}"
    find "bots/{{bot}}" -type d -name __pycache__ -exec rm -rf {} +
    echo "Submitting {{bot}}"
    cambc submit "bots/{{bot}}"
    cambc unrated "87ee9a96-2175-4a03-afbb-a1ed3b67bb84" || true
    cambc unrated "05a96b0d-3ce5-4be8-921b-570dd973994a" || true
    cambc unrated "421bd2a2-c421-4359-a06a-9a517f1e08a7" || true
    echo "Restoring $ranked"
    cambc submit "bots/$ranked"

online *args:
    python scripts/online.py {{args}}

status:
    cambc status

_vps := "chi"
_vps_dir := "~/battlecode"
_vps_cambc := "~/battlecode/.venv/bin/cambc"

sync:
    rsync -av --delete bots/ {{_vps}}:{{_vps_dir}}/bots/
    rsync -av maps/ {{_vps}}:{{_vps_dir}}/maps/
    rsync -av scripts/ {{_vps}}:{{_vps_dir}}/scripts/
    rsync -av proto/ {{_vps}}:{{_vps_dir}}/proto/

remote-run a b map=default_map:
    just sync
    ssh {{_vps}} "cd {{_vps_dir}} && {{_vps_cambc}} run bots/{{a}} bots/{{b}} {{map}} --replay replay.replay26"
    scp {{_vps}}:{{_vps_dir}}/replay.replay26 replay_remote.replay26

remote-match a b map=default_map:
    just sync
    ssh {{_vps}} "cd {{_vps_dir}} && {{_vps_cambc}} run bots/{{a}} bots/{{b}} {{map}} --replay replay.replay26 2>&1 | grep -v '^Completed turn\|^Fatal\|^Python runtime\|^Update available\|^$$'"
    ssh {{_vps}} "cd {{_vps_dir}}/scripts && ../.venv/bin/python -m analysis ../replay.replay26 -s summary"
    scp {{_vps}}:{{_vps_dir}}/replay.replay26 replay_remote.replay26

remote-tournament *args:
    just sync
    ssh {{_vps}} "cd {{_vps_dir}} && nohup .venv/bin/python scripts/tournament.py run {{args}} > tournament.log 2>&1 &"
    @echo "Tournament running on VPS. Check with: just remote-status"

remote-status:
    ssh {{_vps}} "tail -20 {{_vps_dir}}/tournament.log 2>/dev/null || echo 'No tournament running'"

remote-fetch:
    rsync -av {{_vps}}:{{_vps_dir}}/replays_remote/ replays_remote/

ci *args:
    python scripts/remote_ci.py {{args}}

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
