#!/bin/bash
# Launch mgba-qt for human-play RECORDING with play_record_curriculum.lua.
# Captures JSONL trajectory + auto-saves curriculum states on kills/arena entry.
# Usage: launch_mgba_record.sh [rec_label]
#   rec_label: optional, defaults to a timestamp; appended to expert_human_<label>.jsonl
set -e

PROJECT_DIR="/home/struktured/projects/penta-dragon-dx-claude"
ROM="$PROJECT_DIR/rom/Penta Dragon (J) [A-fix].gb"
SCRIPT="$PROJECT_DIR/scripts/probes/play_record_curriculum.lua"
LABEL="${1:-$(date +%Y%m%d_%H%M%S)}"
REC_PATH="$PROJECT_DIR/rl/bc_data/expert_human_${LABEL}.jsonl"

if [ ! -f "$ROM" ]; then echo "ROM not found: $ROM"; exit 1; fi
if [ ! -f "$SCRIPT" ]; then echo "Script not found: $SCRIPT"; exit 1; fi
GUARDED_MGBA="$PROJECT_DIR/scripts/mgba-qt-singleflight"

QTINI="$HOME/.config/mgba/qt.ini"
if [ -f "$QTINI" ]; then
    sed -i 's/^displayDriver=.*/displayDriver=1/' "$QTINI"
fi

mkdir -p "$PROJECT_DIR/rl/bc_data" "$PROJECT_DIR/rl/saves/curriculum"

echo "ROM:      $(basename "$ROM")"
echo "Script:   $(basename "$SCRIPT")"
echo "REC_PATH: $REC_PATH"
echo
echo "*** PLAY INSTRUCTIONS ***"
echo "  - mgba auto-navigates the title (~8 sec)"
echo "  - When 'YOUR TURN' appears in mgba console, play normally"
echo "  - mgba keys: arrows=D-pad, X=A (fire), Z=B, Enter=Start, Backspace=Select"
echo "  - Curriculum hooks auto-save .ss states on kills and arena entry"
echo "  - Quit mgba (Ctrl+Q) when done; JSONL is flushed on shutdown"
echo

REC_PATH="$REC_PATH" \
QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  "$GUARDED_MGBA" "$ROM" --script "$SCRIPT"

echo "Recording stopped. JSONL: $REC_PATH"
