#!/bin/bash
# v36: godmode + PPO with explore-heavy reward, find arena via random teleporter step
# Sara never dies (godmode), big arena/room rewards. Episode = 50000 steps so a
# random teleporter hit becomes likely.
cd /home/struktured/projects/penta-dragon-dx-claude
source rl/.venv/bin/activate
python -c "
import torch
from rl.penta_rl.godmode_env import GodmodeEnv, explore_reward_config
from rl.penta_rl.state import vector_dim
from rl.penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from rl.penta_rl.env import N_ACTIONS
import numpy as np, time, json, os

ROM = '/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb'
SAVE = '/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state'
SAVE_DIR = '/home/struktured/projects/penta-dragon-dx-claude/rl'
BC = '/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt'

device = 'cuda' if torch.cuda.is_available() else 'cpu'
# Single env (godmode + multiprocess pyboy = SDL2 race; single proc is reliable)
n_envs, epochs, steps_per_epoch, max_steps = 1, 1500, 2048, 50000
print(f'Device: {device}, n_envs={n_envs}, epochs={epochs}, max_steps={max_steps}')

cfg_reward = explore_reward_config()
env = GodmodeEnv(ROM, max_steps=max_steps, savestate_path=SAVE, reward_cfg=cfg_reward)
obs, _ = env.reset()
obs_dim = vector_dim()
cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs,
                train_iters=10, entropy_coef=0.02,  # higher entropy for exploration
                hidden=256, n_layers=3, gamma=0.995, pi_lr=1e-4)  # higher gamma for sparse
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
state = torch.load(BC, map_location=device, weights_only=False)
agent.net.load_state_dict(state['model'], strict=False)
print(f'v36: BC + PPO + godmode + explore reward')

metrics = []
arena_eps = []
last_print = time.time()
t_start = time.time()
total_steps = 0
ep_count = 0
unique_rooms_global = set()

for ep_outer in range(epochs):
    buf = TrajectoryBuffer(obs_dim, steps_per_epoch * n_envs)
    obs, _ = env.reset()
    ep_reward = 0.0
    ep_unique_rooms = set()
    ep_max_section = 0
    ep_arena_seen = set()
    for t in range(steps_per_epoch):
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            logits, vals = agent.net(o)
            dist = torch.distributions.Categorical(logits=logits)
            acts = dist.sample()
            logps = dist.log_prob(acts)
        a = int(acts.item()); v = float(vals.item()); lp = float(logps.item())
        obs2, r, term, trunc, info = env.step(a)
        s = info['state']
        ep_unique_rooms.add(s.room)
        unique_rooms_global.add(s.room)
        if s.section > ep_max_section: ep_max_section = s.section
        if 0x0C <= s.scene <= 0x14:
            ep_arena_seen.add(s.scene)
            if s.scene not in [a['scene'] for a in arena_eps]:
                arena_eps.append({'epoch': ep_outer+1, 'step': t,
                                  'scene': s.scene, 'reward': float(ep_reward)})
                print(f'  *** ARENA {hex(s.scene)} *** epoch={ep_outer+1} t={t}')
        buf.store(obs, a, r, v, lp, term or trunc)
        ep_reward += r
        obs = obs2
        if term or trunc:
            obs, _ = env.reset()
            ep_count += 1
            ep_reward = 0.0
        total_steps += 1
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        _, last_v = agent.net(o); last_val = float(last_v.item())
    data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
    losses = agent.update(data)
    elapsed = time.time() - t_start
    m = {'epoch': ep_outer+1, 'elapsed_s': round(elapsed, 1),
         'total_steps': total_steps, 'ep_count': ep_count,
         'unique_rooms_ep': sorted(list(ep_unique_rooms)),
         'unique_rooms_global': sorted(list(unique_rooms_global)),
         'max_section': ep_max_section,
         'arena_seen': sorted([hex(x) for x in ep_arena_seen]),
         'arena_count_global': len(arena_eps),
         'loss_pi': round(losses['pi'], 4),
         'loss_v': round(losses['v'], 4),
         'entropy': round(losses['ent'], 4)}
    metrics.append(m)
    if time.time() - last_print >= 5 or ep_outer == 0 or ep_outer == epochs - 1:
        print(f\"ep {ep_outer+1:4d}/{epochs}  total_steps={total_steps:6d}  \"
              f\"rooms_global={sorted(list(unique_rooms_global))}  \"
              f\"arena_count={len(arena_eps)}  ent={m['entropy']:.3f}  t={elapsed:.0f}s\")
        last_print = time.time()
    if (ep_outer + 1) % 25 == 0:
        ckpt = f'{SAVE_DIR}/ppo_v36_godmode_explore_ep{ep_outer+1}.pt'
        torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
                    'arena_eps': arena_eps,
                    'unique_rooms_global': sorted(list(unique_rooms_global))}, ckpt)

final = f'{SAVE_DIR}/ppo_v36_godmode_explore_final.pt'
torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
            'arena_eps': arena_eps,
            'unique_rooms_global': sorted(list(unique_rooms_global))}, final)
with open(final.replace('.pt', '_metrics.json'), 'w') as f:
    json.dump(metrics, f, indent=2)
print(f'\\nFinal: {final}')
print(f'Total: {ep_count} eps, rooms={sorted(list(unique_rooms_global))}, '
      f'arenas={len(arena_eps)}')
env.close()
" 2>&1
