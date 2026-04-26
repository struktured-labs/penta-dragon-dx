"""Behavioral cloning pre-train of PolicyValueNet from expert trajectories."""
from __future__ import annotations
import json, time, sys, os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from .ppo import PolicyValueNet, PPOConfig
from .state import vector_dim
from .env import N_ACTIONS
from .bc_data import load_dataset


def main(jsonl_path: str, out_path: str = None, epochs: int = 30,
         batch_size: int = 256, lr: float = 3e-4, val_frac: float = 0.1):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    X, y = load_dataset(jsonl_path)
    n = len(X)
    n_val = int(n * val_frac)
    rng = np.random.default_rng(42)
    perm = rng.permutation(n)
    X = X[perm]; y = y[perm]
    X_train, y_train = X[n_val:], y[n_val:]
    X_val, y_val = X[:n_val], y[:n_val]
    print(f"Train: {len(X_train)}, Val: {len(X_val)}")

    obs_dim = vector_dim()
    cfg = PPOConfig()
    net = PolicyValueNet(obs_dim, N_ACTIONS, cfg.hidden).to(device)
    opt = optim.Adam(net.parameters(), lr=lr)

    # Class weights to combat imbalance (some actions much more common)
    counts = np.bincount(y_train, minlength=N_ACTIONS).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    weights = (counts.sum() / (N_ACTIONS * counts))
    weights = torch.as_tensor(weights, dtype=torch.float32, device=device)
    print(f"Class weights: {weights.cpu().numpy().round(2)}")
    loss_fn = nn.CrossEntropyLoss(weight=weights)

    Xt_t = torch.as_tensor(X_train, dtype=torch.float32, device=device)
    yt_t = torch.as_tensor(y_train, dtype=torch.long, device=device)
    Xv_t = torch.as_tensor(X_val, dtype=torch.float32, device=device)
    yv_t = torch.as_tensor(y_val, dtype=torch.long, device=device)

    history = []
    t0 = time.time()
    for ep in range(epochs):
        net.train()
        idx = torch.randperm(len(Xt_t), device=device)
        ep_loss, n_correct, n_total = 0.0, 0, 0
        for start in range(0, len(idx), batch_size):
            j = idx[start:start+batch_size]
            xb, yb = Xt_t[j], yt_t[j]
            logits, _ = net(xb)
            loss = loss_fn(logits, yb)
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item() * len(yb)
            n_correct += (logits.argmax(-1) == yb).sum().item()
            n_total += len(yb)
        train_loss = ep_loss / n_total
        train_acc = n_correct / n_total
        # Val
        net.eval()
        with torch.no_grad():
            v_logits, _ = net(Xv_t)
            v_loss = loss_fn(v_logits, yv_t).item()
            v_acc = (v_logits.argmax(-1) == yv_t).float().mean().item()
        elapsed = time.time() - t0
        history.append({"epoch": ep+1, "train_loss": train_loss, "train_acc": train_acc,
                        "val_loss": v_loss, "val_acc": v_acc, "elapsed_s": elapsed})
        print(f"ep {ep+1:2d}/{epochs}  loss={train_loss:.4f}  acc={train_acc:.3f}  "
              f"val_loss={v_loss:.4f}  val_acc={v_acc:.3f}  t={elapsed:.0f}s")

    out_path = out_path or "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt"
    torch.save({"model": net.state_dict(), "history": history}, out_path)
    with open(out_path.replace(".pt", "_history.json"), "w") as f:
        json.dump(history, f, indent=2)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    jsonl = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_trajectories.jsonl"
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    main(jsonl, epochs=epochs)
