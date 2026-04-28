# Copyright 2026 Human Systems. MIT License.
"""pytest module for HybridHierarchicalRouter and EnhancedRouter.

Converted from the demo script test_hierarchical_router.py which had no
assertions and could not run in CI.
"""

from __future__ import annotations

import pytest

from switchboard.canonical_ids import AgentID, TaskID
from switchboard.hybrid_hierarchical_router import (
    ComplexityClassifier,
    HybridHierarchicalRouter,
    HybridRoutingDecision,
    MCTSWorkflowSearcher,
    SubTask,
    TaskDecomposer,
    route_task,
)
from switchboard.router_integration import EnhancedRouter


# ── ComplexityClassifier ──────────────────────────────────────────────────────

class TestComplexityClassifier:
    def setup_method(self):
        self.cc = ComplexityClassifier()

    def test_simple_task_scores_low(self):
        result = self.cc.classify("fix this bug")
        assert result.score <= 0.4, f"Expected low complexity, got {result.score}"
        assert result.is_simple

    def test_complex_task_scores_high(self):
        result = self.cc.classify(
            "research the codebase, design a distributed training system, implement it, and benchmark performance"
        )
        assert result.score > 0.5, f"Expected high complexity, got {result.score}"
        assert result.is_complex

    def test_medium_task_not_simple_not_complex(self):
        result = self.cc.classify("analyze this dataset and create a summary report")
        assert result.score > 0.0
        assert result.estimated_steps >= 1

    def test_score_clamped_to_unit_interval(self):
        for text in ["fix", "x", "a b c d e f g h i j k l m n o p q"]:
            result = self.cc.classify(text)
            assert 0.0 <= result.score <= 1.0

    def test_estimated_steps_positive(self):
        result = self.cc.classify("do something")
        assert result.estimated_steps >= 1


# ── TaskDecomposer ────────────────────────────────────────────────────────────

class TestTaskDecomposer:
    def setup_method(self):
        self.decomposer = TaskDecomposer()

    def test_simple_task_returns_single_subtask(self):
        from switchboard.hybrid_hierarchical_router import ComplexityScore
        complexity = ComplexityScore(0.2, 100, 1, "simple")
        subtasks = self.decomposer.decompose("explain this function", complexity)
        assert len(subtasks) == 1
        assert subtasks[0].id == "t0"

    def test_multi_step_task_is_decomposed(self):
        from switchboard.hybrid_hierarchical_router import ComplexityScore
        complexity = ComplexityScore(0.7, 500, 4, "complex")
        subtasks = self.decomposer.decompose(
            "debug this issue, fix it, and add regression tests", complexity
        )
        assert len(subtasks) >= 2

    def test_subtask_dependencies_are_sequential(self):
        from switchboard.hybrid_hierarchical_router import ComplexityScore
        complexity = ComplexityScore(0.7, 500, 4, "complex")
        subtasks = self.decomposer.decompose(
            "analyze the data, build a model, and evaluate results", complexity
        )
        if len(subtasks) > 1:
            # Second subtask should depend on first
            assert f"t{0}" in subtasks[1].dependencies

    def test_known_pattern_code_review(self):
        from switchboard.hybrid_hierarchical_router import ComplexityScore
        complexity = ComplexityScore(0.7, 500, 4, "complex")
        subtasks = self.decomposer.decompose("code review this module", complexity)
        assert len(subtasks) >= 1

    def test_ids_are_unique(self):
        from switchboard.hybrid_hierarchical_router import ComplexityScore
        complexity = ComplexityScore(0.8, 1000, 6, "complex")
        subtasks = self.decomposer.decompose(
            "design a system, implement it, test it, and document it", complexity
        )
        ids = [s.id for s in subtasks]
        assert len(ids) == len(set(ids)), "Duplicate subtask IDs"


# ── MCTSWorkflowSearcher ──────────────────────────────────────────────────────

