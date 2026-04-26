"""Reward function for Penta Dragon RL."""
from __future__ import annotations
from dataclasses import dataclass, field
from .state import GameState


@dataclass
class RewardConfig:
    """Per-event reward weights. LLM coach can mutate these."""
    boss_kill: float = 5.0           # unique boss killed (DCBB → 0 with new FFBF)
    miniboss_enter: float = 0.5      # entered miniboss state (D880 → 0x0A)
    section_advance: float = 0.5     # DCB8 incremented
    room_change: float = 1.0         # FFBD changed
    level_change: float = 3.0        # FFBA changed
    boss_damage: float = 0.1         # DCBB decreased
    player_damage: float = -0.3      # player_hp decreased
    death: float = -5.0              # player_hp = 0 OR D880 → 0x17
    powerup_pickup: float = 0.5      # FFC0 went 0 → non-zero
    step_penalty: float = -0.001
    scroll_progress: float = 0.001   # SCY/SCX moved


@dataclass
class RewardTracker:
    """Tracks unique events to avoid double-counting."""
    cfg: RewardConfig = field(default_factory=RewardConfig)
    unique_bosses_killed: set = field(default_factory=set)
    last_state: GameState | None = None
    cumulative: float = 0.0
    event_log: list = field(default_factory=list)

    def step(self, state: GameState) -> tuple[float, dict]:
        """Compute reward for transition last_state → state.

        Returns (reward, info_dict).
        """
        cfg = self.cfg
        prev = self.last_state
        if prev is None:
            self.last_state = state
            return 0.0, {}

        r = 0.0
        events = []

        # Boss kill: DCBB hit 0 AND we have an active miniboss
        if prev.boss_hp > 0 and state.boss_hp == 0 and prev.miniboss != 0:
            key = (prev.level, prev.miniboss)
            if key not in self.unique_bosses_killed:
                self.unique_bosses_killed.add(key)
                r += cfg.boss_kill
                events.append(("boss_kill", key))
            # Boss damage taken into kill bonus too
        elif state.boss_hp < prev.boss_hp:
            delta = prev.boss_hp - state.boss_hp
            r += cfg.boss_damage * (delta / 16.0)

        # Miniboss enter
        if prev.miniboss == 0 and state.miniboss != 0:
            r += cfg.miniboss_enter
            events.append(("miniboss_enter", state.miniboss))

        # Section advance
        if state.section != prev.section:
            r += cfg.section_advance
            events.append(("section", state.section))

        # Room change
        if state.room != prev.room and state.room != 0:
            r += cfg.room_change
            events.append(("room", state.room))

        # Level change
        if state.level != prev.level:
            r += cfg.level_change
            events.append(("level", state.level))

        # Player damage
        if state.player_hp < prev.player_hp:
            r += cfg.player_damage * ((prev.player_hp - state.player_hp) / 256.0)

        # Death
        if state.scene == 0x17 and prev.scene != 0x17:
            r += cfg.death
            events.append(("death", None))

        # Powerup pickup
        if prev.powerup == 0 and state.powerup != 0:
            r += cfg.powerup_pickup
            events.append(("powerup", state.powerup))

        # Scroll progress
        if state.scy != prev.scy or state.scx != prev.scx:
            r += cfg.scroll_progress

        # Step penalty
        r += cfg.step_penalty

        self.cumulative += r
        self.last_state = state
        if events:
            self.event_log.append(events)
        return r, {"events": events, "cumulative": self.cumulative,
                   "n_unique_bosses": len(self.unique_bosses_killed)}

    def reset(self):
        self.unique_bosses_killed.clear()
        self.last_state = None
        self.cumulative = 0.0
        self.event_log.clear()
