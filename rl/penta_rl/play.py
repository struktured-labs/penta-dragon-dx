"""Watch a trained policy play in a real PyBoy window (SDL2)."""
from __future__ import annotations
import sys, time
import torch
from .env import PentaEnv, N_ACTIONS
from .state import vector_dim
from .ppo import PPOAgent, PPOConfig


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def main(checkpoint: str, n_episodes: int = 1, deterministic: bool = False,
         max_steps: int = 6000, savestate: str | None = None, speed: int = 1):
    device = "cpu"  # rendering with cuda doesn't help much
    env = PentaEnv(ROM, max_steps=max_steps, render_mode="SDL2", savestate_path=savestate)
    obs_dim = vector_dim()
    cfg = PPOConfig()
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    state = torch.load(checkpoint, map_location=device, weights_only=False)
    agent.net.load_state_dict(state["model"])
    agent.net.eval()
    env.pb.set_emulation_speed(speed) if hasattr(env, "pb") and env.pb else None

    for ep in range(n_episodes):
        obs, info = env.reset()
        env.pb.set_emulation_speed(speed)
        ep_reward = 0.0
        steps = 0
        while True:
            a, v, logp = agent.act(obs, deterministic=deterministic)
            obs, r, term, trunc, info = env.step(a)
            ep_reward += r
            steps += 1
            if term or trunc:
                break
        s = env.get_state()
        print(f"ep {ep}: steps={steps} reward={ep_reward:.2f} bosses={info.get('n_unique_bosses', 0)} "
              f"final_scene=0x{s.scene:02X} final_room={s.room}")
    env.close()


if __name__ == "__main__":
    ckpt = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    det = "--det" in sys.argv
    save = None
    for a in sys.argv:
        if a.startswith("--savestate="):
            save = a.split("=", 1)[1]
    main(ckpt, n_episodes=n, deterministic=det, savestate=save)
