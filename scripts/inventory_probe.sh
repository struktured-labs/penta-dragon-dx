#!/bin/bash
# Run mgba with inventory_probe.lua attached. Play and pick up/use items.
set -e
PROJ=/home/struktured/projects/penta-dragon-dx-claude
ROM="$PROJ/rom/Penta Dragon (J) [A-fix].gb"
SCRIPT="$PROJ/scripts/probes/inventory_probe.lua"

pkill -9 -f mgba-qt 2>/dev/null || true
sleep 1
QTINI="$HOME/.config/mgba/qt.ini"
[ -f "$QTINI" ] && sed -i 's/^displayDriver=.*/displayDriver=1/' "$QTINI"

echo "Inventory probe: pick up items, use items, vary inventory."
echo "WRAM dumps to rl/bc_data/inventory_wram.jsonl."
echo ""

QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  mgba-qt "$ROM" --script "$SCRIPT"

echo ""
echo "Probe done. Lines:"
wc -l "$PROJ/rl/bc_data/inventory_wram.jsonl"
