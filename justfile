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
