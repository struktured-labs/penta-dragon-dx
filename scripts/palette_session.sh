#!/bin/bash
# palette_session.sh — start/stop a live palette-editing session
#
#   ./palette_session.sh start [rom_path]
#   ./palette_session.sh stop
#   ./palette_session.sh status
#
# Starts:
#   1. mGBA-qt loading the release-candidate FIXED.gb with live_palettes.lua.
#      Browser scene changes load curated emulator states; the retired
#      SELECT+START teleport is never enabled.
#   2. Python HTTP server at localhost:8077 serving the colour-picker UI.
#   3. Browser pointed at the UI (best-effort: tries xdg-open / open).
#
# Stops:
#   - Stops only the mGBA/editor processes started by this script.

set -e

PROJECT_DIR="/home/struktured/projects/penta-dragon-dx-claude"
ROM_DEFAULT="rom/working/penta_dragon_dx_FIXED.gb"
LUA_SCRIPT="scripts/lua/live_palettes.lua"
EDITOR_SCRIPT="scripts/live_palette_editor.py"
STAGE_STATE_GENERATOR="scripts/diagnostics/generate_stream_stage_states.py"
BOSS_STATE_GENERATOR="scripts/diagnostics/generate_stream_boss_states.py"
STORY_STATE_GENERATOR="scripts/diagnostics/generate_stream_story_states.py"
PORT=8077
LOG_DIR="$PROJECT_DIR/tmp/palette_session"
EDITOR_PID_FILE="$LOG_DIR/editor.pid"
MGBA_PID_FILE="$LOG_DIR/mgba.pid"
EDITOR_LOG="$LOG_DIR/editor.log"

cmd="${1:-start}"

mkdir -p "$LOG_DIR"

editor_running() {
    if [ -f "$EDITOR_PID_FILE" ]; then
        pid=$(cat "$EDITOR_PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            case "$(ps -p "$pid" -o args= 2>/dev/null)" in
                *live_palette_editor.py*) return 0 ;;
            esac
        fi
    fi
    return 1
}

mgba_running() {
    if [ -f "$MGBA_PID_FILE" ]; then
        pid=$(cat "$MGBA_PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            case "$(ps -p "$pid" -o args= 2>/dev/null)" in
                *mgba-qt*live_palettes.lua*) return 0 ;;
            esac
        fi
    fi
    return 1
}

stop_owned_process() {
    pid_file="$1"
    expected="$2"
    if [ ! -f "$pid_file" ]; then
        return
    fi
    pid=$(cat "$pid_file" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        args=$(ps -p "$pid" -o args= 2>/dev/null || true)
        case "$args" in
            *"$expected"*)
                kill "$pid" 2>/dev/null || true
                ;;
        esac
    fi
    rm -f "$pid_file"
}

stop_all() {
    stop_owned_process "$MGBA_PID_FILE" "live_palettes.lua"
    stop_owned_process "$EDITOR_PID_FILE" "live_palette_editor.py"
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

        # Stop this launcher's prior processes before touching cached states.
        # An old mGBA must not load a state while its replacement is being
        # regenerated.
        stop_all

        echo "Starting palette-editor session..."
        # Keep this script alive as the exact parent/guardian for both owned
        # processes. Closing or interrupting it cleans up the session.
        trap stop_all EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        echo "  states:  checking ROM-matched Stage 2-7 scene states"
        python3 "$PROJECT_DIR/$STAGE_STATE_GENERATOR" "$rom"
        echo "  states:  checking release-ROM boss-arena scene states"
        python3 "$PROJECT_DIR/$BOSS_STATE_GENERATOR" "$rom"
        echo "  states:  checking 12 intro/final/ending states"
        python3 "$PROJECT_DIR/$STORY_STATE_GENERATOR" "$rom"
        # 1. Python editor in background
        cd "$PROJECT_DIR"
        nohup python3 "$EDITOR_SCRIPT" --bind 127.0.0.1 --port "$PORT" \
            > "$EDITOR_LOG" 2>&1 &
        editor_pid=$!
        echo "$editor_pid" > "$EDITOR_PID_FILE"
        echo "  editor:  PID $editor_pid → log $EDITOR_LOG"

        # Wait briefly for server to bind port
        port_ready=false
        for _ in 1 2 3 4 5; do
            if ss -lnt 2>/dev/null | grep -q ":$PORT\b" || \
               netstat -lnt 2>/dev/null | grep -q ":$PORT\b"; then
                port_ready=true
                break
            fi
            sleep 0.3
        done
        if ! editor_running || ! $port_ready; then
            echo "  editor:  failed to start; see $EDITOR_LOG"
            stop_all
            exit 1
        fi

        # 2. mGBA with the same XWayland/NVIDIA environment as the verified
        # headed game launch. Do not pipe or redirect this GUI process.
        DISPLAY=:0 \
        QT_QPA_PLATFORM=xcb \
        __GLX_VENDOR_LIBRARY_NAME=nvidia \
            "$PROJECT_DIR/scripts/mgba-qt-singleflight" \
            "$rom" --script "$LUA_SCRIPT" &
        mgba_pid=$!
        echo "$mgba_pid" > "$MGBA_PID_FILE"
        echo "  mgba:    PID $mgba_pid platform=xcb (ROM: $(basename "$rom"))"

        # A background GUI launch can fail after the shell has already returned
        # (for example, if Qt cannot create the requested display device).
        # Refuse to advertise a usable session unless the exact owned mGBA
        # process survives startup.
        sleep 2
        if ! mgba_running; then
            echo "  mgba:    failed to start with the XWayland/xcb display"
            echo "  check DISPLAY=:0 and the mGBA/Qt error shown in the terminal"
            stop_all
            exit 1
        fi

        # 3. Best-effort browser open
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

        echo
        status
        echo
        echo "This command remains the process guardian while the session is live."
        echo "To stop from another shell:  $0 stop"
        set +e
        wait "$mgba_pid"
        mgba_status=$?
        set -e
        exit "$mgba_status"
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
