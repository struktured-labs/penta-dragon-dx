"""Curriculum learning: staged reward configs + advancement criteria."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from .reward import RewardConfig


@dataclass
class CurriculumStage:
    name: str
    reward_cfg: RewardConfig
    advance_when: dict   # e.g., {"max_bosses_20": 1} = advance when max recent bosses >= 1
    min_epochs: int = 5  # don't advance until this many epochs in stage


# Default curriculum: 5 stages from "survive" to "kill all 16"
DEFAULT_CURRICULUM = [
    CurriculumStage(
        name="survive",
        reward_cfg=RewardConfig(
            boss_kill=0, miniboss_enter=0,
            section_advance=0.1, room_change=0.5, level_change=2.0,
            boss_damage=0, player_damage=-0.1, death=-3.0,
            powerup_pickup=0.2, step_penalty=0.001,  # POSITIVE step reward
            scroll_progress=0.005,
        ),
        advance_when={"mean_return_20": 200},
        min_epochs=5,
    ),
    CurriculumStage(
        name="navigate",
        reward_cfg=RewardConfig(
            boss_kill=1, miniboss_enter=0.5,
            section_advance=0.5, room_change=2.0, level_change=5.0,
            boss_damage=0.05, player_damage=-0.2, death=-3.0,
            powerup_pickup=0.5, step_penalty=-0.0005,
            scroll_progress=0.002,
        ),
        advance_when={"mean_return_20": 400},
        min_epochs=5,
    ),
    CurriculumStage(
        name="engage",
        reward_cfg=RewardConfig(
            boss_kill=5, miniboss_enter=1.0,
            section_advance=0.3, room_change=0.5, level_change=3.0,
            boss_damage=0.5, player_damage=-0.3, death=-5.0,
            powerup_pickup=0.5, step_penalty=-0.001,
            scroll_progress=0.001,
        ),
        advance_when={"max_bosses_20": 1},
        min_epochs=10,
    ),
    CurriculumStage(
        name="combat",
        reward_cfg=RewardConfig(
            boss_kill=10, miniboss_enter=2.0,
            section_advance=0.2, room_change=0.5, level_change=3.0,
            boss_damage=0.5, player_damage=-0.3, death=-5.0,
            powerup_pickup=0.5, step_penalty=-0.001,
            scroll_progress=0.001,
        ),
        advance_when={"mean_bosses_20": 1.5},
        min_epochs=15,
    ),
    CurriculumStage(
        name="master",
        reward_cfg=RewardConfig(
            boss_kill=20, miniboss_enter=3.0,
            section_advance=0.1, room_change=0.3, level_change=5.0,
            boss_damage=0.5, player_damage=-0.3, death=-10.0,
            powerup_pickup=0.5, step_penalty=-0.001,
            scroll_progress=0.0005,
        ),
        advance_when={},  # final stage
        min_epochs=100,
    ),
]


class CurriculumScheduler:
    def __init__(self, stages: list[CurriculumStage] = None):
        self.stages = stages or DEFAULT_CURRICULUM
        self.idx = 0
        self.epochs_in_stage = 0

    @property
    def current(self) -> CurriculumStage:
        return self.stages[self.idx]

    def step(self, recent_metric: dict) -> tuple[bool, str]:
        """Returns (advanced, reason)."""
        self.epochs_in_stage += 1
        cur = self.current
        if self.idx >= len(self.stages) - 1:
            return False, ""
        if self.epochs_in_stage < cur.min_epochs:
            return False, ""
        # Check advancement conditions
        for key, threshold in cur.advance_when.items():
            val = recent_metric.get(key, 0)
            if val < threshold:
                return False, f"need {key}>={threshold}, have {val}"
        self.idx += 1
        prev_name = cur.name
        self.epochs_in_stage = 0
        return True, f"advanced {prev_name} → {self.current.name}"