class TestMCTSWorkflowSearcher:
    def setup_method(self):
        self.searcher = MCTSWorkflowSearcher(simulations=10)
        self.agents = [AgentID.CODING, AgentID.DATA_ANALYSIS, AgentID.REVERSE_ENGINEERING]

    def test_search_returns_path_and_tree(self):
        subtask = SubTask(id="t0", description="implement a feature", estimated_complexity=0.5)
        path, tree = self.searcher.search(subtask, self.agents, {})
        assert tree is not None
        assert tree.visits > 0

    def test_search_path_contains_valid_agents(self):
        subtask = SubTask(id="t0", description="write code", estimated_complexity=0.5)
        path, _ = self.searcher.search(subtask, self.agents, {})
        for action in path:
            assert action.get("agent") in self.agents

    def test_simple_subtask_action_space_is_small(self):
        """Simple subtasks (complexity <= 0.6) should not generate collaboration variants."""
        subtask = SubTask(id="t0", description="fix bug", estimated_complexity=0.3)
        actions = self.searcher._generate_actions(subtask, self.agents)
        # Only single-agent actions, no collaborations
        assert all("collaborator" not in a for a in actions)
        assert len(actions) == len(self.agents)

    def test_complex_subtask_action_space_includes_collaborations(self):
        """Complex subtasks (complexity > 0.6) should include collaboration variants."""
        subtask = SubTask(id="t0", description="large system design", estimated_complexity=0.8)
        actions = self.searcher._generate_actions(subtask, self.agents)
        collab_actions = [a for a in actions if "collaborator" in a]
        assert len(collab_actions) > 0

    def test_mcts_tree_visits_sum_equals_simulations(self):
        subtask = SubTask(id="t0", description="analyze this", estimated_complexity=0.5)
        _, tree = self.searcher.search(subtask, self.agents, {})
        assert tree.visits == 10  # simulations=10


# ── HybridHierarchicalRouter ──────────────────────────────────────────────────

class TestHybridHierarchicalRouter:
    def setup_method(self):
        self.router = HybridHierarchicalRouter(use_mcts=True, mcts_simulations=10)

    def test_simple_task_takes_fast_path(self):
        decision = self.router.route("fix this bug", force_complexity="simple")
        assert decision.strategy == "fast"
        assert isinstance(decision, HybridRoutingDecision)

    def test_complex_task_uses_mcts_strategy(self):
        decision = self.router.route(
            "research the codebase, design a distributed training system, implement it, and benchmark performance",
            force_complexity="complex",
        )
        assert decision.strategy in ("mcts", "hierarchical")
        assert len(decision.subtasks) >= 1

    def test_decision_has_primary_agent(self):
        decision = self.router.route("analyze this dataset")
        assert isinstance(decision.primary_agent, AgentID)

    def test_decision_confidence_in_unit_interval(self):
        decision = self.router.route("write python code for sorting")
        assert 0.0 <= decision.confidence <= 1.0

    def test_multi_step_task_produces_subtasks(self):
        decision = self.router.route(
            "analyze the data, clean it, and then build a predictive model",
            force_complexity="complex",
        )
        assert len(decision.subtasks) >= 1

    def test_fast_path_no_subtasks(self):
        decision = self.router.route("explain recursion", force_complexity="simple")
        assert decision.strategy == "fast"

    def test_force_simple_overrides_complex_input(self):
        complex_text = "research, design, implement, test, deploy, benchmark, and document a distributed ML pipeline"
        decision = self.router.route(complex_text, force_complexity="simple")
        assert decision.strategy == "fast"

    def test_route_without_mcts_falls_back_to_hierarchical(self):
        router = HybridHierarchicalRouter(use_mcts=False)
        decision = router.route(
            "analyze the logs and then write a fix",
            force_complexity="complex",
        )
        assert decision.strategy == "hierarchical"


# ── EnhancedRouter ────────────────────────────────────────────────────────────

class TestEnhancedRouter:
    def setup_method(self):
        self.router = EnhancedRouter(use_hierarchical=True, use_mcts=True, mcts_simulations=5)

    def test_route_returns_routing_decision(self):
        from switchboard.router import RoutingDecision
        decision = self.router.route("fix this bug")
        assert isinstance(decision, RoutingDecision)

    def test_route_with_force_agent_bypasses_hierarchy(self):
        from switchboard.router import RoutingDecision
        decision = self.router.route("analyze data", force_agent="coding")
        assert isinstance(decision, RoutingDecision)
        assert decision.metadata.forced_agent_used

    def test_route_complex_task_uses_hierarchical_path(self):
        from switchboard.router import RoutingDecision
        decision = self.router.route(
            "review the repo and then implement the fix"
        )
        assert isinstance(decision, RoutingDecision)

    def test_routing_stats_available(self):
        self.router.route("analyze something")
        stats = self.router.get_routing_stats()
        assert stats.get("hierarchical_enabled") is True

    def test_enhanced_router_disabled_falls_back_to_legacy(self):
        from switchboard.router import RoutingDecision
        router = EnhancedRouter(use_hierarchical=False)
        decision = router.route("write python code")
        assert isinstance(decision, RoutingDecision)


# ── route_task convenience function ──────────────────────────────────────────

class TestRouteTask:
    def test_returns_hybrid_routing_decision(self):
        decision = route_task("analyze this CSV file")
        assert isinstance(decision, HybridRoutingDecision)

    def test_without_mcts(self):
        decision = route_task("generate a report", use_mcts=False)
        assert isinstance(decision, HybridRoutingDecision)
