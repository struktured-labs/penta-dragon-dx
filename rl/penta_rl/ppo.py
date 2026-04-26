"""PPO trainer for PentaEnv. Adapted from dr_mario_rl PPO."""
from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from dataclasses import dataclass


@dataclass
class PPOConfig:
    gamma: float = 0.99
    lam: float = 0.95
    clip_ratio: float = 0.2
    pi_lr: float = 3e-4
    v_lr: float = 1e-3
    train_iters: int = 10
    minibatch: int = 256
    epochs: int = 50
    steps_per_epoch: int = 4096
    entropy_coef: float = 0.01
    hidden: int = 256


class PolicyValueNet(nn.Module):
    """Shared-trunk MLP with policy + value heads."""
    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 256):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.pi_head = nn.Linear(hidden, n_actions)
        self.v_head = nn.Linear(hidden, 1)

    def forward(self, obs: torch.Tensor):
        h = self.trunk(obs)
        return self.pi_head(h), self.v_head(h).squeeze(-1)


class PPOAgent:
    def __init__(self, obs_dim: int, n_actions: int, cfg: PPOConfig | None = None, device: str = "cpu"):
        self.cfg = cfg or PPOConfig()
        self.net = PolicyValueNet(obs_dim, n_actions, self.cfg.hidden).to(device)
        self.optim = optim.Adam(self.net.parameters(), lr=self.cfg.pi_lr)
        self.device = device
        self.obs_dim = obs_dim
        self.n_actions = n_actions

    def act(self, obs: np.ndarray, deterministic: bool = False):
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
            logits, v = self.net(o)
            dist = torch.distributions.Categorical(logits=logits)
            a = logits.argmax(-1) if deterministic else dist.sample()
            logp = dist.log_prob(a)
        return int(a.item()), float(v.item()), float(logp.item())

    def update(self, buf: dict):
        cfg = self.cfg
        obs = torch.as_tensor(buf["obs"], dtype=torch.float32, device=self.device)
        act = torch.as_tensor(buf["act"], dtype=torch.long, device=self.device)
        adv = torch.as_tensor(buf["adv"], dtype=torch.float32, device=self.device)
        ret = torch.as_tensor(buf["ret"], dtype=torch.float32, device=self.device)
        logp_old = torch.as_tensor(buf["logp"], dtype=torch.float32, device=self.device)
        N = obs.shape[0]
        idx = np.arange(N)
        losses = {"pi": [], "v": [], "ent": []}
        for _ in range(cfg.train_iters):
            np.random.shuffle(idx)
            for start in range(0, N, cfg.minibatch):
                j = idx[start:start+cfg.minibatch]
                o, a, adv_b, ret_b, logp_b = obs[j], act[j], adv[j], ret[j], logp_old[j]
                logits, v = self.net(o)
                dist = torch.distributions.Categorical(logits=logits)
                new_logp = dist.log_prob(a)
                ent = dist.entropy().mean()
                ratio = torch.exp(new_logp - logp_b)
                clip_adv = torch.clamp(ratio, 1-cfg.clip_ratio, 1+cfg.clip_ratio) * adv_b
                loss_pi = -(torch.min(ratio*adv_b, clip_adv)).mean() - cfg.entropy_coef*ent
                loss_v = ((v - ret_b)**2).mean()
                loss = loss_pi + 0.5 * loss_v
                self.optim.zero_grad(); loss.backward(); self.optim.step()
                losses["pi"].append(loss_pi.item())
                losses["v"].append(loss_v.item())
                losses["ent"].append(ent.item())
        return {k: float(np.mean(v)) for k, v in losses.items()}


class TrajectoryBuffer:
    def __init__(self, obs_dim: int, capacity: int):
        self.obs = np.zeros((capacity, obs_dim), np.float32)
        self.act = np.zeros((capacity,), np.int64)
        self.rew = np.zeros((capacity,), np.float32)
        self.val = np.zeros((capacity,), np.float32)
        self.logp = np.zeros((capacity,), np.float32)
        self.done = np.zeros((capacity,), np.bool_)
        self.ptr = 0
        self.capacity = capacity

    def store(self, o, a, r, v, logp, done):
        i = self.ptr
        self.obs[i] = o
        self.act[i] = a
        self.rew[i] = r
        self.val[i] = v
        self.logp[i] = logp
        self.done[i] = done
        self.ptr += 1

    def finish(self, gamma: float, lam: float, last_val: float = 0.0):
        T = self.ptr
        adv = np.zeros(T, np.float32)
        vals = self.val[:T]
        rews = self.rew[:T]
        dones = self.done[:T]
        lastgaelam = 0.0
        for t in reversed(range(T)):
            if t + 1 < T:
                nextv = vals[t+1]
                nonterm = 1.0 - float(dones[t])
            else:
                nextv = last_val
                nonterm = 1.0
            delta = rews[t] + gamma*nextv*nonterm - vals[t]
            lastgaelam = delta + gamma*lam*nonterm*lastgaelam
            adv[t] = lastgaelam
        ret = adv + vals[:T]
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        return {"obs": self.obs[:T], "act": self.act[:T],
                "adv": adv, "ret": ret, "logp": self.logp[:T]}

    def reset(self):
        self.ptr = 0
