#!/bin/bash
# usage: run_ls.sh ROM MODE DIR OUT FRAMES INPUT
cd /home/struktured/projects/penta-dragon-dx-issues
rm -f "$4" "$4.done"; mkdir -p "$3"
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy LS_MODE="$2" LS_DIR="$PWD/$3" LS_OUT="$4" LS_FRAMES="$5" LS_INPUT="$6" \
 LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" scripts/mgba-qt-singleflight --script scripts/probes/perf_vblank/lock/probe_lockstep.lua "$1" >"$4.stderr" 2>&1 &
pid=$!
for i in $(seq 1 2400); do [ -f "$4.done" ] && break; kill -0 $pid 2>/dev/null || break; sleep 0.5; done
kill $pid 2>/dev/null; wait $pid 2>/dev/null
[ -f "$4.done" ] && echo "ok $4 $(wc -l < $4)" || echo "FAILED $4"
