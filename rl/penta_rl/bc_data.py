"""Convert recorded expert trajectories (JSONL) → numpy arrays for BC.

Schema must match state.state_to_vector exactly so the BC weights transfer to
PPO without modification.
"""
from __future__ import annotations
import json
import numpy as np
from .state import vector_dim


def jsonl_to_state_vec(d: dict) -> np.ndarray:
    """Build the 71-dim state vector from a recorded JSONL row.

    Mirrors state.state_to_vector exactly (must stay in sync).
    """
    parts = []
    # Scene one-hot (D880 ∈ {0x02, 0x0A, 0x17, 0x18})
    sc = d["D880"]
    parts.append(np.array([sc == 0x02, sc == 0x0A, sc == 0x17, sc == 0x18], dtype=np.float32))
    # Scalars
    parts.append(np.array([
        d["FFBA"] / 8.0, d["FFBD"] / 7.0, float(d["FFBE"]),
        d["FFC0"] / 3.0, float(d["FFC1"]), d["FFBF"] / 16.0,
    ], dtype=np.float32))
    # Combat
    player_hp = d["DCDD"] * 256 + d["DCDC"]
    parts.append(np.array([
        d["DCBB"] / 255.0, player_hp / (23 * 256 + 255), d["DCB8"] / 6.0,
    ], dtype=np.float32))
    # Scroll
    parts.append(np.array([
        d["FFAC"] / 255.0, d["FFAD"] / 255.0, d["FFCF"] / 255.0,
        d["SCY"] / 255.0, d["SCX"] / 255.0, d["DC04"] / 255.0,
    ], dtype=np.float32))
    # Slots (5 × 8 = 40)
    slots = np.array(d["slots"], dtype=np.float32) / 255.0
    parts.append(slots.flatten())
    # OAM features (12 dims) — match state.state_to_vector
    oam = d.get("oam", {})
    sara_x = oam.get("sara_x", -1); sara_y = oam.get("sara_y", -1)
    boss_x = oam.get("boss_x", -1); boss_y = oam.get("boss_y", -1)
    near_x = oam.get("near_x", -1); near_y = oam.get("near_y", -1)
    near_d = oam.get("near_dist", -1); proj_n = oam.get("proj_count", 0)
    boss_count = oam.get("boss_count", 0)
    if boss_x >= 0 and sara_x >= 0:
        bsx = (boss_x - sara_x) / 160.0; bsy = (boss_y - sara_y) / 144.0
    else:
        bsx = 0.0; bsy = 0.0
    parts.append(np.array([
        max(sara_x, 0) / 160.0, max(sara_y, 0) / 144.0,
        max(boss_x, 0) / 160.0, max(boss_y, 0) / 144.0,
        max(near_x, 0) / 160.0, max(near_y, 0) / 144.0,
        max(near_d, 0) / 200.0, proj_n / 10.0, boss_count / 8.0,
        bsx, bsy, 1.0 if boss_count > 0 else 0.0,
    ], dtype=np.float32))
    return np.concatenate(parts)


def load_dataset(jsonl_path: str, max_rows: int | None = None,
                 skip_title: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Load JSONL → (X, y) arrays. Drops title-menu rows where FFC1==0."""
    obs_rows = []
    actions = []
    n_skipped = 0
    with open(jsonl_path) as f:
        for i, line in enumerate(f):
            if not line.strip(): continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if skip_title and d["FFC1"] == 0:
                n_skipped += 1; continue
            obs_rows.append(jsonl_to_state_vec(d))
            actions.append(int(d["action"]))
            if max_rows is not None and len(obs_rows) >= max_rows: break
    X = np.stack(obs_rows)
    y = np.array(actions, dtype=np.int64)
    print(f"Loaded {len(X)} rows from {jsonl_path} (skipped {n_skipped} title-menu rows)")
    print(f"State shape: {X.shape}, action shape: {y.shape}")
    print(f"Action distribution: {np.bincount(y, minlength=12)}")
    assert X.shape[1] == vector_dim(), f"state dim mismatch: {X.shape[1]} vs {vector_dim()}"
    return X, y


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_trajectories.jsonl"
    X, y = load_dataset(path)
