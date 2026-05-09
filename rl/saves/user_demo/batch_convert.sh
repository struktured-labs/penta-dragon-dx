#!/bin/bash
# Batch-convert all mgba .ss files in user_demo/ to PyBoy save states.
# Output: rl/saves/user_demo/converted/<basename>.state

set -e
cd /home/struktured/projects/penta-dragon-dx-claude
source rl/.venv/bin/activate

ROM="rom/Penta Dragon (J) [A-fix].gb"
SRC=rl/saves/user_demo
OUT=rl/saves/user_demo/converted
TMP=tmp/mgba_dump
mkdir -p "$OUT" "$TMP"

# Settle frames: 0 — some states hang on PyBoy tick after inject. Trainer
# will tick naturally during step(), so we just save the immediate post-inject state.
SETTLE=0

for ss in "$SRC"/*.ss; do
    base=$(basename "$ss" .ss)
    prefix="$TMP/$base"
    state_out="$OUT/$base.state"

    if [ -f "$state_out" ]; then
        echo "  skip $base (already converted)"
        continue
    fi

    # Step 1: dump memory regions via mgba+Lua
    STATE_PATH="$prefix" QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
        timeout 15 xvfb-run -a mgba-qt "$ROM" -t "$ss" \
        --script "$SRC/dump_state_to_bin.lua" -l 0 > /dev/null 2>&1 || true
    if [ ! -f "${prefix}_wram.bin" ]; then
        echo "  FAIL dump $base"
        continue
    fi

    # Step 2: inject into PyBoy and save (60s per-state timeout — some hang)
    timeout 60 python "$SRC/inject_to_pyboy.py" "$prefix" "$state_out" "$SETTLE" 2>&1 | tail -2 | sed "s/^/  [$base] /"
    if [ ! -f "$state_out" ]; then
        echo "  [$base] FAIL or TIMEOUT, skipping"
    fi

    # Cleanup
    rm -f "${prefix}_"*.bin "${prefix}_meta.txt"
done

echo ""
echo "=== Done: converted states in $OUT ==="
ls -la "$OUT/"
