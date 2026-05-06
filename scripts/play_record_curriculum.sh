#!/bin/bash
# Launch mgba-qt for HUMAN PLAY with curriculum save-state hooks of (state, action) pairs.
# Output: rl/bc_data/expert_human_curriculum.jsonl (overwrites; rename to add to dataset)
#
# Usage: ./scripts/play_record.sh [rom_path] [out_path]
#   default ROM:    rom/Penta Dragon (J) [A-fix].gb
#   default OUT:    rl/bc_data/expert_human_curriculum.jsonl
#
# Controls (mgba default):
#   Arrow keys = D-pad
#   X = A button (fire projectile)
#   Z = B button
#   Enter = Start
#   Backspace = Select
#
# Title menu auto-navs in ~8 seconds. After that, you control the game.
# Recording starts when you reach gameplay (FFC1=1) and ends when you close mgba.
#
# Tips for good demos:
# - Play at 1× speed (CGB double-speed BREAKS the game per project memory)
# - 5-10 minutes is plenty; aim for several mini-boss kills
# - Vary movement (don't just spin) — cover diverse states
# - It's OK to die occasionally; the kill frames matter most

set -e

PROJECT_DIR="/home/struktured/projects/penta-dragon-dx-claude"
ROM="${1:-rom/Penta Dragon (J) [A-fix].gb}"
OUT="${2:-rl/bc_data/expert_human_curriculum.jsonl}"
SCRIPT="$PROJECT_DIR/scripts/probes/play_record_curriculum.lua"

# Resolve paths relative to project
[[ "$ROM" != /* ]] && ROM="$PROJECT_DIR/$ROM"
[[ "$OUT" != /* ]] && OUT="$PROJECT_DIR/$OUT"

if [ ! -f "$ROM" ]; then echo "ROM not found: $ROM"; exit 1; fi

# Kill existing mgba
pkill -9 -f 'mgba-qt' 2>/dev/null || true
sleep 1

# Ensure OpenGL display driver
QTINI="$HOME/.config/mgba/qt.ini"
[ -f "$QTINI" ] && sed -i 's/^displayDriver=.*/displayDriver=1/' "$QTINI"

mkdir -p "$(dirname "$OUT")"
echo "Recording to: $OUT"
echo "ROM: $ROM"
echo ""
echo "Controls: arrows=D-pad, X=A (fire), Z=B, Enter=Start, Backspace=Select"
echo "Title auto-navs ~8s, then YOUR TURN. Close mgba window to stop recording."
echo ""

REC_PATH="$OUT" \
QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  mgba-qt "$ROM" --script "$SCRIPT"

echo ""
echo "Recording stopped. Lines written:"
wc -l "$OUT"
