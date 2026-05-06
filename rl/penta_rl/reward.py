"""Reward function for Penta Dragon RL.

v2 redesign (post-eval-regression):
- Boss damage and kill dominate vs survival rewards
- Phase-milestone bonuses (DCBB drops below 0xC0, 0x80) to ladder partial progress
- True damage tracking (ignore phase reset upward jumps)
- DCB8-advance kill detection (more accurate than DCBB→0)
- Form transform bonus (Dragon = big deal per walkthrough)
- Less generous survival incentive (penalize dawdling more)
- B-button (Mega-Flash) usage bonus
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .state import GameState


@dataclass
class RewardConfig:
    """Per-event reward weights (v2)."""
    # Combat — primary signal
    # v4: kill bonus dominates; per-frame "fire" / "b_button" / "dragon_active" rewards
    # ZEROED because v17 found a reward hack — stay in fight forever, spam fire,
    # accumulate +400/8000 frames vs +50 for actual kill. Now killing is the only big payoff.
    boss_kill: float = 100.0         # was 50
    boss_kill_chain: float = 200.0   # was 75 — multi-kill should DOMINATE
    boss_damage: float = 0.5         # was 2.0 — DCBB delta is noisy (level timer dual purpose)
    boss_phase_2: float = 10.0       # was 5
    boss_phase_3: float = 20.0       # was 10
    boss_phase_4: float = 40.0       # was 15 — phase 4 is "almost dead"
    miniboss_enter: float = 1.0
    fire_in_combat: float = 0.0      # was 0.05 — REMOVED, was exploited

    # Survival / death (REVERTED to v4 baseline; v6 bump didn't help breakthrough)
    death: float = -20.0             # D880 → 0x17
    player_damage: float = -0.5      # per 256-unit HP loss
    step_penalty: float = -0.005     # 5x prior; dawdling is bad

    # Progression — kept positive but smaller (REVERTED to v4)
    # v5/v5b experiments (section_advance=25) caused oscillation exploit OR over-bias
    # away from kills. v4 reward is the proven baseline.
    section_advance: float = 0.3
    section_max_reached: float = 0.5
    unique_room: float = 0.5
    room_change: float = 0.01
    level_change: float = 10.0       # rare event, big reward

    # Powerup
    powerup_pickup_from_zero: float = 1.5
    powerup_pickup_swap: float = 0.0
    form_transform_dragon: float = 8.0
    dragon_active_step: float = 0.0   # was 0.005 — REMOVED, per-frame exploit

    # B button (Mega-Flash candidate)
    b_button: float = 0.0            # was 0.02 — REMOVED, per-frame exploit

    # Anti-cheese
    scroll_progress: float = 0.0

    # Stage boss progression (long-horizon — D880 0x0C-0x14 = stage boss arenas per arch doc)
    stage_boss_arena_enter: float = 30.0   # first time D880 enters any 0x0C..0x14
    stage_boss_kill: float = 200.0         # D880 transitions from arena to 0x16 (post-boss reload)
    final_boss_penta_dragon: float = 1000.0 # FFBA=8 arena complete (Penta Dragon defeated)
    stage_boss_splash: float = 5.0          # D880 → 0x18 (cinematic splash)


@dataclass
class RewardTracker:
    """Tracks unique events to avoid double-counting."""
    cfg: RewardConfig = field(default_factory=RewardConfig)
    unique_bosses_killed: set = field(default_factory=set)
    visited_rooms: set = field(default_factory=set)
    max_section: int = 0
    last_state: GameState | None = None
    cumulative: float = 0.0
    event_log: list = field(default_factory=list)
    # Per-fight tracking
    cur_boss_section: int = -1   # which DCB8 (2 or 5) was last seen with FFBF active
    cur_boss_min_hp: int = 0xFF  # lowest DCBB seen in current fight (for true damage)
    cur_boss_phase: int = 1      # phase milestones already triggered
    # Stage boss tracking
    stage_arenas_entered: set = field(default_factory=set)  # set of D880 values 0x0C..0x14
    stage_bosses_killed: set = field(default_factory=set)  # FFBA values where we transitioned arena → 0x16

    def step(self, state: GameState, action: int = -1) -> tuple[float, dict]:
        cfg = self.cfg
        prev = self.last_state
        if prev is None:
            self.last_state = state
            self.visited_rooms.add((state.level, state.room))
            return 0.0, {}

        r = 0.0
        events = []

        # ── Combat: kill detection via FFBF transition non-zero → zero ──
        # This is the canonical signal used by autoplay scripts that killed all 16 mini-bosses.
        # FFBF clears ~6 frames BEFORE DCB8 advances, so DCB8-based detection misses entirely.
        if prev.miniboss != 0 and state.miniboss == 0:
            key = (prev.level, prev.miniboss)
            if key not in self.unique_bosses_killed:
                if len(self.unique_bosses_killed) > 0:
                    r += cfg.boss_kill_chain
                    events.append(("BOSS_KILL_CHAIN", key, len(self.unique_bosses_killed)+1))
                else:
                    r += cfg.boss_kill
                    events.append(("BOSS_KILL", key, "via FFBF→0"))
                self.unique_bosses_killed.add(key)
            self.cur_boss_min_hp = 0xFF
            self.cur_boss_phase = 1

        # ── Boss damage: TRUE downward DCBB delta (ignore phase reset jumps) ──
        if prev.miniboss != 0 and state.miniboss != 0:
            # Track new minimum
            if state.boss_hp < self.cur_boss_min_hp:
                # Genuine progress: count chunks below previous min
                progress = self.cur_boss_min_hp - state.boss_hp
                r += cfg.boss_damage * (progress / 16.0)
                self.cur_boss_min_hp = state.boss_hp
                # Phase milestones
                if state.boss_hp < 0xC0 and self.cur_boss_phase < 2:
                    r += cfg.boss_phase_2; self.cur_boss_phase = 2
                    events.append(("phase_2", state.boss_hp))
                if state.boss_hp < 0x80 and self.cur_boss_phase < 3:
                    r += cfg.boss_phase_3; self.cur_boss_phase = 3
                    events.append(("phase_3", state.boss_hp))
                if state.boss_hp < 0x40 and self.cur_boss_phase < 4:
                    r += cfg.boss_phase_4; self.cur_boss_phase = 4
                    events.append(("phase_4", state.boss_hp))

        # ── Miniboss enter ──
        if prev.miniboss == 0 and state.miniboss != 0:
            r += cfg.miniboss_enter
            self.cur_boss_min_hp = state.boss_hp
            self.cur_boss_phase = 1
            events.append(("miniboss_enter", state.miniboss))

        # ── Fire bonus only in combat ──
        if action == 0 and state.miniboss != 0:
            r += cfg.fire_in_combat

        # ── B button (Mega-Flash candidate) ──
        if action == 1:
            r += cfg.b_button

        # ── Section advance (excluding boss-kill case which gave kill bonus) ──
        if state.section != prev.section and prev.section not in (2, 5):
            r += cfg.section_advance
            events.append(("section", state.section))
        if state.section > self.max_section:
            r += cfg.section_max_reached * (state.section - self.max_section)
            self.max_section = state.section

        # ── Room ──
        if state.room != prev.room and state.room != 0:
            r += cfg.room_change
        rkey = (state.level, state.room)
        if rkey not in self.visited_rooms:
            self.visited_rooms.add(rkey)
            r += cfg.unique_room
            events.append(("unique_room", rkey))

        # ── Level change (rare, big) ──
        if state.level != prev.level:
            r += cfg.level_change
            events.append(("level", state.level))

        # ── Player damage ──
        if state.player_hp < prev.player_hp:
            r += cfg.player_damage * ((prev.player_hp - state.player_hp) / 256.0)

        # ── Death ──
        if state.scene == 0x17 and prev.scene != 0x17:
            r += cfg.death
            events.append(("death", None))

        # ── Stage boss arena entry (D880 → 0x0C..0x14) ──
        if 0x0C <= state.scene <= 0x14 and state.scene != prev.scene:
            if state.scene not in self.stage_arenas_entered:
                self.stage_arenas_entered.add(state.scene)
                r += cfg.stage_boss_arena_enter
                events.append(("STAGE_ARENA_ENTER", hex(state.scene), state.level))
        # ── Stage boss splash (D880 → 0x18) ──
        if state.scene == 0x18 and prev.scene != 0x18:
            r += cfg.stage_boss_splash
            events.append(("stage_boss_splash",))
        # ── Stage boss kill: D880 transitions FROM arena TO 0x16 (post-boss reload) ──
        if 0x0C <= prev.scene <= 0x14 and state.scene == 0x16:
            if prev.level not in self.stage_bosses_killed:
                self.stage_bosses_killed.add(prev.level)
                r += cfg.stage_boss_kill
                events.append(("STAGE_BOSS_KILL", prev.level, hex(prev.scene)))
                # Final boss = FFBA=8 (Penta Dragon, D880=0x14)
                if prev.level == 8:
                    r += cfg.final_boss_penta_dragon
                    events.append(("FINAL_BOSS_PENTA_DRAGON_DEFEATED",))

        # ── Powerup pickup (tiered: from-zero vs swap) ──
        if prev.powerup == 0 and state.powerup != 0:
            r += cfg.powerup_pickup_from_zero
            events.append(("powerup_from_zero", state.powerup))
        elif prev.powerup != 0 and state.powerup != prev.powerup and state.powerup != 0:
            r += cfg.powerup_pickup_swap

        # ── Form transform to Dragon ──
        if prev.form == 0 and state.form == 1:
            r += cfg.form_transform_dragon
            events.append(("dragon_transform",))
        if state.form == 1:
            r += cfg.dragon_active_step

        # ── Step penalty ──
        r += cfg.step_penalty

        # ── Scroll (zero by default in v2) ──
        if state.scy != prev.scy or state.scx != prev.scx:
            r += cfg.scroll_progress

        self.cumulative += r
        self.last_state = state
        if events:
            self.event_log.append(events)
        return r, {"events": events, "cumulative": self.cumulative,
                   "n_unique_bosses": len(self.unique_bosses_killed)}

    def reset(self):
        self.unique_bosses_killed.clear()
        self.visited_rooms.clear()
        self.max_section = 0
        self.last_state = None
        self.cumulative = 0.0
        self.event_log.clear()
        self.cur_boss_section = -1
        self.cur_boss_min_hp = 0xFF
        self.cur_boss_phase = 1
        self.stage_arenas_entered.clear()
        self.stage_bosses_killed.clear()
