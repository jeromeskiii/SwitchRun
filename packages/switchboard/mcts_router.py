# Copyright 2026 Human Systems. MIT License.
"""MCTS-based model router for intelligent LLM selection.

Integrates MCTS algorithms from RLBotPack with Switchboard routing
to dynamically select optimal models based on task characteristics.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from switchboard.config import SwitchboardConfig

try:
    from photonic import MCTS_RESULT, PhotonicBus, PhotonicEvent
    _PHOTONIC_AVAILABLE = True
except ImportError:
    _PHOTONIC_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Specification for an LLM model."""

    id: str
    name: str
    provider: str
    cost_per_1k_tokens: float
    avg_latency_ms: float
    strengths: frozenset[str] = field(default_factory=frozenset)
    context_window: int = 4096


@dataclass
class TaskFeatures:
    """Extracted features from a task for model selection."""

    complexity: str  # "low", "medium", "high"
    estimated_tokens: int
    requires_code: bool
    requires_creativity: bool
    requires_reasoning: bool
    domain: str  # "coding", "analysis", "writing", "general"
    urgency: str  # "low", "medium", "high" (affects latency preference)


@dataclass
class SelectionResult:
    """Result of MCTS model selection."""

    model: ModelSpec
    confidence: float
    expected_reward: float
    simulations_run: int
    selection_path: list[str]


