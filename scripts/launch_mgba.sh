#!/usr/bin/env bash
# Launch mgba-qt for human play on NVIDIA + KDE Wayland
# Usage: launch_mgba.sh [rom_path]
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ROM="${1:-rom/working/penta_dragon_dx_FIXED.gb}"
GUARDED_MGBA="$PROJECT_DIR/scripts/mgba-qt-singleflight"
if [[ "$#" -gt 0 ]]; then
    shift
fi

# Resolve relative paths against project dir
if [[ "$ROM" != /* ]]; then
    ROM="$PROJECT_DIR/$ROM"
fi

if [ ! -f "$ROM" ]; then
    echo "ROM not found: $ROM"
    exit 1
fi

# Ensure OpenGL display driver in config
QTINI="$HOME/.config/mgba/qt.ini"
if [ -f "$QTINI" ]; then
    sed -i 's/^displayDriver=.*/displayDriver=1/' "$QTINI"
fi

# Stay alive as the emulator's guardian. If this launcher is interrupted, the
# wrapper's parent-death signal terminates the exact emulator it owns.
echo "Starting guarded mGBA (a concurrent emulator will fail closed)..."
DISPLAY=:0 \
QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  exec "$GUARDED_MGBA" "$ROM" "$@"
