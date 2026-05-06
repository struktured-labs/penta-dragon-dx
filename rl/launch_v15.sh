#!/bin/bash
# v15: PPO from SCRATCH, REAL ROM, gameplay_start.state (full level 1 from start), max_steps=18000
cd /home/struktured/projects/penta-dragon-dx-claude
source rl/.venv/bin/activate
python -c "
from rl.penta_rl.train_simple import main
main(
    epochs=2000,
    steps_per_epoch=512,
    n_envs=2,
    max_steps=18000,
    label='v15_fullstart',
    savestate='/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state',
    rom='/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb',
    resume=None,
)
" 2>&1