class ModelSelectionMCTS:
    """MCTS-based model selector for optimal LLM routing.

    State: (task_features_hash, selected_model_chain)
    Action: Select next model to evaluate
    Reward: Performance metric combining accuracy, cost, and latency
    """

    def __init__(
        self,
        available_models: list[ModelSpec],
        config: Optional[SwitchboardConfig] = None,
        budget: int = 100,
        exploration_constant: float = 1.414,
    ):
        self.models = {m.id: m for m in available_models}
        self.model_ids = list(self.models.keys())
        self.config = config or SwitchboardConfig()
        self.budget = budget
        self.c = exploration_constant
        self._history: dict[str, dict] = {}  # Track past selections

        # Performance tracking for online learning
        self.model_performance: dict[str, list[float]] = {m.id: [] for m in available_models}

    class Node:
        """Node in the MCTS tree."""

        def __init__(
            self,
            state: tuple[str, tuple[str, ...]],
            parent: Optional["ModelSelectionMCTS.Node"] = None,
            action: Optional[str] = None,
        ):
            self.state = state  # (task_hash, (model_1, model_2, ...))
            self.parent = parent
            self.action = action  # Model ID selected at this node
            self.children: list[ModelSelectionMCTS.Node] = []
            self.visits = 0
            self.total_reward = 0.0
            self.untried_actions: Optional[list[str]] = None

    def select_model(
        self,
        task_features: TaskFeatures,
        reward_func: Optional[Callable[[str, TaskFeatures], float]] = None,
        timeout_ms: int = 500,
    ) -> SelectionResult:
        """Select optimal model using MCTS.

        Args:
            task_features: Characteristics of the task
            reward_func: Optional custom reward function(model_id, features) -> float
            timeout_ms: Maximum time to spend on MCTS search (default 500ms)

        Returns:
            SelectionResult with chosen model and metadata
        """
        task_hash = self._hash_task(task_features)
        root_state = (task_hash, ())

        # Use default reward function if none provided
        evaluate = reward_func or self._default_reward

        # Build tree
        root = self.Node(root_state)
        root.untried_actions = self.model_ids.copy()

        # Track both iterations and time
        start_time = time.time()
        timeout_seconds = timeout_ms / 1000.0
        simulations_run = 0

        for iteration in range(self.budget):
            # Check time budget
            if time.time() - start_time > timeout_seconds:
                logger.debug(
                    f"MCTS timeout after {simulations_run} simulations "
                    f"({(time.time() - start_time)*1000:.1f}ms elapsed)"
                )
                break

            # Selection: Traverse tree using UCB1
            node = self._select(root)

            # Expansion: Add child if possible
            if node.untried_actions:
                node = self._expand(node)

            # Simulation: Evaluate this model choice
            if node.action:
                reward = evaluate(node.action, task_features)
            else:
                reward = 0.0

            # Backpropagation
            self._backprop(node, reward)
            simulations_run += 1

        # Select best model (most visited)
        if not root.children:
            # Fallback: use heuristic selection
            best_model = self._heuristic_select(task_features)
            return SelectionResult(
                model=best_model,
                confidence=0.5,
                expected_reward=0.0,
                simulations_run=simulations_run,
                selection_path=["heuristic_fallback"],
            )

        best_child = max(root.children, key=lambda n: n.visits)
        if not best_child.action:
            raise RuntimeError("Best child has no action assigned")
        best_model = self.models[best_child.action]

        # Calculate confidence based on visit distribution
        total_visits = sum(c.visits for c in root.children)
        confidence = best_child.visits / total_visits if total_visits > 0 else 0.0

        # Build selection path
        path = self._get_selection_path(best_child)

        result = SelectionResult(
            model=best_model,
            confidence=confidence,
            expected_reward=best_child.total_reward / max(best_child.visits, 1),
            simulations_run=simulations_run,
            selection_path=path,
        )

        self._emit_mcts_result(result, task_features)
        return result

    def _select(self, node: Node) -> Node:
        """Select node using UCB1 algorithm."""
        while node.children and not node.untried_actions:
            node = self._ucb_select(node)
        return node

    def _ucb_select(self, node: Node) -> Node:
        """Select child with highest UCB1 score."""
        parent_visits = max(node.visits, 1)
        best_score = -float("inf")
        best_child = None

        for child in node.children:
            exploitation = child.total_reward / max(child.visits, 1)
            exploration = self.c * np.sqrt(np.log(parent_visits) / max(child.visits, 1))
            score = exploitation + exploration

            if score > best_score:
                best_score = score
                best_child = child

        return best_child or node

    def _expand(self, node: Node) -> Node:
        """Expand node by adding a child."""
        if not node.untried_actions:
            return node

        # Select untried action (randomize to avoid bias toward first-listed model)
        action = node.untried_actions.pop(random.randint(0, len(node.untried_actions) - 1))

        # Create new state
        task_hash, model_chain = node.state
        new_chain = model_chain + (action,)
        new_state = (task_hash, new_chain)

        # Create child node
        child = self.Node(new_state, parent=node, action=action)
        child.untried_actions = [m for m in self.model_ids if m not in new_chain]
        node.children.append(child)

        return child

    def _backprop(self, node: Optional[Node], reward: float) -> None:
        """Backpropagate reward up the tree."""
        while node is not None:
            node.visits += 1
            node.total_reward += reward
            node = node.parent

    def _default_reward(self, model_id: str, features: TaskFeatures) -> float:
        """Calculate default reward for model-task pairing.

        Combines:
        - Capability match (does model excel at this domain?)
        - Cost efficiency
        - Latency appropriateness
        - Historical performance
        """
        model = self.models[model_id]

        # Capability match score (0-1)
        capability_score = self._capability_match(model, features)

        # Cost efficiency (normalized, higher is better)
        max_cost = max(m.cost_per_1k_tokens for m in self.models.values())
        cost_score = 1.0 - (model.cost_per_1k_tokens / max_cost)

        # Latency score (based on urgency)
        latency_score = self._latency_score(model, features)

        # Historical performance (if available)
        historical_score = self._historical_score(model_id)

        # Weighted combination
        weights = {
            "capability": 0.4,
            "cost": 0.2,
            "latency": 0.2,
            "historical": 0.2,
        }

        total_reward = (
            weights["capability"] * capability_score
            + weights["cost"] * cost_score
            + weights["latency"] * latency_score
            + weights["historical"] * historical_score
        )

        return total_reward

    def _capability_match(self, model: ModelSpec, features: TaskFeatures) -> float:
        """Score how well model capabilities match task requirements."""
        score = 0.0

        # Domain match
        if features.domain in model.strengths:
            score += 0.5

        # Complexity match
        if features.complexity == "high" and "reasoning" in model.strengths:
            score += 0.3
        elif features.complexity == "low":
            score += 0.2  # Simple tasks don't need powerful models

        # Context window check
        if features.estimated_tokens <= model.context_window * 0.8:
            score += 0.2

        return min(score, 1.0)

    def _latency_score(self, model: ModelSpec, features: TaskFeatures) -> float:
        """Score based on whether latency meets urgency requirements."""
        if features.urgency == "high":
            # Prefer fast models for urgent tasks
            max_latency = max(m.avg_latency_ms for m in self.models.values())
            return 1.0 - (model.avg_latency_ms / max_latency)
        elif features.urgency == "low":
            # Latency less important
            return 0.8
        else:
            # Medium urgency
            latencies = [m.avg_latency_ms for m in self.models.values()]
            median_latency = np.median(latencies) if latencies else 0.0
            
            # Guard against division by zero
            if median_latency == 0.0:
                logger.debug("Median latency is 0, returning neutral score")
                return 0.5
            
            latency_diff = abs(model.avg_latency_ms - median_latency)
            # Clamp to [0, 1] to prevent scores > 1
            return max(0.0, min(1.0, 1.0 - latency_diff / median_latency))

    def _historical_score(self, model_id: str) -> float:
        """Score based on historical performance."""
        history = self.model_performance.get(model_id, [])
        if not history:
            return 0.5  # Neutral if no history

        # Return moving average of recent performance
        recent = history[-10:]  # Last 10 evaluations
        return sum(recent) / len(recent)

    def _heuristic_select(self, features: TaskFeatures) -> ModelSpec:
        """Heuristic model selection when MCTS fails."""
        # Score each model
        scores = {model_id: self._default_reward(model_id, features) for model_id in self.model_ids}

        best_id = max(scores.items(), key=lambda x: x[1])[0]
        return self.models[best_id]

    def _get_selection_path(self, node: Node) -> list[str]:
        """Reconstruct path from root to node."""
        path = []
        current = node
        while current is not None:
            if current.action:
                path.append(current.action)
            current = current.parent
        return list(reversed(path))

    def _hash_task(self, features: TaskFeatures) -> str:
        """Create hash of task features for state identification."""
        feature_str = (
            f"{features.complexity}:{features.domain}:{features.estimated_tokens}:"
            f"{features.urgency}:{features.requires_code}:{features.requires_creativity}:"
            f"{features.requires_reasoning}"
        )
        return hashlib.sha256(feature_str.encode()).hexdigest()[:16]

    def _emit_mcts_result(self, result: SelectionResult, features: TaskFeatures) -> None:
        """Emit a Photonic MCTS_RESULT event; silently skipped if photonic is unavailable."""
        if not _PHOTONIC_AVAILABLE:
            return
        try:
            PhotonicBus.instance().emit(PhotonicEvent(
                type=MCTS_RESULT,
                source="switchboard/mcts_router",
                payload={
                    "selected_model": result.model.id,
                    "provider": result.model.provider,
                    "confidence": round(result.confidence, 4),
                    "expected_reward": round(result.expected_reward, 4),
                    "simulations": result.simulations_run,
                    "domain": features.domain,
                    "complexity": round(features.complexity, 2),
                },
            ))
        except Exception as exc:
            logger.debug("photonic emit failed: %s", exc)

    def update_performance(self, model_id: str, actual_reward: float) -> None:
        """Update historical performance after actual usage."""
        if model_id in self.model_performance:
            self.model_performance[model_id].append(actual_reward)
            # Keep last 100 results
            self.model_performance[model_id] = self.model_performance[model_id][-100:]


