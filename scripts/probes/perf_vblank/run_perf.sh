#!/bin/bash
# Perf prototype measurement (issue #49). Run only when no suite is running.
cd /home/struktured/projects/penta-dragon-dx-issues
P=tmp/perf-proto
for v in ${VARIANTS:-P1 P2 P3 P4 all}; do
  echo "== $(date +%H:%M:%S) profile $v"
  S7PROBE=scripts/probes/perf_vblank/probe_prof.lua bash scripts/probes/perf_vblank/s7run_slow.sh $P/$v $P/prof-$v $PWD/tmp/phase5/g3-glyph/stock-world.img 80
  python3 scripts/probes/perf_vblank/prof.py $P/prof-$v/stage7-dx-a-loop-patrol/result.json.prof.tsv | head -1
  python3 scripts/probes/perf_vblank/prof.py $P/prof-$v/stage7-dx-b-loop-patrol/result.json.prof.tsv | head -1
done
for v in ${S7VARIANTS:-all P2 P1 P3 P4}; do
  echo "== $(date +%H:%M:%S) stage7 v3 gate $v"
  GM=$P/gm-$v ROM=$P/$v/penta_dragon_dx_FIXED.gb .venv/bin/python scripts/probes/perf_vblank/gate2.py gameplay_movement_stress
done
echo "== $(date +%H:%M:%S) DONE"
