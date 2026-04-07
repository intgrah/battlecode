#!/usr/bin/env fish

if test (count $argv) -lt 2
    echo "Usage: ci.fish BOT_A BOT_B" >&2
    exit 1
end

set BOT_A $argv[1]
set BOT_B $argv[2]

set -l dir replays_ci/(date +%Y%m%d_%H%M%S)
mkdir -p $dir

set maps corridors settlement gaussian pixel_forest starry_night wasteland_oasis

for map in $maps
    fish scripts/remote_match.fish bc $BOT_A $BOT_B -m $map -o $dir/{$map}_p1.replay26 &
    fish scripts/remote_match.fish chi $BOT_B $BOT_A -m $map -o $dir/{$map}_p2.replay26 &
end

wait
