# Copyright 2026 Human Systems. MIT License.
"""Nexus Model Advisor - Uses Nexus MCTS data for intelligent model selection.

This module reads Nexus's MCTS scores and provides model recommendations
based on historical performance data. It doesn't execute models, just advises
which one to use based on UCB1 scores from Nexus's accumulated data.
"""

import json
import math
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelRecommendation:
    """Recommendation from Nexus advisor."""

    model: str
    confidence: float
    avg_reward: float
    plays: int
    cold_start: bool
    alternatives: list[str]
    arm_key: str


class NexusAdvisor:
    """Advises on model selection using Nexus MCTS data.

    Reads the Nexus scores file (~/.opencode/mcts-scores.json) and provides
    UCB1-based model recommendations. This is read-only - it learns from
    Nexus's historical data without modifying it.
    """

    NEXUS_SCORES_PATH = os.path.expanduser("~/.opencode/mcts-scores.json")
    UCB1_C = math.sqrt(2)
    MIN_CONFIDENT_PLAYS = 5
    FRAMEWORK_MAP = {
        "coding": "coder",
        "implementation": "coder",
        "refactoring": "coder",
        "testing": "coder",
        "system_design": "architect",
        "architecture": "architect",
        "reverse_engineering": "reviewer",
        "debugging": "reviewer",
        "data_analysis": "reasoning",
        "trading_analysis": "arbitrage",
        "documentation": "writer",
        "reporting": "writer",
        "creative_writing": "creative",
        "general": "planner",
        "express": "express",
        "typescript": "express",
        "api": "express",
        "risk_analysis": "arbitrage",
        "python": "arbitrage",
    }

    def __init__(self, scores_path: Optional[str] = None):
        self.scores_path = scores_path or self.NEXUS_SCORES_PATH
        self._data: Optional[dict] = None
        self._load_data()

    def _load_data(self) -> None:
        """Load Nexus scores data."""
        if not os.path.exists(self.scores_path):
            self._data = {"version": 3, "totalPlays": 0, "arms": {}}
            return

        try:
            with open(self.scores_path, 'r') as f:
                self._data = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._data = {"version": 3, "totalPlays": 0, "arms": {}}

    def _get_framework(self, task_type: str) -> str:
        """Map Switchboard task type to Nexus framework."""
        return self.FRAMEWORK_MAP.get(task_type, "planner")

    def _calculate_ucb1(self, avg_reward: float, plays: int, total_plays: int, cold_start_ucb1: float = 0.0) -> float:
        if plays == 0:
            return cold_start_ucb1
        exploitation = avg_reward
        exploration = self.UCB1_C * math.sqrt(math.log(total_plays) / plays)
        return exploitation + exploration

    def recommend(
        self,
        task_type: str = "general",
        language: str = "python",
        complexity: int = 5,
    ) -> Optional[ModelRecommendation]:
        """Get model recommendation based on Nexus data.

        Args:
            task_type: Switchboard task type (coding, data_analysis, etc.)
            language: Programming language (python, typescript, etc.)
            complexity: Task complexity 1-10

        Returns:
            ModelRecommendation or None if no data available
        """
        if not self._data or not self._data.get("arms"):
            return None

        framework = self._get_framework(task_type)
        arms = self._data.get("arms", {})

        # First pass: find matching arms and compute framework-local total plays
        # Arm key format: "model/org::framework::optional-lang::optional-task"
        # parts[1] is always the framework in all patterns
        matching_arms = []
        for arm_key, arm_data in arms.items():
            parts = arm_key.split("::")
            if len(parts) >= 2 and parts[1] == framework:
                matching_arms.append((arm_key, arm_data))

        if not matching_arms:
            return None

        framework_total_plays = sum(a.get("plays", 0) for _, a in matching_arms)

        warm_max = 0.0
        for _, arm_data in matching_arms:
            plays = arm_data.get("plays", 0)
            if plays > 0:
                ucb1 = arm_data.get("avgReward", 0) + self.UCB1_C * math.sqrt(
                    math.log(max(framework_total_plays, 1)) / plays
                )
                if ucb1 > warm_max:
                    warm_max = ucb1

        cold_start_ucb1 = warm_max * 0.5 if warm_max > 0 else 2.0

        candidates = []
        for arm_key, arm_data in matching_arms:
            model_id = arm_key.split("::")[0]
            avg_reward = arm_data.get("avgReward", 0)
            plays = arm_data.get("plays", 0)
            ucb1_score = self._calculate_ucb1(avg_reward, plays, max(framework_total_plays, 1), cold_start_ucb1)

            candidates.append({
                "model": model_id,
                "arm_key": arm_key,
                "avg_reward": avg_reward,
                "plays": plays,
                "ucb1_score": ucb1_score,
            })

        candidates.sort(key=lambda x: (x["ucb1_score"], x["plays"], x["avg_reward"]), reverse=True)

        best = candidates[0]
        alternatives = [c["model"] for c in candidates[1:4]]

        # Calculate confidence based on plays
        confidence = min(best["plays"] / self.MIN_CONFIDENT_PLAYS, 1.0)
        cold_start = best["plays"] < self.MIN_CONFIDENT_PLAYS

        return ModelRecommendation(
            model=best["model"],
            confidence=confidence,
            avg_reward=best["avg_reward"],
            plays=best["plays"],
            cold_start=cold_start,
            alternatives=alternatives,
            arm_key=best["arm_key"],
        )

    def get_stats(self) -> dict:
        """Get summary stats from Nexus data."""
        if not self._data:
            return {"total_plays": 0, "arms_count": 0, "top_models": []}

        arms = self._data.get("arms", {})
        total_plays = self._data.get("totalPlays", 0)

        # Get top models by average reward
        model_scores = []
        for arm_key, arm_data in arms.items():
            model_scores.append({
                "model": arm_data.get("modelId", arm_key),
                "avg_reward": arm_data.get("avgReward", 0),
                "plays": arm_data.get("plays", 0),
            })

        model_scores.sort(key=lambda x: x["avg_reward"], reverse=True)

        return {
            "total_plays": total_plays,
            "arms_count": len(arms),
            "top_models": model_scores[:5],
        }


# Singleton instance for reuse
_advisor: Optional[NexusAdvisor] = None


def get_advisor() -> NexusAdvisor:
    """Get or create the singleton Nexus advisor."""
    global _advisor
    if _advisor is None:
        _advisor = NexusAdvisor()
    return _advisor


def recommend_model(
    task_type: str = "general",
    language: str = "python",
    complexity: int = 5,
) -> Optional[ModelRecommendation]:
    """Convenience function to get a model recommendation."""
    return get_advisor().recommend(task_type, language, complexity)


def get_nexus_stats() -> dict:
    """Convenience function to get Nexus stats."""
    return get_advisor().get_stats()
