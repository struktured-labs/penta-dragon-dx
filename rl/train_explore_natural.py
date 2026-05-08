"""Train PPO from gameplay_start.state with godmode HP — random walk + kills approach.

User said: "a randomly walking agent who kills things can beat the game.
By random I mean it explores the whole map, enters teleports and doors, etc.
Keep in mind the miniboss gates ur ability to exit/enter rooms."

Strategy:
- Start from gameplay_start (FFBA=0, normal level 1 dungeon)
- godmode: infinite HP, infinite corridor timer (DCBB pumped outside arena)
- Use v19 ep200 ckpt as base — it kills mini-bosses well
- PPO finetune with EXPLORATION rewards: unique rooms, arena entry, FFBA advance
"""
from __future__ import annotations
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import json, sys, time
import numpy as np
import torch
torch.set_num_threads(1)

sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from penta_rl.env import N_ACTIONS, PentaEnv, ACTION_BUTTONS
from penta_rl.godmode_env import godmode_step
from penta_rl.state import vector_dim, read_state, state_to_vector
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from penta_rl.reward import RewardConfig
from train_shalamar_np import NumpyPolicy

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
GAMEPLAY = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
V19_CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"
OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def explore_reward_cfg() -> RewardConfig:
    cfg = RewardConfig()
    cfg.step_penalty = -0.001
    cfg.boss_damage = 0.5
    cfg.boss_kill = 100.0
    cfg.boss_kill_chain = 50.0
    cfg.unique_room = 100.0          # huge bonus for new (level, room) tuple
    cfg.stage_boss_arena_enter = 1000.0  # ENTERING arena is the goal
    return cfg


