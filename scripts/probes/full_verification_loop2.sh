#!/bin/bash
# Full 10x verification loop — meant to run standalone, logs all output
# Usage: nohup bash scripts/probes/full_verification_loop2.sh > /tmp/penta_loop_full.log 2>&1 &
# Then: tail -f /tmp/penta_loop_full.log

ROM="rom/working/penta_dragon_dx_teleport.gb"
LOGDIR="/tmp/penta_verify_10x_$(date +%s)"
mkdir -p "$LOGDIR"

echo "=== PENTA DRAGON DX — FULL VERIFICATION LOOP ==="
echo "ROM: $ROM"
echo "Log dir: $LOGDIR"
echo "Started: $(date)"
echo ""

cd /home/struktured/projects/penta-dragon-dx-claude

TARGET_PASSES=10
pass_count=0

# Pre-build
python3 scripts/build_v301_teleport.py > "$LOGDIR/build_pre.log" 2>&1 && echo "Pre-build OK"
echo ""

for attempt in $(seq 1 100); do
    ts_start=$(date +%s)
    echo "=== Attempt $attempt ==="

    python3 scripts/build_v301_teleport.py > "$LOGDIR/build_$attempt.log" 2>&1
    if [ ! -f "$ROM" ]; then
        echo "BUILD FAILED"
        cat "$LOGDIR/build_$attempt.log"
        exit 1
    fi

    all_ok=true

    # 1
    echo -n "  verify_title_animation_frames ... "
    timeout 200 python3 scripts/probes/verify_title_animation_frames.py "$ROM" > "$LOGDIR/title_frames_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 2
    echo -n "  verify_flash_attribution ... "
    timeout 350 python3 scripts/probes/verify_flash_attribution.py "$ROM" > "$LOGDIR/flash_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 3
    echo -n "  verify_title_color ... "
    timeout 120 python3 scripts/probes/verify_title_color.py "$ROM" > "$LOGDIR/title_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 4
    echo -n "  verify_gameplay_palette ... "
    timeout 200 python3 scripts/probes/verify_gameplay_palette.py "$ROM" > "$LOGDIR/gameplay_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 5
    echo -n "  verify_miniboss_color ... "
    timeout 300 python3 scripts/probes/verify_miniboss_color.py "$ROM" > "$LOGDIR/miniboss_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 6
    echo -n "  verify_scroll_tearing ... "
    timeout 300 python3 scripts/probes/verify_scroll_tearing.py "$ROM" > "$LOGDIR/scroll_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 7
    echo -n "  verify_phantom_d887 ... "
    timeout 300 python3 scripts/probes/verify_phantom_d887.py "$ROM" > "$LOGDIR/d887_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    # 8
    echo -n "  verify_boss_arena_palettes ... "
    timeout 600 python3 scripts/probes/verify_boss_arena_palettes.py "$ROM" --output "$LOGDIR/boss_palettes_$attempt" > "$LOGDIR/boss_$attempt.log" 2>&1
    rc=$?; if [ $rc -eq 0 ]; then echo "PASS"; else echo "FAIL($rc)"; all_ok=false; fi

    elapsed=$(( $(date +%s) - ts_start ))
    echo ""

    if $all_ok; then
        pass_count=$((pass_count + 1))
        echo "ATTEMPT $attempt: ALL 8 PASS (${elapsed}s) — streak: $pass_count/$TARGET_PASSES"
        echo ""

        if [ $pass_count -ge $TARGET_PASSES ]; then
            echo ""
            echo "============================================"
            echo "  VERIFICATION COMPLETE"
            echo "  $TARGET_PASSES CONSECUTIVE PASSES"
            echo "============================================"
            echo "Finished: $(date)"
            echo ""
            echo "=== BUILD OUTPUT ==="
            cat "$LOGDIR/build_$attempt.log"
            echo ""
            echo "=== FINAL TEST RESULTS ==="
            for tag in title_frames flash title gameplay miniboss scroll d887 boss; do
                echo ""
                echo "--- $tag ---"
                tail -5 "$LOGDIR/${tag}_$attempt.log" 2>/dev/null
            done
            echo ""
            echo "Log directory: $LOGDIR"
            exit 0
        fi
    else
        pass_count=0
        echo "ATTEMPT $attempt: FAILURE (${elapsed}s) — streak reset"
        echo ""
    fi
done

echo "FAILED after 100 attempts"
exit 1
