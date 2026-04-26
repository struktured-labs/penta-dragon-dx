"""Gymnasium env wrapping PyBoy + Penta Dragon."""
from __future__ import annotations
import os
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pyboy import PyBoy

from .state import read_state, state_to_vector, vector_dim, GameState
from .reward import RewardConfig, RewardTracker


# Action space: 12 discrete actions
# 0-7: single buttons (A, B, Sel, Start, R, L, U, D)
# 8-11: common combos (UP+A, DOWN+A, LEFT+B, RIGHT+B)
ACTION_BUTTONS = [
    ["a"], ["b"], ["select"], ["start"],
    ["right"], ["left"], ["up"], ["down"],
    ["up", "a"], ["down", "a"], ["left", "b"], ["right", "b"],
]
N_ACTIONS = len(ACTION_BUTTONS)


# Hardcoded title-menu navigation sequence (verified working).
# Returns the schedule of (frame_range, button) tuples.
TITLE_NAV = [
    (180, 185, "down"),
    (193, 198, "a"),
    (241, 246, "a"),
    (291, 296, "a"),
    (341, 346, "start"),
    (391, 396, "a"),
]
TITLE_END_FRAME = 500  # buffer to settle into gameplay


class PentaEnv(gym.Env):
    """Penta Dragon DX gymnasium env via PyBoy.

    Observation: 59-dim float32 state vector (see state.state_to_vector).
    Action: discrete 12-way (single buttons + common combos).
    Reward: from reward.RewardTracker with configurable shaping.
    Episode terminates on: death (D880=0x17), max steps, or success (boss 16 killed).
    """
    metadata = {"render_modes": ["null", "SDL2"]}

    def __init__(
        self,
        rom_path: str,
        max_steps: int = 18000,           # ~5 min at 60 FPS / 4 frame skip
        frame_skip: int = 4,
        reward_cfg: RewardConfig | None = None,
        render_mode: str = "null",
        cgb: bool = True,
    ):
        super().__init__()
        self.rom_path = rom_path
        self.max_steps = max_steps
        self.frame_skip = frame_skip
        self.reward_tracker = RewardTracker(reward_cfg or RewardConfig())
        self.render_mode = render_mode
        self.cgb = cgb

        self.observation_space = spaces.Box(0.0, 1.0, (vector_dim(),), dtype=np.float32)
        self.action_space = spaces.Discrete(N_ACTIONS)

        self.pb: PyBoy | None = None
        self.steps = 0
        self._held = []  # currently held buttons

    # ---- core API ----

    def reset(self, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if self.pb is not None:
            self.pb.stop()
            self.pb = None
        self.pb = PyBoy(self.rom_path, window=self.render_mode, sound_emulated=False, cgb=self.cgb)
        self.reward_tracker.reset()
        self.steps = 0
        self._held = []

        # Auto-navigate title menu to gameplay
        self._run_title_nav()

        s = read_state(self.pb)
        # Initialize tracker with first state
        self.reward_tracker.last_state = s
        return state_to_vector(s), {"state": s}

    def step(self, action: int):
        # Release previously held buttons
        for b in self._held:
            self.pb.button_release(b)
        # Press new buttons
        self._held = ACTION_BUTTONS[action]
        for b in self._held:
            self.pb.button_press(b)
        # Tick frame_skip frames
        for _ in range(self.frame_skip):
            self.pb.tick()
        self.steps += 1
        # Read state + reward
        s = read_state(self.pb)
        reward, info = self.reward_tracker.step(s, action=action)
        # Termination
        terminated = (s.scene == 0x17)  # death cinematic
        # Truncated by max_steps
        truncated = self.steps >= self.max_steps
        # Success: killed boss 16 specifically (level 8, miniboss 16)
        success = (8, 16) in self.reward_tracker.unique_bosses_killed
        if success:
            terminated = True
            info["success"] = True
        info["state"] = s
        info["steps"] = self.steps
        return state_to_vector(s), reward, terminated, truncated, info

    def close(self):
        if self.pb is not None:
            self.pb.stop()
            self.pb = None

    # ---- helpers ----

    def _run_title_nav(self):
        """Run the verified title-menu input sequence to reach gameplay."""
        prev = None
        for f in range(TITLE_END_FRAME):
            cur = None
            for fr_lo, fr_hi, btn in TITLE_NAV:
                if fr_lo <= f <= fr_hi:
                    cur = btn
                    break
            if cur != prev:
                if prev is not None:
                    self.pb.button_release(prev)
                if cur is not None:
                    self.pb.button_press(cur)
                prev = cur
            self.pb.tick()
        if prev is not None:
            self.pb.button_release(prev)

    def get_state(self) -> GameState:
        return read_state(self.pb)

    def patch_rom(self, file_offset: int, value: int):
        """Bypass MBC and patch raw ROM byte. Useful for boss-16 spawn force."""
        # PyBoy's cart_data API
        self.pb.memory[file_offset] = value  # may not work for >0x7FFF
        # Fallback: direct cart access if available
        try:
            self.pb.cartridge.rom[file_offset] = value
        except (AttributeError, IndexError):
            pass
