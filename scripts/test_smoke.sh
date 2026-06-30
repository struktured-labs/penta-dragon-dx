#!/usr/bin/env bash
# Quintra smoke test — runs the ROM under headless mGBA + a Lua harness
# that takes screenshots at each major screen transition.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ROM="${1:-$PROJECT_DIR/rom/working/quintra.gbc}"
OUT_DIR="${QUINTRA_OUT_DIR:-$PROJECT_DIR/tmp/smoketest}"

if [ ! -f "$ROM" ]; then
    echo "FAIL: ROM not found: $ROM"
    exit 1
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/h_*.png

echo "[smoke] running $ROM under headless mGBA..."
unset DISPLAY WAYLAND_DISPLAY
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
    QUINTRA_OUT_DIR="$OUT_DIR" \
    timeout 30 xvfb-run -a mgba-qt "$ROM" \
        --script "$SCRIPT_DIR/quintra_smoketest.lua" \
        -l 0 2>&1 | grep -v 'Window\|Qt\|libpng' || true

pkill -9 -f 'Xvfb :' 2>/dev/null || true

PASS=0 FAIL=0 TOTAL=0
check() {
    local name="$1" min="${2:-300}"
    local f="$OUT_DIR/h_${name}.png"
    TOTAL=$((TOTAL+1))
    if [ ! -f "$f" ]; then
        echo "  FAIL $name (file missing)"; FAIL=$((FAIL+1)); return
    fi
    local sz=$(stat -c%s "$f")
    if [ "$sz" -lt "$min" ]; then
        echo "  FAIL $name (file ${sz}B < ${min}B)"; FAIL=$((FAIL+1)); return
    fi
    echo "  PASS $name (${sz}B)"; PASS=$((PASS+1))
}

echo "[smoke] results in $OUT_DIR/"
check 01_title              400
check 02_class_select       400
check 03_room_enter         400
check 04_room_left          400
check 05_room_down          400
check 06_room_right         400
check 07_room_after_wall_push 400
check 08_back_to_title      400

echo "[smoke] $PASS/$TOTAL passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then exit 1; fi
exit 0
