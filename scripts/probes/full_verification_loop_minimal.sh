#!/bin/bash
# Minimal verification loop — just the essentials
set -o pipefail

ROM="rom/working/penta_dragon_dx_teleport.gb"
LOGDIR="/tmp/penta_verify_batch_$(date +%s)"
mkdir -p "$LOGDIR"
cd /home/struktured/projects/penta-dragon-dx-claude

exec > "$LOGDIR/full.log" 2>&1
echo "=== PENTA DRAGON DX — FULL VERIFICATION LOOP ==="
echo "Log dir: $LOGDIR"
date

TARGET=10
streak=0

for attempt in $(seq 1 100); do
    start=$(date +%s)
    python3 scripts/build_v301_teleport.py > "$LOGDIR/build_$attempt.log" 2>&1

    # Run all 8 tests in strict sequence
    all_ok=true

    # 1 - PyBoy
    timeout 180 python3 scripts/probes/verify_title_animation_frames.py "$ROM" > "$LOGDIR/t1_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: title_animation $attempt"; }
    # 2 - PyBoy
    timeout 300 python3 scripts/probes/verify_flash_attribution.py "$ROM" > "$LOGDIR/t2_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: flash $attempt"; }
    # 3 - mgba
    timeout 120 python3 scripts/probes/verify_title_color.py "$ROM" > "$LOGDIR/t3_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: title_color $attempt"; }
    # 4 - mgba
    timeout 180 python3 scripts/probes/verify_gameplay_palette.py "$ROM" > "$LOGDIR/t4_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: gameplay $attempt"; }
    # 5 - mgba
    timeout 240 python3 scripts/probes/verify_miniboss_color.py "$ROM" > "$LOGDIR/t5_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: miniboss $attempt"; }
    # 6 - mgba
    timeout 240 python3 scripts/probes/verify_scroll_tearing.py "$ROM" > "$LOGDIR/t6_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: scroll $attempt"; }
    # 7 - mgba
    timeout 240 python3 scripts/probes/verify_phantom_d887.py "$ROM" > "$LOGDIR/t7_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: d887 $attempt"; }
    # 8 - PyBoy
    timeout 600 python3 scripts/probes/verify_boss_arena_palettes.py "$ROM" --output "$LOGDIR/bp_$attempt" > "$LOGDIR/t8_$attempt.log" 2>&1 || { all_ok=false; echo "FAIL: boss $attempt"; }

    elapsed=$(( $(date +%s) - start ))

    if $all_ok; then
        streak=$((streak + 1))
        echo "ATTEMPT $attempt: ALL 8 PASS (${elapsed}s) streak=$streak/$TARGET"
        if [ $streak -ge $TARGET ]; then
            echo "=== VERIFICATION COMPLETE ==="
            echo "All 8 tests passed $TARGET times consecutively"
            echo "--- Build output ---"
            cat "$LOGDIR/build_$attempt.log"
            echo ""
            for i in 3 4 5 6 7 1 2 8; do
                echo "--- test $i ---"
                tail -3 "$LOGDIR/t${i}_$attempt.log" 2>/dev/null
            done
            exit 0
        fi
    else
        echo "ATTEMPT $attempt: FAIL (${elapsed}s) streak RESET"
        streak=0
    fi
done

echo "FAILED after 100 attempts"
exit 1