# Predefined model registry
DEFAULT_MODELS = [
    ModelSpec(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        cost_per_1k_tokens=0.005,
        avg_latency_ms=800,
        strengths=frozenset({"coding", "reasoning", "analysis", "writing"}),
        context_window=128000,
    ),
    ModelSpec(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        cost_per_1k_tokens=0.00015,
        avg_latency_ms=400,
        strengths=frozenset({"general", "coding"}),
        context_window=128000,
    ),
    ModelSpec(
        id="claude-sonnet-4",
        name="Claude Sonnet 4 (2025-05-14)",
        provider="anthropic",
        cost_per_1k_tokens=0.003,
        avg_latency_ms=900,
        strengths=frozenset({"coding", "analysis", "writing", "reasoning"}),
        context_window=200000,
    ),
    ModelSpec(
        id="claude-3-5-sonnet",
        name="Claude 3.5 Sonnet",
        provider="anthropic",
        cost_per_1k_tokens=0.003,
        avg_latency_ms=900,
        strengths=frozenset({"coding", "analysis", "writing", "reasoning"}),
        context_window=200000,
    ),
    ModelSpec(
        id="claude-3-haiku",
        name="Claude 3 Haiku",
        provider="anthropic",
        cost_per_1k_tokens=0.00025,
        avg_latency_ms=350,
        strengths=frozenset({"general", "quick"}),
        context_window=200000,
    ),
    ModelSpec(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider="google",
        cost_per_1k_tokens=0.0001,
        avg_latency_ms=280,
        strengths=frozenset({"general", "fast", "coding"}),
        context_window=1000000,
    ),
    ModelSpec(
        id="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        provider="google",
        cost_per_1k_tokens=0.000075,
        avg_latency_ms=300,
        strengths=frozenset({"general", "fast"}),
        context_window=1000000,
    ),
    ModelSpec(
        id="llama-3.3-70b",
        name="Llama 3.3 70B",
        provider="meta",
        cost_per_1k_tokens=0.0009,
        avg_latency_ms=550,
        strengths=frozenset({"coding", "reasoning", "analysis"}),
        context_window=128000,
    ),
    ModelSpec(
        id="llama-3.1-70b",
        name="Llama 3.1 70B",
        provider="meta",
        cost_per_1k_tokens=0.0009,
        avg_latency_ms=600,
        strengths=frozenset({"coding", "reasoning"}),
        context_window=128000,
    ),
    ModelSpec(
        id="deepseek-v3",
        name="DeepSeek V3",
        provider="deepseek",
        cost_per_1k_tokens=0.00027,
        avg_latency_ms=700,
        strengths=frozenset({"coding", "reasoning", "analysis"}),
        context_window=64000,
    ),
    ModelSpec(
        id="qwen-2.5-72b",
        name="Qwen 2.5 72B",
        provider="alibaba",
        cost_per_1k_tokens=0.0009,
        avg_latency_ms=650,
        strengths=frozenset({"coding", "reasoning", "writing"}),
        context_window=128000,
    ),
    ModelSpec(
        id="mistral-large",
        name="Mistral Large",
        provider="mistral",
        cost_per_1k_tokens=0.002,
        avg_latency_ms=750,
        strengths=frozenset({"coding", "reasoning", "writing", "analysis"}),
        context_window=128000,
    ),
]


def create_mcts_router(budget: int = 50) -> ModelSelectionMCTS:
    """Factory function to create MCTS router with default models."""
    return ModelSelectionMCTS(
        available_models=DEFAULT_MODELS,
        budget=budget,
    )
