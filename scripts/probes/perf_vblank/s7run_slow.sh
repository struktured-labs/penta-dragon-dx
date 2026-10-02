#!/bin/bash
# usage: s7run.sh ROMDIR OUTDIR [IMAGE SEED]
set -e
cd /home/struktured/projects/penta-dragon-dx-issues
rm -rf "$2"; mkdir -p "$2"
if [ -n "$3" ]; then export STAGE7_WORLD_IMAGE="$3" STAGE7_WORLD_SEED="$4"; fi
STAGE7_STATE_PATROL_BASE_PROBE=$PWD/scripts/diagnostics/probe_stage_speed.lua STAGE_SPEED_CAMERA_TRACE=1 LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" TMPDIR=$PWD/tmp timeout 2000 .venv/bin/python -c "import sys;from pathlib import Path;sys.path.insert(0,'scripts/diagnostics');import verify_stage_speed_matrix as m;m.PROBE=Path(__import__('os').environ.get('S7PROBE','scripts/diagnostics/probe_stage7_state_patrol.lua')).resolve();raise SystemExit(m.main())" --dx-rom "$1/penta_dragon_dx_FIXED.gb" --original-rom "$PWD/rom/Penta Dragon (J).gb" --targets 6 --input-mode loop-patrol --frames 4000 --tolerance 0.02 --accepted-slow-stage 7=0.92 --output "$2" --timeout 400 > "$2.log" 2>&1 || true
