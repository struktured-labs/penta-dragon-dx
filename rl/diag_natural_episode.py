"""Diagnostic: load latest natural-explore ckpt, run 3 deterministic episodes,
log scene/miniboss/section transitions to find why agent never kills mini-boss."""
from __future__ import annotations
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import sys, time
import numpy as np
import torch
torch.set_num_threads(1)

sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from penta_rl.env import N_ACTIONS, PentaEnv, ACTION_BUTTONS
from penta_rl.godmode_env import godmode_step
from penta_rl.state import vector_dim, read_state, state_to_vector
from penta_rl.ppo import PPOAgent, PPOConfig
from penta_rl.reward import RewardConfig
from train_shalamar_np import NumpyPolicy
from train_explore_natural import NaturalExploreEnv, explore_reward_cfg, ROM, GAMEPLAY

CKPT = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_explore_natural_latest.pt"
N_EPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
MAX_STEPS = int(sys.argv[3]) if len(sys.argv) > 3 else 2048


def main():
    env = NaturalExploreEnv(ROM, max_steps=MAX_STEPS, savestate_path=GAMEPLAY,
                            reward_cfg=explore_reward_cfg())
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=1, steps_per_epoch=MAX_STEPS, train_iters=1, entropy_coef=0.05)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device="cpu")
    state = torch.load(CKPT, map_location="cpu", weights_only=False)
    agent.net.load_state_dict(state["model"])
    print(f"Loaded {CKPT}", flush=True)
    print(f"Prior epochs={len(state.get('metrics', []))} ffba_advances={state.get('ffba_advances', 0)}",
          flush=True)
    np_policy = NumpyPolicy(agent)
    rng = np.random.default_rng(42)

    for ep in range(N_EPS):
        obs, info = env.reset()
        s = info["state"]
        print(f"\n=== EP {ep} === init D880={hex(s.scene)} FFBA={s.level} FFBD={s.room} "
              f"FFBF={s.miniboss} DCB8={env.pb.memory[0xDCB8]}", flush=True)
        np_policy.refresh()
        prev_scene = s.scene
        prev_mb = s.miniboss
        prev_dcb8 = env.pb.memory[0xDCB8]
        prev_room = s.room
        scene_changes = []
        mb_events = []
        section_changes = []
        room_changes = []
        ep_reward = 0.0
        damage_events = 0
        for t in range(MAX_STEPS):
            logits, v = np_policy.forward(obs)
            # Argmax (deterministic)
            a = int(np.argmax(logits))
            obs, rew, term, trunc, info = env.step(a)
            ep_reward += float(rew)
            s = info["state"]
            cur_dcb8 = env.pb.memory[0xDCB8]
            if s.scene != prev_scene:
                scene_changes.append((t, hex(prev_scene), hex(s.scene)))
                prev_scene = s.scene
            if s.miniboss != prev_mb:
                mb_events.append((t, prev_mb, s.miniboss, hex(s.scene),
                                   env.pb.memory[0xDCBB]))
                prev_mb = s.miniboss
            if cur_dcb8 != prev_dcb8:
                section_changes.append((t, prev_dcb8, cur_dcb8))
                prev_dcb8 = cur_dcb8
            if s.room != prev_room:
                room_changes.append((t, prev_room, s.room))
                prev_room = s.room
            done = term or trunc
            if done:
                break
        print(f"  reward={ep_reward:.1f} steps={t+1} terminated={term} truncated={trunc}", flush=True)
        print(f"  unique tuples visited: {info.get('n_visited',0)} arenas: {info.get('n_arenas',0)}", flush=True)
        print(f"  scene_changes: {len(scene_changes)}", flush=True)
        for sc in scene_changes[:8]:
            print(f"    t={sc[0]} {sc[1]}->{sc[2]}", flush=True)
        print(f"  mb_events: {len(mb_events)}", flush=True)
        for mb in mb_events[:8]:
            print(f"    t={mb[0]} FFBF {mb[1]}->{mb[2]} scene={mb[3]} DCBB={mb[4]}", flush=True)
        print(f"  section_changes (DCB8): {len(section_changes)}", flush=True)
        for sc in section_changes[:8]:
            print(f"    t={sc[0]} {sc[1]}->{sc[2]}", flush=True)
        print(f"  room_changes: {len(room_changes)}", flush=True)
    env.close()


if __name__ == "__main__":
    main()
