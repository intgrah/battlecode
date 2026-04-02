default_map := `ls maps/*.map26 | shuf -n1`
[private]
_analysis := "uv run replay-analyze"

run a b map=default_map:
    cambc run {{ a }} {{ b }} {{ map }}

v replay="replay.replay26": vv
    lib/visualiser/viewer/target/release/visualiser-viewer {{ replay }}

vv:
    cargo build --release --manifest-path lib/visualiser/viewer/Cargo.toml

w replay="replay.replay26":
    cambc watch {{ replay }}

flow replay="replay.replay26":
    python scripts/flow_visualize.py {{ replay }}

watch a b map=default_map:
    cambc run {{ a }} {{ b }} {{ map }} --watch

analyze replay="replay.replay26" *args="":
    {{ _analysis }} {{ replay }} {{ args }}

stats replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s summary

economy replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s economy

network replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s network

spatial replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s spatial

defense replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s defense

combat replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s combat

bots replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s bots

compare replay="replay.replay26":
    {{ _analysis }} {{ replay }} -s compare

full replay="replay.replay26":
    python scripts/replay_full.py {{ replay }}

debug replay="replay.replay26" *args="":
    python scripts/replay_debug.py {{ replay }} {{ args }}

debug-team replay="replay.replay26" team="A" *args="":
    python scripts/replay_debug.py {{ replay }} --team {{ team }} {{ args }}

debug-entity replay="replay.replay26" entity="" *args="":
    python scripts/replay_debug.py {{ replay }} --entity {{ entity }} {{ args }}

explain replay="replay.replay26" *args="":
    python scripts/replay_debug.py {{ replay }} --min-priority 40 --no-map {{ args }}

map *args:
    python scripts/replay_map.py {{ args }}

download match_id:
    python scripts/download_match.py {{ match_id }}

match a b map=default_map:
    -cambc run {{ a }} {{ b }} {{ map }} 2>&1 | grep -v "^Completed turn\|^Fatal\|^Python runtime\|^Update available\|^$"
    {{ _analysis }} replay.replay26 -s summary

proto:
    protoc --python_out=lib/proto/src/proto --pyi_out=lib/proto/src/proto --proto_path=lib/proto/src/proto lib/proto/src/proto/cambc.proto
    ruff check --fix lib/proto/
    ruff format lib/proto/

lint:
    ruff check --fix bots/ scripts/

ty:
    #!/usr/bin/env bash
    ty check
    for d in bots/*/pyproject.toml; do
        d=$(dirname "$d")
        ty check --project "$d" "$d"
    done

fmt:
    ruff format bots/ scripts/

f: ty lint fmt

tournament *args:
    python scripts/tournament.py {{ args }}

build bot:
    #!/usr/bin/env bash
    rm -rf build/bot
    cp -r "bots/{{ bot }}" build/bot
    # Vendor workspace dependencies
    for dep in lib/*/src/; do
        name=$(basename "$(dirname "$dep")")
        src="lib/$name/src/$name"
        if [ -d "$src" ] && grep -q "\"$name\"" "bots/{{ bot }}/pyproject.toml" 2>/dev/null; then
            cp -r "$src" "build/bot/$name"
        fi
    done
    find build/bot -type d -name __pycache__ -exec rm -rf {} +
    find build/bot -type f \( -name "*.pyi" -o -name pyproject.toml \) -delete
    echo "Built {{ bot }} -> build/bot"

submit bot: (build bot)
    cambc submit build/bot

challenge bot opponent:
    #!/usr/bin/env bash
    ranked="${RANKED:-v21}"
    find "bots/{{ bot }}" -type d -name __pycache__ -exec rm -rf {} +
    echo "Submitting {{ bot }}"
    cambc submit "bots/{{ bot }}"
    echo "Challenging {{ opponent }}"
    cambc unrated "{{ opponent }}"
    echo "Restoring $ranked"
    cambc submit "bots/$ranked"

online *args:
    python scripts/online.py {{ args }}

status:
    cambc status

[private]
_vps := "chi"
[private]
_vps_dir := "~/battlecode"
[private]
_vps_cambc := "~/battlecode/.venv/bin/cambc"

sync:
    rsync -av --delete bots/ {{ _vps }}:{{ _vps_dir }}/bots/
    rsync -av maps/ {{ _vps }}:{{ _vps_dir }}/maps/
    rsync -av scripts/ {{ _vps }}:{{ _vps_dir }}/scripts/
    rsync -av proto/ {{ _vps }}:{{ _vps_dir }}/proto/

remote-run a b map=default_map:
    just sync
    ssh {{ _vps }} "cd {{ _vps_dir }} && {{ _vps_cambc }} run bots/{{ a }} bots/{{ b }} {{ map }} --replay replay.replay26"
    scp {{ _vps }}:{{ _vps_dir }}/replay.replay26 replay_remote.replay26

remote-match a b map=default_map:
    just sync
    ssh {{ _vps }} "cd {{ _vps_dir }} && {{ _vps_cambc }} run bots/{{ a }} bots/{{ b }} {{ map }} --replay replay.replay26 2>&1 | grep -v '^Completed turn\|^Fatal\|^Python runtime\|^Update available\|^$$'"
    ssh {{ _vps }} "cd {{ _vps_dir }} && .venv/bin/python -m scripts.analysis replay.replay26 -s summary"
    scp {{ _vps }}:{{ _vps_dir }}/replay.replay26 replay_remote.replay26

remote-tournament *args:
    just sync
    ssh {{ _vps }} "cd {{ _vps_dir }} && nohup .venv/bin/python scripts/tournament.py {{ args }} > tournament.log 2>&1 &"
    @echo "Tournament running on VPS. Check with: just remote-status"

remote-status:
    ssh {{ _vps }} "tail -20 {{ _vps_dir }}/tournament.log 2>/dev/null || echo 'No tournament running'"

remote-fetch:
    rsync -av {{ _vps }}:{{ _vps_dir }}/replays_remote/ replays_remote/

ci *args:
    python scripts/remote_ci.py {{ args }}

docs:
    #!/usr/bin/env bash
    cd docs
    curl -s https://docs.battlecode.cam/llms.txt -o llms.txt
    grep -oP 'https://docs\.battlecode\.cam/\S+\.md' llms.txt | while read -r url; do
        path="${url#https://docs.battlecode.cam/}"
        mkdir -p "$(dirname "$path")"
        curl -s "$url" -o "$path"
        echo "$path"
    done
