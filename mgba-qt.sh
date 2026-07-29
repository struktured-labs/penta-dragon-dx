#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DISPLAY=:0 \
QT_QPA_PLATFORM=xcb \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
exec "$PROJECT_DIR/scripts/mgba-qt-singleflight" "$@"
