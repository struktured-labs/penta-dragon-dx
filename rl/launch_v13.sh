#!/bin/bash
# v13: PPO from v12c resume, REAL ROM, gargoyle.state, FIXED reward, long eps
cd /home/struktured/projects/penta-dragon-dx-claude
source rl/.venv/bin/activate
python -c "
from rl.penta_rl.train_simple import main
main(
    epochs=1500,
    steps_per_epoch=512,
    n_envs=2,
    max_steps=12000,
    label='v13_fixed_reward',
    savestate='/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state',
    rom='/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb',
    resume='/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v12c_cheat_2env_final.pt',
)
" 2>&1
