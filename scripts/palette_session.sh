#!/bin/bash
# palette_session.sh — start/stop a live palette-editing session
#
#   ./palette_session.sh start [rom_path]
#   ./palette_session.sh stop
#   ./palette_session.sh status
#
# Starts:
#   1. mGBA-qt loading the ROM (default: penta_dragon_dx_v301.gb) with the
#      live_palettes.lua script attached so it reacts to colour changes.
#   2. Python HTTP server at localhost:8077 serving the colour-picker UI.
#   3. Browser pointed at the UI (best-effort: tries xdg-open / open).
#
# Stops:
#   - Kills mgba-qt and the live_palette_editor.py process.

set -e

PROJECT_DIR="/home/struktured/projects/penta-dragon-dx-claude"
ROM_DEFAULT="rom/working/penta_dragon_dx_v301.gb"
LUA_SCRIPT="scripts/lua/live_palettes.lua"
EDITOR_SCRIPT="scripts/live_palette_editor.py"
PORT=8077
LOG_DIR="$PROJECT_DIR/tmp/palette_session"
EDITOR_PID_FILE="$LOG_DIR/editor.pid"
EDITOR_LOG="$LOG_DIR/editor.log"
MGBA_LOG="$LOG_DIR/mgba.log"

cmd="${1:-start}"

mkdir -p "$LOG_DIR"

editor_running() {
    if [ -f "$EDITOR_PID_FILE" ]; then
        pid=$(cat "$EDITOR_PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    pgrep -f "live_palette_editor.py" >/dev/null 2>&1
}

mgba_running() {
    pgrep -f "mgba-qt.*live_palettes.lua" >/dev/null 2>&1
}

stop_all() {
    pkill -9 -f "live_palette_editor.py" 2>/dev/null || true
    pkill -9 -f "mgba-qt" 2>/dev/null || true
    rm -f "$EDITOR_PID_FILE"
    sleep 1
}

status() {
    if editor_running; then
        echo "editor: RUNNING (port $PORT)"
    else
        echo "editor: not running"
    fi
    if mgba_running; then
        echo "mgba:   RUNNING (with live_palettes.lua)"
    else
        echo "mgba:   not running"
    fi
}

case "$cmd" in
    start)
        rom="${2:-$ROM_DEFAULT}"
        if [[ "$rom" != /* ]]; then
            rom="$PROJECT_DIR/$rom"
        fi
        if [ ! -f "$rom" ]; then
            echo "ROM not found: $rom"
            exit 1
        fi

        echo "Starting palette-editor session..."
        # Clean slate
        stop_all

        # 1. Python editor in background
        cd "$PROJECT_DIR"
        nohup python3 "$EDITOR_SCRIPT" > "$EDITOR_LOG" 2>&1 &
        editor_pid=$!
        echo "$editor_pid" > "$EDITOR_PID_FILE"
        echo "  editor:  PID $editor_pid → log $EDITOR_LOG"

        # Wait briefly for server to bind port
        for _ in 1 2 3 4 5; do
            if ss -lnt 2>/dev/null | grep -q ":$PORT\b" || \
               netstat -lnt 2>/dev/null | grep -q ":$PORT\b"; then
                break
            fi
            sleep 0.3
        done

        # 2. Ensure OpenGL driver setting (mirrors launch_mgba.sh)
        qtini="$HOME/.config/mgba/qt.ini"
        if [ -f "$qtini" ]; then
            sed -i 's/^displayDriver=.*/displayDriver=1/' "$qtini"
        fi

        # 3. mGBA with the live Lua script.
        # Pick platform: xcb if DISPLAY is set (XWayland or X11 session,
        # works with NVIDIA via __GLX_VENDOR_LIBRARY_NAME), else wayland.
        # The Claude Code shell typically has only WAYLAND_DISPLAY, so
        # default to wayland mode for compatibility with that path.
        if [ -n "$DISPLAY" ]; then
            QT_QPA_PLATFORM=xcb \
            __GLX_VENDOR_LIBRARY_NAME=nvidia \
            VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json \
                nohup mgba-qt "$rom" --script "$LUA_SCRIPT" \
                > "$MGBA_LOG" 2>&1 &
            mgba_platform="xcb"
        elif [ -n "$WAYLAND_DISPLAY" ]; then
            QT_QPA_PLATFORM=wayland \
            XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
            WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
                nohup mgba-qt "$rom" --script "$LUA_SCRIPT" \
                > "$MGBA_LOG" 2>&1 &
            mgba_platform="wayland"
        else
            echo "  mgba:    no DISPLAY or WAYLAND_DISPLAY — cannot launch GUI"
            mgba_pid=""
        fi
        if [ -n "${mgba_platform:-}" ]; then
            mgba_pid=$!
            echo "  mgba:    PID $mgba_pid platform=$mgba_platform → log $MGBA_LOG (ROM: $(basename "$rom"))"
        fi

        # 4. Best-effort browser open
        sleep 1
        url="http://localhost:$PORT"
        opened=false
        for opener in xdg-open open; do
            if command -v "$opener" >/dev/null 2>&1; then
                "$opener" "$url" >/dev/null 2>&1 &
                opened=true
                break
            fi
        done
        if $opened; then
            echo "  browser: opened $url"
        else
            echo "  browser: open this URL yourself → $url"
        fi

        sleep 2
        echo
        status
        echo
        echo "To stop:  $0 stop"
        ;;
    stop)
        echo "Stopping palette-editor session..."
        stop_all
        status
        ;;
    status)
        status
        ;;
    *)
        echo "usage: $0 {start [rom_path] | stop | status}"
        exit 1
        ;;
esac
