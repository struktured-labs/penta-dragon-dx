#!/bin/bash
# usage: run_pix.sh ROM OUT.tsv FRAMES MODE
cd /home/struktured/projects/penta-dragon-dx-issues
rm -f "$2" "$2.done"
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy PIX_OUT="$2" PIX_FRAMES="$3" PIX_INPUT="$4" \
 LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" scripts/mgba-qt-singleflight --script scripts/probes/perf_vblank/probe_pixhash.lua "$1" >/dev/null 2>&1 &
pid=$!
for i in $(seq 1 1200); do [ -f "$2.done" ] && break; kill -0 $pid 2>/dev/null || break; sleep 0.5; done
kill $pid 2>/dev/null; wait $pid 2>/dev/null
[ -f "$2.done" ] && echo "ok $2 $(wc -l < $2)" || echo "FAILED $2"