class NaturalExploreEnv(PentaEnv):
    """gameplay_start env, godmode HP, terminate on FFBA advance OR max steps.
    Tracks unique (FFBA, FFBD, DCB8) tuples to reward exploration."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._visited = set()
        self._init_ffba = 0
        self._arenas_seen = set()

    def reset(self, seed=None, options=None):
        self._visited = set()
        self._arenas_seen = set()
        self._stale_count = 0
        self._last_pos = None
        if self.pb is None:
            obs, info = super().reset(seed=seed, options=options)
            self._init_ffba = info["state"].level
            return obs, info
        with open(self.savestate_path, "rb") as fh:
            self.pb.load_state(fh)
        self.reward_tracker.reset()
        self.steps = 0
        self._held = []
        s = read_state(self.pb)
        self.reward_tracker.last_state = s
        self._init_ffba = s.level
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
        # Exploration bonus: new (FFBA, FFBD, DCB8) tuple
        key = (s.level, s.room, self.pb.memory[0xDCB8])
        if key not in self._visited:
            self._visited.add(key)
            reward += 10.0
        # Stagnation penalty: track player pixel position; penalize if stuck
        py = self.pb.memory[0xFE05]
        px = self.pb.memory[0xFE04]
        cur_pos = (s.room, py // 8, px // 8)  # 8x8 tile grid
        if cur_pos == self._last_pos:
            self._stale_count += 1
            if self._stale_count > 30:
                reward -= 0.5  # stagnation penalty
        else:
            self._stale_count = 0
            reward += 0.05  # tiny reward for movement
            self._last_pos = cur_pos
        # Reward room CHANGES (regardless of unique) — encourages navigation
        if s.room != self.reward_tracker.last_state.room:
            reward += 20.0
        # Arena entry bonus
        if 0x0C <= s.scene <= 0x14 and s.scene not in self._arenas_seen:
            self._arenas_seen.add(s.scene)
            reward += 200.0
        # FFBA advance = HUGE reward + terminate
        success = s.level > self._init_ffba
        terminated = success
        truncated = self.steps >= self.max_steps
        if success:
            info["success"] = True
            reward += 1000.0
        info["state"] = s
        info["steps"] = self.steps
        info["n_visited"] = len(self._visited)
        info["n_arenas"] = len(self._arenas_seen)
        return state_to_vector(s), reward, terminated, truncated, info


def run_chunk(epochs, steps_per_epoch, label, resume_path=None):
    device = "cpu"
    env = NaturalExploreEnv(ROM, max_steps=1024, savestate_path=GAMEPLAY,
                            reward_cfg=explore_reward_cfg())
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch,
                    train_iters=10, entropy_coef=0.05)  # higher exploration
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

    # Resume priority: latest checkpoint, else v19 ep200 base
    loaded = False
    if resume_path and os.path.exists(resume_path):
        state = torch.load(resume_path, map_location=device, weights_only=False)
        agent.net.load_state_dict(state["model"])
        prior_metrics = state.get("metrics", [])
        prior_advances = state.get("ffba_advances", 0)
        print(f"Resumed from {resume_path}, {len(prior_metrics)} prior epochs", flush=True)
        loaded = True
    elif os.path.exists(V19_CKPT):
        try:
            state = torch.load(V19_CKPT, map_location=device, weights_only=False)
            agent.net.load_state_dict(state["model"])
            prior_metrics = []
            prior_advances = 0
            print(f"Bootstrapped from v19 ep200", flush=True)
            loaded = True
        except Exception as e:
            print(f"v19 load failed: {e}, training from scratch", flush=True)
    if not loaded:
        prior_metrics = []
        prior_advances = 0

    np_policy = NumpyPolicy(agent)

    obs, info = env.reset()
    init_ffba = info["state"].level
    print(f"Initial: FFBA={init_ffba} D880={hex(info['state'].scene)} FFBD={info['state'].room}", flush=True)

    completed_returns = []
    ffba_advances = prior_advances
    arenas_total = 0
    visited_total = set()
    metrics = list(prior_metrics)
    t_start = time.time()
    rng = np.random.default_rng(int(time.time()) & 0xFFFF)

    def save_ckpt():
        save_path = f"{OUT_DIR}/ppo_{label}_chunk{len(metrics)}.pt"
        torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                    "ffba_advances": ffba_advances}, save_path)
        latest = f"{OUT_DIR}/ppo_{label}_latest.pt"
        if os.path.lexists(latest):
            os.unlink(latest)
        os.symlink(save_path, latest)

    for ep in range(epochs):
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch)
        n_done = 0
        ep_reward = 0.0
        np_policy.refresh()
        max_visited_this_ep = 0
        max_arenas_this_ep = 0
        for t in range(steps_per_epoch):
            logits, v = np_policy.forward(obs)
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            a = int(rng.choice(N_ACTIONS, p=probs))
            lp = float(np.log(probs[a] + 1e-10))
            obs2, rew, term, trunc, info2 = env.step(a)
            done = term or trunc
            buf.store(obs, a, float(rew), v, lp, done)
            ep_reward += float(rew)
            max_visited_this_ep = max(max_visited_this_ep, info2.get("n_visited", 0))
            max_arenas_this_ep = max(max_arenas_this_ep, info2.get("n_arenas", 0))
            if info2["state"].level > init_ffba:
                ffba_advances += 1
                print(f"  *** FFBA ADVANCE *** ep={n_done+1} {init_ffba}→{info2['state'].level} reward={ep_reward:.2f}", flush=True)
            if done:
                n_done += 1
                completed_returns.append(ep_reward)
                ep_reward = 0.0
                obs, info = env.reset()
            else:
                obs = obs2

        _, last_val = np_policy.forward(obs)
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        recent = completed_returns[-10:] or [0.0]
        elapsed = time.time() - t_start
        m = {
            "epoch": len(metrics) + 1, "elapsed_s": round(elapsed, 1),
            "n_eps_chunk": len(completed_returns),
            "mean_return": round(float(np.mean(recent)), 2),
            "max_return": round(float(max(recent)), 2),
            "ffba_advances": ffba_advances,
            "max_visited_ep": max_visited_this_ep,
            "max_arenas_ep": max_arenas_this_ep,
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        print(f"ep {len(metrics):4d}  eps={len(completed_returns):3d}  "
              f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
              f"adv={ffba_advances}  vis={max_visited_this_ep}  arenas={max_arenas_this_ep}  "
              f"ent={m['entropy']:.3f}  t={elapsed:.0f}s", flush=True)
        save_ckpt()

    print(f"\nChunk done: {len(metrics)} epochs, {ffba_advances} advances", flush=True)
    env.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    label = sys.argv[3] if len(sys.argv) > 3 else "explore_natural"
    resume = sys.argv[4] if len(sys.argv) > 4 else f"{OUT_DIR}/ppo_{label}_latest.pt"
    run_chunk(epochs, steps, label, resume_path=resume)
