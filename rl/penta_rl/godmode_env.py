"""PentaEnv subclass that injects godmode every tick, uses an explore-heavy reward.

godmode (per tick):
- HP infinite (DCDD/DCDC)
- Corridor timer never expires (DCBB clamped when no boss)
- DD06=0 (release scroll lock)
- DCDF/DCDE max (freeze timer cascade)
- Auto-finish near-death boss
- Death-scene revert (0x17 → 0x02)

Reward additions vs base reward.py:
- unique_room: +50 (was +0.5) — exploration is the primary signal
- arena_enter: +1000 — the goal
- room_change: tiny per change (avoid oscillation farming)
"""
from __future__ import annotations
import numpy as np
import gymnasium as gym
from .env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from .state import read_state, state_to_vector
from .reward import RewardConfig, RewardTracker


def godmode_step(pb):
    """Inject god-mode: infinite HP + corridor timer never expires.
    Policy must learn items/Dragon naturally.
    """
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFE6] = 0xFF
    pb.memory[0xDCDF] = 0xFF
    pb.memory[0xDCDE] = 0xFF
    pb.memory[0xDD06] = 0
    if pb.memory[0xFFBF] == 0:
        pb.memory[0xDCBB] = 0xFF
    elif pb.memory[0xDCBB] < 0x20 and pb.memory[0xD880] in (0x0A, 0x0B):
        pb.memory[0xFFBF] = 0
        pb.memory[0xDCBB] = 0xFF
    if pb.memory[0xD880] == 0x17:
        pb.memory[0xD880] = 0x02
        pb.memory[0xDCBB] = 0xFF


class GodmodeEnv(PentaEnv):
    """PentaEnv with per-tick godmode injection."""

    def step(self, action: int):
        # Release previously held buttons, press new ones
        for b in self._held:
            self.pb.button_release(b)
        self._held = ACTION_BUTTONS[action]
        for b in self._held:
            self.pb.button_press(b)
        # Tick frame_skip times with godmode injected each tick
        for _ in range(self.frame_skip):
            godmode_step(self.pb)
            self.pb.tick()
        self.steps += 1
        s = read_state(self.pb)
        reward, info = self.reward_tracker.step(s, action=action)
        # Extra reward shaping: big bonus for arena entry, room exploration
        if 0x0C <= s.scene <= 0x14:
            # arena entry (would also fire as STAGE_ARENA_ENTER in base reward)
            pass  # base reward already gives 30 — add to it
        # Termination only via success or max_steps; no death-induced termination
        # because godmode prevents 0x17 from sticking
        truncated = self.steps >= self.max_steps
        success = (8, 16) in self.reward_tracker.unique_bosses_killed or \
                  (any(0x0C <= s.scene <= 0x14 for _ in [None]))  # any arena = success-ish
        terminated = success
        if success:
            info["success"] = True
        info["state"] = s
        info["steps"] = self.steps
        return state_to_vector(s), reward, terminated, truncated, info


def explore_reward_config() -> RewardConfig:
    """RewardConfig tuned for exploration: heavy room/arena bonuses."""
    cfg = RewardConfig()
    # Existing: stage_boss_arena_enter = 30. Bump it.
    cfg.stage_boss_arena_enter = 1000.0
    # Unique room: big bump from 0.5 to 50 — exploration is THE goal
    cfg.unique_room = 50.0
    # Reduce step penalty (give Sara time to explore)
    cfg.step_penalty = -0.001
    # Reduce kill-related rewards (we have godmode, kills are easy)
    cfg.boss_kill = 10.0  # was 100
    cfg.boss_kill_chain = 20.0  # was 200
    cfg.boss_phase_2 = 1.0
    cfg.boss_phase_3 = 1.0
    cfg.boss_phase_4 = 1.0
    cfg.boss_damage = 0.0  # avoid damage farming
    return cfg
