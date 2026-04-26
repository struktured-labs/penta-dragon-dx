"""Multiprocess vectorized PentaEnv."""
from __future__ import annotations
import multiprocessing as mp
import numpy as np
from typing import Callable
from .env import PentaEnv, N_ACTIONS
from .reward import RewardConfig


def _make_penta_env(rom_path: str, max_steps: int):
    """Top-level factory (picklable)."""
    return PentaEnv(rom_path, max_steps=max_steps)


def _worker(remote, rom_path: str, max_steps: int):
    env = _make_penta_env(rom_path, max_steps)
    obs, info = env.reset()
    try:
        while True:
            cmd, data = remote.recv()
            if cmd == "step":
                obs, r, term, trunc, info = env.step(data)
                done = term or trunc
                if done:
                    obs, info = env.reset()
                # Strip non-pickleable bits from info
                info_min = {
                    "n_unique_bosses": info.get("n_unique_bosses", 0),
                    "events": info.get("events", []),
                    "success": info.get("success", False),
                    "steps": info.get("steps", 0),
                }
                remote.send((obs, r, done, info_min))
            elif cmd == "reset":
                obs, info = env.reset()
                remote.send(obs)
            elif cmd == "close":
                env.close()
                remote.close()
                break
    except Exception as e:
        try:
            env.close()
        except Exception:
            pass
        remote.send(("error", str(e)))


class VecPentaEnv:
    def __init__(self, rom_path: str, n: int = 4, max_steps: int = 2000):
        self.n = n
        self.parents = []
        self.procs = []
        ctx = mp.get_context("spawn")
        for _ in range(n):
            parent, child = ctx.Pipe()
            p = ctx.Process(target=_worker, args=(child, rom_path, max_steps), daemon=True)
            p.start()
            child.close()
            self.parents.append(parent)
            self.procs.append(p)
        self.action_n = N_ACTIONS

    def reset(self):
        for parent in self.parents:
            parent.send(("reset", None))
        return np.stack([parent.recv() for parent in self.parents])

    def step(self, actions: np.ndarray):
        for parent, a in zip(self.parents, actions):
            parent.send(("step", int(a)))
        results = [parent.recv() for parent in self.parents]
        obs, rew, done, infos = zip(*results)
        return np.stack(obs), np.array(rew, dtype=np.float32), np.array(done, dtype=np.bool_), list(infos)

    def close(self):
        for parent in self.parents:
            try:
                parent.send(("close", None))
            except Exception:
                pass
        for p in self.procs:
            p.join(timeout=2)
            if p.is_alive():
                p.terminate()


