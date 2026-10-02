#!/bin/bash
# issue #49: lockstep pixel identity (fixed probe: default-flag savestates) for base vs P1-P4/all,
# then the same-harness base Stage-7 v3 gate rerun (noise estimate).
cd /home/struktured/projects/penta-dragon-dx-issues
P=tmp/perf-proto; L=$P/lock; S=scripts/probes/perf_vblank
echo "== $(date +%H:%M:%S) record"
bash $S/lock/run_ls.sh $P/base.gb record $L/st2-idle $L/rec2-idle.tsv 9000 none
bash $S/lock/run_ls.sh $P/base.gb record $L/st2-game $L/rec2-game.tsv 5000 game
for v in base all P1 P2 P3 P4; do
  rom=$P/$v/penta_dragon_dx_FIXED.gb; [ $v = base ] && rom=$P/base.gb
  echo "== $(date +%H:%M:%S) replay $v"
  bash $S/lock/run_ls.sh $rom replay $L/st2-idle $L/rep2-idle-$v.tsv 9000 none
  bash $S/lock/run_ls.sh $rom replay $L/st2-game $L/rep2-game-$v.tsv 5000 game
done
echo "rec-vs-rep base idle: $(python3 $S/lock/cmp_ls.py $L/rec2-idle.tsv $L/rep2-idle-base.tsv)"
echo "rec-vs-rep base game: $(python3 $S/lock/cmp_ls.py $L/rec2-game.tsv $L/rep2-game-base.tsv)"
for v in all P1 P2 P3 P4; do
  echo "idle $v: $(python3 $S/lock/cmp_ls.py $L/rep2-idle-base.tsv $L/rep2-idle-$v.tsv)"
  echo "game $v: $(python3 $S/lock/cmp_ls.py $L/rep2-game-base.tsv $L/rep2-game-$v.tsv)"
done
echo "== $(date +%H:%M:%S) stage7 v3 gate base (rerun, same harness)"
GM=$P/gm-base ROM=$P/base.gb .venv/bin/python $S/gate2.py gameplay_movement_stress
python3 $S/gate_summary.py $P/gm-*/logs/gameplay_movement_stress.log tmp/rl-suite-20261002-01/matrix/logs/gameplay_movement_stress.log
echo "== $(date +%H:%M:%S) DONE"
