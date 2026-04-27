"""DAgger (Dataset Aggregation) for PentaEnv.

Algorithm:
  1. Train initial BC on expert demos
  2. Loop:
     a. Roll out current policy in env, log states it visits
     b. Query "expert" (heuristic from autoplay_v96 getKeys logic) for action at each state
     c. Append (state, expert_action) pairs to dataset
     d. Retrain policy on expanded dataset

The "expert" here is a Python re-implementation of v9.6 autoplay's getKeys()
function, which we can call directly without invoking mgba.
"""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import torch
from .env import PentaEnv, N_ACTIONS
from .state import vector_dim, GameState
from .ppo import PolicyValueNet, PPOConfig
from .bc_data import load_dataset


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


# Action constants matching env.ACTION_BUTTONS
ACT_A     = 0
ACT_B     = 1
ACT_R     = 4
ACT_L     = 5
ACT_U     = 6
ACT_D     = 7
ACT_UA    = 8
ACT_DA    = 9
ACT_LB    = 10
ACT_RB    = 11


def expert_action(s: GameState, frame_idx: int) -> int:
    """Reimplement v9.6 autoplay getKeys() in Python, returning action_idx.

    Operates on GameState including OAM features.
    """
    oam = s.raw_addrs.get("oam", {}) if s.raw_addrs else {}
    sara_x = oam.get("sara_x", 80); sara_y = oam.get("sara_y", 72)
    boss_x = oam.get("boss_x", -1); boss_y = oam.get("boss_y", -1)
    boss_count = oam.get("boss_count", 0)
    near_d = oam.get("near_dist", -1)
    near_x = oam.get("near_x", 0); near_y = oam.get("near_y", 0)

    f = frame_idx
    boss = s.miniboss

    # Boss fight: track + fire + dodge
    if boss > 0:
        if boss_count > 0 and boss_x >= 0:
            dx = boss_x - sara_x
            dy = boss_y - sara_y
            dist = (dx*dx + dy*dy) ** 0.5
            # Fire most frames
            fire = (f % 3 < 2)
            # Direction selection
            if dist > 70:
                # Move toward boss horizontally
                if abs(dx) > abs(dy):
                    return ACT_RB if dx > 0 else ACT_LB  # B button while moving
                else:
                    if dy > 0: return ACT_DA if fire else ACT_D
                    else: return ACT_UA if fire else ACT_U
            elif dist < 30:
                # Move away
                if dx > 0: return ACT_LB
                else: return ACT_RB
            else:
                # Circle / fire
                cy = f % 240
                if cy < 60: return ACT_UA if fire else ACT_U
                elif cy < 120: return ACT_RB
                elif cy < 180: return ACT_DA if fire else ACT_D
                else: return ACT_LB
        else:
            # Boss flag set but not visible — circle
            cy = f % 180
            if cy < 90: return ACT_RB
            else: return ACT_LB
    else:
        # Explore: RIGHT + fire + sine
        fire = (f % 4 < 2)
        cycle = f % 180
        if sara_y < 30: return ACT_DA if fire else ACT_D
        elif sara_y > 110: return ACT_UA if fire else ACT_U
        elif cycle < 45: return ACT_UA if fire else ACT_U
        elif cycle >= 90 and cycle < 135: return ACT_DA if fire else ACT_D
        else: return ACT_R if not fire else ACT_A  # right + fire (no combo, fall back to A)


