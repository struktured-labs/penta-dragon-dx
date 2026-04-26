"""LLM coach via Anthropic Claude API.

Periodically inspects training metrics + state samples and returns
structured suggestions for reward shaping, sub-goals, or env tweaks.
"""
from __future__ import annotations
import json, os
from dataclasses import asdict
from .reward import RewardConfig

try:
    import anthropic
except ImportError:
    anthropic = None


COACH_SYSTEM = """You are an RL coach for a PPO agent learning to play Penta Dragon DX (a Game Boy action-RPG with 8 levels and 16 mini-bosses).

Your job: inspect recent training metrics + game-state samples and return STRUCTURED JSON guidance to accelerate learning.

Return a JSON object with these optional keys:
- reward_cfg_delta: dict of RewardConfig field overrides (e.g., {"boss_kill": 10.0})
- subgoal: short string describing what the agent should focus on next
- diagnosis: short string explaining a stuck pattern (if any)
- action_bias: list of (action_idx, multiplier) to bias action sampling (e.g., to encourage attacking)
- patches: list of {addr: int, value: int, reason: str} for ROM patches (rare)

Be terse. Maximum 200 tokens per response. Don't suggest changes if the agent is making clear progress.

Game-specific knowledge:
- Action 0 = A (attack/projectile), Action 1 = B (cancel/secondary)
- Movement: 4 (right), 5 (left), 6 (up), 7 (down)
- Combos: 8 (up+a), 9 (down+a), 10 (left+b), 11 (right+b)
- D880=0x02 = normal gameplay; 0x0A = mini-boss combat; 0x17 = death
- FFBF = 0 normal; 1-15 valid mini-boss; 16 = boss 16 (collision broken without ROM patch)
- Killing boss 16 normally requires patching ROM 0x2D7F+1,4,7,10,13 from 0x00 to non-zero (hitbox fix)
- Powerups (FFC0): 1=spiral, 2=shield, 3=turbo
- Death cinematic delay: 180-450 frames after DCBB=0
"""


class LLMCoach:
    def __init__(self, model: str = "claude-opus-4-7", api_key: str | None = None):
        if anthropic is None:
            self.client = None
            print("[coach] anthropic not installed; using heuristic-only coach")
            return
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.history = []

    def is_available(self) -> bool:
        return self.client is not None

    def coach(self, recent_metrics: list[dict], reward_cfg: RewardConfig,
              recent_events: list[list[tuple[int, str]]] | None = None,
              extra_context: str = "") -> dict:
        """Send a coaching request to the LLM and return structured guidance.

        Falls back to heuristic if no LLM available.
        """
        if self.client is None:
            return self._heuristic_coach(recent_metrics, reward_cfg)

        prompt = self._build_prompt(recent_metrics, reward_cfg, recent_events, extra_context)
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system=COACH_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text if resp.content else ""
            # Try to extract JSON from response
            guidance = self._parse_json(text)
            self.history.append({"prompt": prompt, "response": text, "parsed": guidance})
            return guidance
        except Exception as e:
            print(f"[coach] API error: {e}; falling back to heuristic")
            return self._heuristic_coach(recent_metrics, reward_cfg)

    def _build_prompt(self, recent_metrics, reward_cfg, recent_events, extra_context):
        m = recent_metrics[-5:] if len(recent_metrics) >= 5 else recent_metrics
        evs = recent_events[-3:] if recent_events else []
        return f"""Recent metrics (last {len(m)} epochs):
{json.dumps(m, indent=2)}

Current reward config:
{json.dumps(asdict(reward_cfg), indent=2)}

Recent event samples:
{json.dumps(evs, indent=2, default=str)[:1000]}

{extra_context}

Return JSON guidance now."""

    def _parse_json(self, text: str) -> dict:
        """Extract first JSON object from text."""
        try:
            # Look for first { and matching }
            start = text.find("{")
            if start < 0:
                return {}
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{": depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return json.loads(text[start:i+1])
        except Exception as e:
            print(f"[coach] JSON parse error: {e}")
        return {}

    def _heuristic_coach(self, recent_metrics, reward_cfg) -> dict:
        """Simple non-LLM fallback."""
        if len(recent_metrics) < 3:
            return {}
        last3 = recent_metrics[-3:]
        mean_ret = sum(m.get("mean_return_10", 0) for m in last3) / 3
        max_bosses = max(m.get("max_bosses_10", 0) for m in last3)

        guidance = {}
        if max_bosses == 0 and mean_ret < 200:
            # Stuck — boost combat reward
            guidance["reward_cfg_delta"] = {"boss_kill": 10.0, "miniboss_enter": 1.0}
            guidance["subgoal"] = "Reach and engage first mini-boss (gargoyle)"
            guidance["diagnosis"] = "No bosses killed, low return — agent likely not attacking"
            guidance["action_bias"] = [[0, 2.0]]  # boost A button
        elif max_bosses < 2:
            guidance["subgoal"] = "Kill multiple mini-bosses in single episode"
        return guidance

    def apply(self, guidance: dict, reward_cfg: RewardConfig) -> RewardConfig:
        """Apply guidance to reward config (mutates and returns new copy)."""
        delta = guidance.get("reward_cfg_delta", {})
        if not delta:
            return reward_cfg
        new = RewardConfig(**asdict(reward_cfg))
        for k, v in delta.items():
            if hasattr(new, k):
                setattr(new, k, float(v))
        return new
