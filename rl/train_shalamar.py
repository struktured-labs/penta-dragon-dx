"""Train PPO from the Shalamar arena save state — verified-stable arena (FFBA=1, D880=0x0D).

Single-env training (multi-env godmode setup races SDL2). Goal: kill Shalamar consistently.
Success signal: FFBA advances from 1 to 2 (Shalamar dies → next stage).
"""
from __future__ import annotations
import json, time, sys, os
import numpy as np
import torch

sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from penta_rl.env import N_ACTIONS, PentaEnv, ACTION_BUTTONS
from penta_rl.godmode_env import godmode_step
from penta_rl.state import vector_dim, read_state, state_to_vector
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from penta_rl.reward import RewardConfig


class ShalamarArenaEnv(PentaEnv):
    """PentaEnv loaded into Shalamar arena, godmode HP, terminate on FFBA advance.

    Fast reset: reload save_state without restarting PyBoy (avoids 5-10s SDL2 init per ep).
    Episode ends when:
    - FFBA increments (Shalamar killed → next stage) ✓ success
    - max_steps reached (truncated)
    """

    def __init__(self, *args, init_level=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_level = init_level
        self._last_ffba = init_level

    def reset(self, seed=None, options=None):
        # First reset: PentaEnv creates PyBoy and loads state
        if self.pb is None:
            obs, info = super().reset(seed=seed, options=options)
            self._last_ffba = info["state"].level
            return obs, info
        # Subsequent resets: just reload state (no PyBoy restart)
        with open(self.savestate_path, "rb") as fh:
            self.pb.load_state(fh)
        self.reward_tracker.reset()
        self.steps = 0
        self._held = []
        s = read_state(self.pb)
        self.reward_tracker.last_state = s
        self._last_ffba = s.level
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
        # Success: FFBA advanced past initial level (Shalamar died)
        success = s.level > self.init_level
        terminated = success
        truncated = self.steps >= self.max_steps
        if success:
            info["success"] = True
            info["levels_advanced"] = s.level - self.init_level
            reward += 500.0  # big bonus for kill
        info["state"] = s
        info["steps"] = self.steps
        return state_to_vector(s), reward, terminated, truncated, info

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"
OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def boss_kill_reward_cfg() -> RewardConfig:
    """Reward shaped for killing the stage boss (Shalamar)."""
    cfg = RewardConfig()
    # Step penalty (encourage fast kill)
    cfg.step_penalty = -0.005
    # Big reward for FFBA advance (means Shalamar died → game progresses)
    cfg.stage_boss_arena_enter = 0.0  # already in arena
    # Reward damaging the boss (DCBB drops)
    cfg.boss_damage = 0.5  # was 0
    # Boss kill (FFBF→0 transition or scene leaves arena)
    cfg.boss_kill = 200.0
    cfg.boss_kill_chain = 50.0
    cfg.unique_room = 5.0  # leaving arena to next room = good
    return cfg


def main(epochs: int = 100, steps_per_epoch: int = 1024, max_steps_episode: int = 600,
         label: str = "shalamar"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}, epochs={epochs}, steps/epoch={steps_per_epoch}")
    print(f"Save state: {SHALAMAR}")

    env = ShalamarArenaEnv(ROM, max_steps=max_steps_episode, savestate_path=SHALAMAR,
                            reward_cfg=boss_kill_reward_cfg(), init_level=1)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch,
                    train_iters=10, entropy_coef=0.03,
                    gamma=0.995, lam=0.97)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

    metrics = []
    obs, info = env.reset()
    init_ffba = info["state"].level
    init_d880 = info["state"].scene
    print(f"Initial: FFBA={init_ffba} D880={hex(init_d880)} HP={info['state'].player_hp}")

    ep_reward = 0.0
    ep_steps = 0
    completed_returns = []
    boss_kills = 0
    ffba_advances = 0
    last_print = time.time()
    t_start = time.time()
    for ep in range(epochs):
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch)
        for t in range(steps_per_epoch):
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, vals = agent.net(o)
                dist = torch.distributions.Categorical(logits=logits)
                act = dist.sample()
                logp = dist.log_prob(act)
            a = int(act.item())
            v = float(vals.item())
            lp = float(logp.item())
            obs2, rew, term, trunc, info2 = env.step(a)
            done = term or trunc
            buf.store(obs, a, float(rew), v, lp, done)
            ep_reward += float(rew)
            ep_steps += 1
            cur_ffba = info2["state"].level
            cur_d880 = info2["state"].scene
            if cur_ffba > init_ffba:
                ffba_advances += 1
                print(f"  *** FFBA ADVANCE *** ep={len(completed_returns)+1} init={init_ffba}→{cur_ffba} "
                      f"steps={ep_steps} reward={ep_reward:.2f}")
                done = True
            if done:
                completed_returns.append(ep_reward)
                ep_reward = 0.0
                ep_steps = 0
                obs, info = env.reset()
            else:
                obs = obs2

        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            _, last_v = agent.net(o)
            last_val = float(last_v.item())
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        elapsed = time.time() - t_start
        recent = completed_returns[-30:] or [0.0]
        m = {
            "epoch": ep + 1, "elapsed_s": round(elapsed, 1),
            "n_eps": len(completed_returns),
            "mean_return": round(float(np.mean(recent)), 3),
            "max_return": round(float(max(recent)), 3),
            "ffba_advances": ffba_advances,
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        if time.time() - last_print >= 5 or ep == 0 or ep == epochs - 1:
            print(f"ep {ep+1:4d}/{epochs}  eps={len(completed_returns):4d}  "
                  f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
                  f"adv={ffba_advances}  ent={m['entropy']:.3f}  t={elapsed:.0f}s")
            last_print = time.time()

        if (ep + 1) % 25 == 0:
            ckpt = f"{OUT_DIR}/ppo_{label}_ep{ep+1}.pt"
            torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                        "ffba_advances": ffba_advances}, ckpt)

    final = f"{OUT_DIR}/ppo_{label}_final.pt"
    torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                "ffba_advances": ffba_advances}, final)
    with open(final.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nFinal: {final}")
    print(f"FFBA advances (Shalamar kills): {ffba_advances} / {len(completed_returns)} eps")
    env.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    label = sys.argv[3] if len(sys.argv) > 3 else "shalamar"
    main(epochs=epochs, steps_per_epoch=steps, label=label)