def rollout_with_expert_labels(env: PentaEnv, agent_net, device: str, n_steps: int,
                                deterministic: bool = False,
                                beta: float = 0.0, frame_offset: int = 0) -> tuple[list, list]:
    """Roll out env using policy mixed with expert (DAgger).

    beta = probability of using EXPERT action (vs policy action) at each step.
    Always logs (state, expert_action) regardless.
    """
    obs, info = env.reset()
    states = []
    expert_actions = []
    rng = np.random.default_rng()
    for step in range(n_steps):
        s = info["state"]
        ea = expert_action(s, frame_offset + step)
        states.append(obs.copy())
        expert_actions.append(ea)
        # Choose action
        if rng.random() < beta:
            a = ea
        else:
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, _ = agent_net(o)
                if deterministic:
                    a = int(logits.argmax(-1).item())
                else:
                    dist = torch.distributions.Categorical(logits=logits)
                    a = int(dist.sample().item())
        obs, r, term, trunc, info = env.step(a)
        if term or trunc:
            obs, info = env.reset()
    return states, expert_actions


def main(initial_ckpt: str, expert_jsonl: str, out_path: str = None,
         dagger_iters: int = 3, rollout_steps: int = 4000,
         bc_epochs: int = 30, batch_size: int = 256, beta_schedule: list = None,
         savestate: str = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    obs_dim = vector_dim()
    cfg = PPOConfig()
    net = PolicyValueNet(obs_dim, N_ACTIONS, cfg.hidden).to(device)
    state = torch.load(initial_ckpt, map_location=device, weights_only=False)
    net.load_state_dict(state["model"], strict=False)
    print(f"Loaded {initial_ckpt}")

    # Load expert demos as starting dataset
    X_expert, y_expert = load_dataset(expert_jsonl)
    X_all = X_expert.copy()
    y_all = y_expert.copy()

    beta_schedule = beta_schedule or [0.5, 0.25, 0.0]  # decay expert mixing

    env = PentaEnv(ROM, max_steps=rollout_steps, savestate_path=savestate)
    optim = torch.optim.Adam(net.parameters(), lr=1e-4)
    loss_fn = torch.nn.CrossEntropyLoss()

    for it in range(dagger_iters):
        beta = beta_schedule[min(it, len(beta_schedule) - 1)]
        print(f"\n=== DAgger iter {it+1}/{dagger_iters} beta={beta} ===")
        net.eval()
        states, eactions = rollout_with_expert_labels(env, net, device, rollout_steps, beta=beta,
                                                      frame_offset=it * rollout_steps)
        X_new = np.stack(states)
        y_new = np.array(eactions, dtype=np.int64)
        # Aggregate
        X_all = np.concatenate([X_all, X_new])
        y_all = np.concatenate([y_all, y_new])
        print(f"  rollout: {len(X_new)} new pairs. dataset now {len(X_all)} total.")
        print(f"  rollout action dist: {np.bincount(y_new, minlength=N_ACTIONS)}")

        # BC retrain
        net.train()
        Xt = torch.as_tensor(X_all, dtype=torch.float32, device=device)
        yt = torch.as_tensor(y_all, dtype=torch.long, device=device)
        n = len(Xt)
        for ep in range(bc_epochs):
            perm = torch.randperm(n, device=device)
            ep_loss = 0; n_correct = 0
            for s in range(0, n, batch_size):
                j = perm[s:s+batch_size]
                xb, yb = Xt[j], yt[j]
                logits, _ = net(xb)
                loss = loss_fn(logits, yb)
                optim.zero_grad(); loss.backward(); optim.step()
                ep_loss += loss.item() * len(yb)
                n_correct += (logits.argmax(-1) == yb).sum().item()
            if ep == bc_epochs - 1 or ep % 10 == 0:
                print(f"  bc ep {ep+1}/{bc_epochs}: loss={ep_loss/n:.4f} acc={n_correct/n:.3f}")

    out_path = out_path or "/home/struktured/projects/penta-dragon-dx-claude/rl/dagger_final.pt"
    torch.save({"model": net.state_dict()}, out_path)
    print(f"\nSaved {out_path}")
    env.close()


if __name__ == "__main__":
    ckpt = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt"
    expert = sys.argv[2] if len(sys.argv) > 2 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_v96.jsonl"
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    main(ckpt, expert, dagger_iters=iters)
