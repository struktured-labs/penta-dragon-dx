"""Train PPO from Shalamar arena — pure numpy inner loop, torch only for gradient updates.

Avoids the torch+PyBoy deadlock by never running torch ops inside the env-step loop.
"""
from __future__ import annotations
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import json, time, sys
import numpy as np
import torch
torch.set_num_threads(1)

sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from penta_rl.env import N_ACTIONS, PentaEnv, ACTION_BUTTONS
from penta_rl.godmode_env import godmode_step
from penta_rl.state import vector_dim, read_state, state_to_vector
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from penta_rl.reward import RewardConfig

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"
OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def boss_kill_reward_cfg() -> RewardConfig:
    cfg = RewardConfig()
    cfg.step_penalty = -0.005
    cfg.boss_damage = 0.5
    cfg.boss_kill = 200.0
    cfg.boss_kill_chain = 50.0
    cfg.unique_room = 5.0
    return cfg


class ShalamarArenaEnv(PentaEnv):
    def __init__(self, *args, init_level=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_level = init_level

    def reset(self, seed=None, options=None):
        if self.pb is None:
            obs, info = super().reset(seed=seed, options=options)
            return obs, info
        with open(self.savestate_path, "rb") as fh:
            self.pb.load_state(fh)
        self.reward_tracker.reset()
        self.steps = 0
        self._held = []
        s = read_state(self.pb)
        self.reward_tracker.last_state = s
        return state_to_vector(s), {"state": s}

    def step(self, action: int):
        for b in self._held:
            self.pb.button_release(b)
        self._held = ACTION_BUTTONS[action]
        for b in self._held:
            self.pb.button_press(b)
        for _ in range(self.frame_skip):
            godmode_step(self.pb)
            self.pb.tick()
        self.steps += 1
        s = read_state(self.pb)
        reward, info = self.reward_tracker.step(s, action=action)
        success = s.level > self.init_level
        terminated = success
        truncated = self.steps >= self.max_steps
        if success:
            info["success"] = True
            reward += 500.0
        info["state"] = s
        info["steps"] = self.steps
        return state_to_vector(s), reward, terminated, truncated, info


class NumpyPolicy:
    """Numpy-only forward pass. Weights mirrored from torch agent."""
    def __init__(self, agent):
        self.agent = agent
        self.refresh()

    def refresh(self):
        """Copy torch weights to numpy."""
        weights = []
        with torch.no_grad():
            for p in self.agent.net.parameters():
                weights.append(p.cpu().numpy().copy())
        self.weights = weights

    def forward(self, obs):
        """3-layer MLP + 2 heads (policy logits, value).

        Match PolicyValueNet: shared trunk Linear→ReLU→Linear→ReLU→Linear→ReLU,
        then policy head Linear, value head Linear.
        """
        # Get layer order from torch model. PolicyValueNet has:
        # trunk: Linear(obs,256), ReLU, Linear(256,256), ReLU, Linear(256,256), ReLU
        # head_pi: Linear(256, n_actions)
        # head_v: Linear(256, 1)
        h = obs.astype(np.float32)
        # 3 trunk layers
        for i in range(3):
            W = self.weights[i*2].T  # torch stores [out, in], so transpose
            b = self.weights[i*2 + 1]
            h = np.maximum(0, h @ W + b)
        # Policy head
        Wpi = self.weights[6].T
        bpi = self.weights[7]
        logits = h @ Wpi + bpi
        # Value head
        Wv = self.weights[8].T
        bv = self.weights[9]
        v = (h @ Wv + bv).squeeze()
        return logits, float(v)


def main(epochs=100, steps_per_epoch=1024, max_steps_episode=600, label="shalamar_np"):
    device = "cpu"
    print(f"Device: {device}, epochs={epochs}, steps/epoch={steps_per_epoch}", flush=True)
    print(f"Save state: {SHALAMAR}", flush=True)

    env = ShalamarArenaEnv(ROM, max_steps=max_steps_episode, savestate_path=SHALAMAR,
                           reward_cfg=boss_kill_reward_cfg(), init_level=1)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch,
                    train_iters=10, entropy_coef=0.03)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    np_policy = NumpyPolicy(agent)

    obs, info = env.reset()
    init_ffba = info["state"].level
    print(f"Initial: FFBA={init_ffba} D880={hex(info['state'].scene)} HP={info['state'].player_hp}", flush=True)

    completed_returns = []
    ffba_advances = 0
    metrics = []
    t_start = time.time()
    rng = np.random.default_rng(0)

    for ep in range(epochs):
        t_ep = time.time()
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch)
        n_done = 0
        ep_reward = 0.0
        # Refresh numpy weights at start of each epoch
        np_policy.refresh()
        for t in range(steps_per_epoch):
            # Pure numpy forward pass
            logits, v = np_policy.forward(obs)
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            a = int(rng.choice(N_ACTIONS, p=probs))
            lp = float(np.log(probs[a] + 1e-10))
            obs2, rew, term, trunc, info2 = env.step(a)
            done = term or trunc
            buf.store(obs, a, float(rew), v, lp, done)
            ep_reward += float(rew)
            if info2["state"].level > init_ffba:
                ffba_advances += 1
                print(f"  *** FFBA ADVANCE *** ep={n_done+1} reward={ep_reward:.2f}", flush=True)
                done = True
            if done:
                n_done += 1
                completed_returns.append(ep_reward)
                ep_reward = 0.0
                obs, info = env.reset()
            else:
                obs = obs2

        # Compute last_val with numpy
        _, last_val = np_policy.forward(obs)
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        # Torch update — outside the env loop, no PyBoy interaction
        losses = agent.update(data)

        recent = completed_returns[-20:] or [0.0]
        elapsed = time.time() - t_start
        m = {
            "epoch": ep + 1, "elapsed_s": round(elapsed, 1),
            "n_eps_total": len(completed_returns),
            "mean_return": round(float(np.mean(recent)), 2),
            "max_return": round(float(max(recent)), 2),
            "ffba_advances": ffba_advances,
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        print(f"ep {ep+1:3d}/{epochs}  eps={len(completed_returns):4d}  "
              f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
              f"adv={ffba_advances}  ent={m['entropy']:.3f}  t={elapsed:.0f}s", flush=True)

        if (ep + 1) % 25 == 0:
            ckpt = f"{OUT_DIR}/ppo_{label}_ep{ep+1}.pt"
            torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                        "ffba_advances": ffba_advances}, ckpt)

    final = f"{OUT_DIR}/ppo_{label}_final.pt"
    torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                "ffba_advances": ffba_advances}, final)
    with open(final.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nFinal: {final}", flush=True)
    print(f"FFBA advances: {ffba_advances} / {len(completed_returns)} eps", flush=True)
    env.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    label = sys.argv[3] if len(sys.argv) > 3 else "shalamar_np"
    main(epochs=epochs, steps_per_epoch=steps, label=label)
