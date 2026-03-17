#!/bin/bash
# Headless gameplay test harness for Penta Dragon DX Remake
# Runs mGBA with Lua scripting, captures screenshots, verifies gameplay
# Usage: ./scripts/test_headless.sh [rom_path]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ROM="${1:-$PROJECT_DIR/rom/working/penta_dragon_dx.gbc}"
TMP="$PROJECT_DIR/tmp"
LUA_SCRIPT="$SCRIPT_DIR/test_harness.lua"

mkdir -p "$TMP"

if [ ! -f "$ROM" ]; then
    echo "FAIL: ROM not found: $ROM"
    exit 1
fi

# Pre-check: verify no bank span warnings in map file
MAP_FILE="${ROM%.gbc}.map"
if [ -f "$MAP_FILE" ]; then
    CODE_SIZE=$(grep "^_CODE" "$MAP_FILE" | grep -oP '\d+(?=\. bytes)')
    if [ -n "$CODE_SIZE" ] && [ "$CODE_SIZE" -gt 32000 ]; then
        echo "WARNING: _CODE size is ${CODE_SIZE} bytes (bank 1 limit ~32000)"
        echo "Risk of bank span crash!"
    fi
fi

# Clean previous results
rm -f "$TMP"/h_*.png "$TMP/test_results.txt"

# Run headless test
echo "Running headless test on $(basename "$ROM")..."
unset DISPLAY WAYLAND_DISPLAY
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
timeout 30 xvfb-run -a mgba-qt "$ROM" \
  --script "$LUA_SCRIPT" -l 0 2>/dev/null || true

# Kill stray Xvfb
pkill -9 -f 'Xvfb :' 2>/dev/null || true

# Verify screenshots exist
PASS=0
FAIL=0
TOTAL=0

check_screenshot() {
    local name="$1"
    local file="$TMP/h_${name}.png"
    local min_size="${2:-500}"
    TOTAL=$((TOTAL + 1))

    if [ ! -f "$file" ]; then
        echo "FAIL: $name - screenshot not created"
        FAIL=$((FAIL + 1))
        return 1
    fi

    local size=$(stat -c%s "$file")
    if [ "$size" -lt "$min_size" ]; then
        echo "FAIL: $name - file too small (${size}B < ${min_size}B), likely blank"
        FAIL=$((FAIL + 1))
        return 1
    fi

    echo "PASS: $name (${size}B)"
    PASS=$((PASS + 1))
    return 0
}

echo ""
echo "=== Test Results ==="
check_screenshot "title" 800
check_screenshot "gameplay" 2000
check_screenshot "scrolled" 2000
check_screenshot "left" 2000
check_screenshot "up" 2000
check_screenshot "shoot" 2000
check_screenshot "dragon" 2000
check_screenshot "combat" 2000
check_screenshot "menu" 1500

echo ""
echo "Results: $PASS/$TOTAL passed, $FAIL failed"

# Save results
echo "PASS=$PASS FAIL=$FAIL TOTAL=$TOTAL" > "$TMP/test_results.txt"
echo "ROM=$(basename "$ROM")" >> "$TMP/test_results.txt"
date >> "$TMP/test_results.txt"

if [ "$FAIL" -gt 0 ]; then
    echo "OVERALL: FAIL"
    exit 1
else
    echo "OVERALL: PASS"
    exit 0
fi
