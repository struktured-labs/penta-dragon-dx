#!/bin/bash
cd /home/struktured/projects/penta-dragon-dx-claude/rl
source .venv/bin/activate
LABEL="${1:-demo_curriculum}"
TOTAL_CHUNKS="${2:-200}"
CHUNK_EPOCHS="${3:-2}"
STEPS="${4:-1024}"
TIMEOUT="${5:-180}"
LOG="logs/${LABEL}_chunked.log"
echo "==== Demo curriculum: $TOTAL_CHUNKS chunks of $CHUNK_EPOCHS epochs ====" >> "$LOG"
for i in $(seq 1 $TOTAL_CHUNKS); do
    echo "" >> "$LOG"
    echo "==== CHUNK $i/$TOTAL_CHUNKS ====" >> "$LOG"
    echo "$(date): starting chunk $i" >> "$LOG"
    timeout $TIMEOUT python -u train_demo_curriculum.py $CHUNK_EPOCHS $STEPS $LABEL >> "$LOG" 2>&1
    rc=$?
    echo "$(date): chunk $i exit=$rc" >> "$LOG"
    if [ $rc -eq 0 ]; then echo "  chunk $i: ok" >> "$LOG"
    elif [ $rc -eq 124 ]; then echo "  chunk $i: TIMEOUT" >> "$LOG"
    else echo "  chunk $i: error $rc" >> "$LOG"
    fi
done
