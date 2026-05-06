#!/bin/bash
# v26: BC + PPO from gameplay_start.state, REWARD v5 (section_advance bumped 0.3→25)
# Goal: section bonus drives corridor navigation past gargoyle into spider section
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
SAVE = '/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state'
SAVE_DIR = '/home/struktured/projects/penta-dragon-dx-claude/rl'
BC = '/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt'

device = 'cuda' if torch.cuda.is_available() else 'cpu'
n_envs, epochs, steps_per_epoch, max_steps = 2, 1500, 512, 18000
print(f'Device: {device}, n_envs={n_envs}, epochs={epochs}, max_steps={max_steps}')
venv = VecPentaEnv(ROM, n=n_envs, max_steps=max_steps, savestate_path=SAVE)
obs_dim = vector_dim()
cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs,
                train_iters=10, entropy_coef=0.005,
                hidden=256, n_layers=3, gamma=0.99, pi_lr=1e-4)
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
state = torch.load(BC, map_location=device, weights_only=False)
agent.net.load_state_dict(state['model'], strict=False)
print(f'v26: BC + PPO + reward v5 (section_advance 0.3→25)')

metrics, completed_returns, completed_bosses, multi_kill_eps = [], [], [], []
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
            if dones[i]:
                completed_returns.append(float(ep_rewards[i]))
                nb = int(infos[i].get('n_unique_bosses', 0))
                completed_bosses.append(nb)
                if nb >= 2:
                    multi_kill_eps.append({'ep_global': len(completed_returns),
                        'epoch': ep+1, 'n_bosses': nb, 'reward': float(ep_rewards[i])})
                    print(f'  *** MULTI KILL *** ep_global={len(completed_returns)} '
                          f'n_bosses={nb} reward={ep_rewards[i]:.2f}')
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
         'loss_pi': round(losses['pi'], 4),
         'loss_v': round(losses['v'], 4),
         'entropy': round(losses['ent'], 4)}
    metrics.append(m)
    if time.time() - last_print >= 5 or ep == 0 or ep == epochs - 1:
        print(f\"ep {ep+1:4d}/{epochs}  eps={len(completed_returns):5d}  \"
              f\"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  \"
              f\"bosses={m['max_bosses']} (cum {m['total_boss_kills']}, multi100 {multi_recent})  \"
              f\"ent={m['entropy']:.3f}  t={elapsed:.0f}s\")
        last_print = time.time()
    if (ep + 1) % 25 == 0:
        ckpt = f'{SAVE_DIR}/ppo_v26_rewardv5_ep{ep+1}.pt'
        torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
                    'multi_kill_episodes': multi_kill_eps}, ckpt)

final = f'{SAVE_DIR}/ppo_v26_rewardv5_final.pt'
torch.save({'model': agent.net.state_dict(), 'metrics': metrics,
            'multi_kill_episodes': multi_kill_eps}, final)
with open(final.replace('.pt', '_metrics.json'), 'w') as f:
    json.dump(metrics, f, indent=2)
print(f'\\nFinal: {final}')
print(f'Total: {len(completed_returns)} eps, {sum(completed_bosses)} cum kills, '
      f'{len(multi_kill_eps)} multi-kill eps')
venv.close()
" 2>&1
