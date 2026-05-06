#!/bin/bash
# v20: RESUME v19 ep200 (golden), max_steps=20000, ckpt every 25 epochs (catch peaks)
# Goal: reach stage boss arena (D880=0x0C..0x14) after killing both mini-bosses
cd /home/struktured/projects/penta-dragon-dx-claude
source rl/.venv/bin/activate
python -c "
import torch
from rl.penta_rl.vec_env import VecPentaEnv
from rl.penta_rl.state import vector_dim
from rl.penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from rl.penta_rl.env import N_ACTIONS
import numpy as np, time, json, os

ROM = '/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb'
SAVE = '/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state'
SAVE_DIR = '/home/struktured/projects/penta-dragon-dx-claude/rl'
RESUME = '/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt'

device = 'cuda' if torch.cuda.is_available() else 'cpu'
n_envs, epochs, steps_per_epoch, max_steps = 2, 800, 512, 20000
print(f'Device: {device}, n_envs={n_envs}, epochs={epochs}, max_steps={max_steps}')
venv = VecPentaEnv(ROM, n=n_envs, max_steps=max_steps, savestate_path=SAVE)
obs_dim = vector_dim()
cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs,
                train_iters=10, entropy_coef=0.01,  # slight bump from 0.005 to keep stochasticity
                hidden=256, n_layers=3, gamma=0.99, pi_lr=3e-5)  # lower yet
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
state = torch.load(RESUME, map_location=device, weights_only=False)
agent.net.load_state_dict(state['model'])
print(f'Resumed from v19 ep200 (golden); chasing stage boss arena')

metrics, completed_returns, completed_bosses, multi_kill_eps, arena_eps = [], [], [], [], []
obs = venv.reset()
ep_rewards = np.zeros(n_envs, dtype=np.float32)
last_print = time.time()
t_start = time.time()
for ep in range(epochs):
    buf = TrajectoryBuffer(obs_dim, steps_per_epoch * n_envs)
    for t in range(steps_per_epoch):
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device)
            logits, vals = agent.net(o)
            dist = torch.distributions.Categorical(logits=logits)
            acts = dist.sample(); logps = dist.log_prob(acts)
        acts_np = acts.cpu().numpy(); vals_np = vals.cpu().numpy(); logps_np = logps.cpu().numpy()
        obs2, rews, dones, infos = venv.step(acts_np)
        for i in range(n_envs):
            buf.store(obs[i], int(acts_np[i]), float(rews[i]), float(vals_np[i]),
                      float(logps_np[i]), bool(dones[i]))
            ep_rewards[i] += rews[i]
            for ev in infos[i].get('events', []):
                if isinstance(ev, tuple) and ev:
                    if 'STAGE_ARENA' in str(ev[0]):
                        arena_eps.append({'ep': len(completed_returns)+1, 'epoch': ep+1, 'ev': str(ev)})
                        print(f'  *** ARENA *** ep_global={len(completed_returns)+1} ev={ev}')
                    if 'STAGE_BOSS_KILL' in str(ev[0]) or 'PENTA_DRAGON' in str(ev[0]):
                        print(f'  *** STAGE BOSS KILL *** ep={ep+1} {ev}')
            if dones[i]:
                completed_returns.append(float(ep_rewards[i]))
                nb = int(infos[i].get('n_unique_bosses', 0))
                completed_bosses.append(nb)
                if nb >= 2:
                    multi_kill_eps.append({'ep_global': len(completed_returns),
                        'epoch': ep+1, 'n_bosses': nb, 'reward': float(ep_rewards[i])})
                ep_rewards[i] = 0
        obs = obs2
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device)
        _, last_v = agent.net(o); last_val = float(last_v.mean().item())
    data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
    losses = agent.update(data)
    elapsed = time.time() - t_start
    recent = completed_returns[-30:] or [0.0]; recent_b = completed_bosses[-30:] or [0]
    multi_recent = sum(1 for b in completed_bosses[-100:] if b >= 2)
    m = {'epoch': ep+1, 'elapsed_s': round(elapsed, 1),
         'n_eps_total': len(completed_returns),
         'mean_return': round(float(np.mean(recent)), 3),
         'max_return': round(float(max(recent)), 3),
         'mean_bosses': round(float(np.mean(recent_b)), 2),
         'max_bosses': int(max(recent_b)),
         'total_boss_kills': int(np.sum(completed_bosses)),
         'multi_kill_recent_100': multi_recent,
         'arena_count': len(arena_eps),
         'loss_pi': round(losses['pi'], 4),
         'loss_v': round(losses['v'], 4),
         'entropy': round(losses['ent'], 4)}
    metrics.append(m)
    if time.time() - last_print >= 5 or ep == 0 or ep == epochs - 1:
        print(f\"ep {ep+1:4d}/{epochs}  eps={len(completed_returns):5d}  \"
              f\"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  \"
              f\"bosses={m['max_bosses']} (cum {m['total_boss_kills']}, multi100 {multi_recent}, arena {len(arena_eps)})  \"
              f\"ent={m['entropy']:.3f}  t={elapsed:.0f}s\")
        last_print = time.time()
    # Frequent ckpts to catch transient peaks (every 25 epochs)
    if (ep + 1) % 25 == 0:
        ckpt = f'{SAVE_DIR}/ppo_v20_resume19_ep{ep+1}.pt'
        torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
                    'multi_kill_episodes': multi_kill_eps,
                    'arena_episodes': arena_eps}, ckpt)

final = f'{SAVE_DIR}/ppo_v20_resume19_final.pt'
torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
            'multi_kill_episodes': multi_kill_eps,
            'arena_episodes': arena_eps}, final)
with open(final.replace('.pt', '_metrics.json'), 'w') as f:
    json.dump(metrics, f, indent=2)
print(f'\\nFinal: {final}')
print(f'Total: {len(completed_returns)} eps, {sum(completed_bosses)} cum kills, '
      f'{len(multi_kill_eps)} multi-kill eps, {len(arena_eps)} arena entries')
venv.close()
" 2>&1
