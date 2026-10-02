#!/bin/bash
# issue #49: pixel/attract checks then run_perf.sh (profiles + Stage-7 v3 gates)
cd /home/struktured/projects/penta-dragon-dx-issues
P=tmp/perf-proto
for v in base P1 P2 P3 P4 all; do
  rom=$P/$v/penta_dragon_dx_FIXED.gb; [ $v = base ] && rom=$P/base.gb
  echo "== $(date +%H:%M:%S) pix $v"
  bash scripts/probes/perf_vblank/run_pix.sh $rom $P/pix/idle-$v.tsv 9000 none
  bash scripts/probes/perf_vblank/run_pix.sh $rom $P/pix/play-$v.tsv 5000 play
done
for v in P1 P2 P3 P4 all; do
  echo "idle $v: $(python3 scripts/probes/perf_vblank/cmp_pix.py $P/pix/idle-base.tsv $P/pix/idle-$v.tsv)"
  echo "play $v: $(python3 scripts/probes/perf_vblank/cmp_pix.py $P/pix/play-base.tsv $P/pix/play-$v.tsv)"
done
bash scripts/probes/perf_vblank/run_perf.sh
