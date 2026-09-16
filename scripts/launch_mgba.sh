#!/usr/bin/env bash
# Launch mgba-qt for human play on NVIDIA + KDE Wayland
# Usage: launch_mgba.sh [rom_path] [mGBA arguments...]
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
GUARDED_MGBA="$PROJECT_DIR/scripts/mgba-qt-singleflight"
ROM_ARGUMENT=""
if [[ "$#" -gt 0 && "$1" != -* ]]; then
    ROM_ARGUMENT="$1"
    shift
fi

# Ensure OpenGL display driver in config
QTINI="$HOME/.config/mgba/qt.ini"
if [ -f "$QTINI" ]; then
    sed -i 's/^displayDriver=.*/displayDriver=1/' "$QTINI"
fi

# Stay alive as the emulator's guardian. If this launcher is interrupted, the
# wrapper's parent-death signal terminates the exact emulator it owns.
echo "Starting guarded mGBA (a concurrent emulator will fail closed)..."
PREPARE_ARGUMENTS=(--project-root "$PROJECT_DIR")
if [[ -n "$ROM_ARGUMENT" ]]; then
    PREPARE_ARGUMENTS+=(--rom "$ROM_ARGUMENT")
fi
for argument in "$@"; do
    PREPARE_ARGUMENTS+=("--extra-arg=$argument")
done
ROM="$(/usr/bin/python3 "$PROJECT_DIR/scripts/prepare_headed_launch.py" "${PREPARE_ARGUMENTS[@]}")"
DISPLAY=:0 \
QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
  exec "$GUARDED_MGBA" "$ROM" "$@"
