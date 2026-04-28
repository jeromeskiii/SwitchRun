# Copyright 2026 Human Systems. MIT License.
"""Integration layer for Hybrid Hierarchical Router into existing Switchboard.

This module bridges the new HALO/MASTER/CASTER-inspired routing architecture
with the existing Switchboard components (classifier, planner, router).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from switchboard.classifier import ClassificationResult
from switchboard.planner import ExecutionPlan, ExecutionStep
from switchboard.router import Router, RoutingDecision, RoutingMetadata
from switchboard.canonical_ids import AgentID, TaskID, resolve_task_to_agent
from switchboard.hybrid_hierarchical_router import (
    HybridHierarchicalRouter,
    HybridRoutingDecision,
    ExecutionMetrics,
    ComplexityScore,
)

logger = logging.getLogger(__name__)


class EnhancedRouter(Router):
    """Extended Router with hierarchical-MCTS capabilities.

    This is a drop-in replacement for the existing Router that adds:
    - Layer 1: Fast complexity-based routing
    - Layer 2: HALO-style task decomposition
    - Layer 3: MASTER-style MCTS workflow search
    - Layer 4: CASTER-style cost-aware learning
    """

    def __init__(
        self,
        classifier=None,
        planner=None,
        config=None,
        # New hierarchical router parameters
        use_hierarchical: bool = True,
        use_mcts: bool = True,
        mcts_simulations: int = 20,
        llm_client=None,
        # Legacy parameters
        low_confidence_threshold=None,
        validate_plans=None,
        debug_logging=None,
    ):
        # Initialize base Router
        super().__init__(
            classifier=classifier,
            planner=planner,
            config=config,
            low_confidence_threshold=low_confidence_threshold,
            validate_plans=validate_plans,
            debug_logging=debug_logging,
        )

        # Initialize hierarchical router
        self.hierarchical_router = None
        if use_hierarchical:
            self.hierarchical_router = HybridHierarchicalRouter(
                classifier=classifier,
                llm_client=llm_client,
                use_mcts=use_mcts,
                mcts_simulations=mcts_simulations,
            )

        self.use_hierarchical = use_hierarchical
        self.metrics_history: list[tuple[HybridRoutingDecision, ExecutionMetrics]] = []

    def route_with_hierarchy(self, input_text: str) -> HybridRoutingDecision:
        """Route using full hierarchical-MCTS pipeline.

        This is the new advanced routing path that goes through all layers:
        1. Intent classification + complexity assessment
        2. Task decomposition (if complex)
        3. MCTS workflow search (if very complex)
        4. Cost-aware agent selection
        """
        if not self.hierarchical_router:
            raise RuntimeError("Hierarchical routing not enabled")

        decision = self.hierarchical_router.route(input_text)

        if self.config.debug_logging:
            logger.info(
                f"Hierarchical route: strategy={decision.strategy}, "
                f"agent={decision.primary_agent.value}, "
                f"subtasks={len(decision.subtasks)}"
            )

        return decision

    def route(self, input_text: str, force_agent: Optional[str] = None) -> RoutingDecision:
        """Route input through the pipeline.

        If hierarchical routing is enabled and no agent is forced,
        uses the new multi-layer architecture.
        Otherwise, falls back to legacy routing.
        """
        # Check for forced agent (bypass hierarchical)
        if force_agent:
            return super().route(input_text, force_agent=force_agent)

        # Check for simple queries that don't need hierarchy
        if self._is_simple_query(input_text):
            return super().route(input_text)

        # Use hierarchical routing for complex queries
        if self.use_hierarchical and self.hierarchical_router:
            try:
                hh_decision = self.route_with_hierarchy(input_text)

                # Convert hierarchical decision to legacy RoutingDecision format
                return self._convert_to_legacy_decision(hh_decision)

            except Exception as e:
                logger.warning(f"Hierarchical routing failed: {e}, falling back to legacy")
                return super().route(input_text)

        # Fallback to legacy routing
        return super().route(input_text)

    def _is_simple_query(self, text: str) -> bool:
        """Quick heuristic to identify simple queries."""
        # Short queries are likely simple
        if len(text.split()) < 5:
            return True

        # Direct commands are simple
        simple_starts = ("fix", "explain", "run", "show", "get", "list")
        if text.lower().startswith(simple_starts):
            return True

        return False

    def _convert_to_legacy_decision(self, hh_decision: HybridRoutingDecision) -> RoutingDecision:
        """Convert hierarchical decision to legacy format."""
        # Create classification from hierarchical decision
        classification = ClassificationResult(
            task_id=TaskID.from_string(hh_decision.metadata.get("classification", "general")),
            confidence=hh_decision.confidence,
            reason=f"Hierarchical routing ({hh_decision.strategy})",
            alternatives=[],
            requires_multi_step=len(hh_decision.subtasks) > 1,
            estimated_complexity="high" if hh_decision.strategy == "mcts" else "medium",
            metadata=hh_decision.metadata,
        )

        # Create execution plan from subtasks
        steps = []
        for i, subtask in enumerate(hh_decision.subtasks):
            agent = subtask.assigned_agent or hh_decision.primary_agent
            steps.append(
                ExecutionStep(
                    task_id=TaskID.from_string(hh_decision.metadata.get("classification", "general")),
                    agent_id=agent,
                    input_text=subtask.description,
                    confidence=hh_decision.confidence,
                    alternatives=[],
                    reason=f"Subtask {i + 1} from hierarchical decomposition",
                )
            )

        strategy = "sequential" if len(steps) > 1 else "single"
        plan = ExecutionPlan(
            strategy=strategy,
            steps=steps,
            fallback_agent_id=AgentID.GENERAL,
            confidence=hh_decision.confidence,
        )

        tree_summary = None
        if hh_decision.workflow_tree:
            tree_summary = {
                "visits": hh_decision.workflow_tree.visits,
                "total_reward": hh_decision.workflow_tree.total_reward,
                "children": len(hh_decision.workflow_tree.children),
            }

        metadata = RoutingMetadata(
            low_confidence_override=False,
            forced_agent_used=False,
            forced_agent_valid=True,
            plan_validated=True,
            validation_errors=[],
            original_task_id=classification.task_id,
            original_confidence=classification.confidence,
            strategy=hh_decision.strategy,
            complexity_score=hh_decision.metadata.get("complexity_score", 0.0),
            subtask_count=len(hh_decision.subtasks),
            mcts_used=hh_decision.metadata.get("mcts_used", False),
            mcts_tree_summary=tree_summary,
            estimated_cost=hh_decision.estimated_cost,
            estimated_latency_ms=hh_decision.estimated_latency_ms,
        )

        return RoutingDecision(classification=classification, plan=plan, metadata=metadata)

    def record_execution_metrics(
        self,
        hh_decision: HybridRoutingDecision,
        actual_tokens: int,
        actual_latency_ms: int,
        success: bool,
        quality_score: float = 0.0,
    ) -> None:
        """Record metrics from actual execution for learning."""
        if not self.hierarchical_router:
            return

        metrics = ExecutionMetrics(
            actual_tokens=actual_tokens,
            actual_latency_ms=actual_latency_ms,
            actual_cost=actual_tokens * 0.0001,  # Rough estimate
            success=success,
            quality_score=quality_score,
        )

        self.hierarchical_router.record_feedback(hh_decision, metrics)
        self.metrics_history.append((hh_decision, metrics))

    def get_routing_stats(self) -> dict[str, Any]:
        """Get statistics about routing decisions."""
        if not self.hierarchical_router:
            return {"hierarchical_enabled": False}

        stats = self.hierarchical_router.get_agent_stats()

        # Add strategy distribution
        strategy_counts: dict[str, int] = {}
        for decision, _ in self.metrics_history:
            strategy = decision.strategy
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            "hierarchical_enabled": True,
            "agent_performance": stats,
            "strategy_distribution": strategy_counts,
            "total_routes": len(self.metrics_history),
        }


class RoutingOrchestrator:
    """High-level orchestrator that manages routing complexity."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.router = EnhancedRouter(
            use_hierarchical=self.config.get("use_hierarchical", True),
            use_mcts=self.config.get("use_mcts", True),
            mcts_simulations=self.config.get("mcts_simulations", 20),
            debug_logging=self.config.get("debug", False),
        )

    def process(self, task: str, context: Optional[dict] = None) -> dict[str, Any]:
        """Process a task through the full orchestration pipeline."""

        # Route the task
        decision = self.router.route_with_hierarchy(task)

        # Build execution context
        execution_context = {
            "task": task,
            "routing_decision": {
                "strategy": decision.strategy,
                "primary_agent": decision.primary_agent.value,
                "confidence": decision.confidence,
                "estimated_cost": decision.estimated_cost,
                "estimated_latency_ms": decision.estimated_latency_ms,
            },
            "subtasks": [
                {
                    "id": st.id,
                    "description": st.description,
                    "agent": st.assigned_agent.value if st.assigned_agent else None,
                    "dependencies": st.dependencies,
                    "status": st.status,
                }
                for st in decision.subtasks
            ],
            "metadata": decision.metadata,
        }

        return execution_context

    def get_stats(self) -> dict[str, Any]:
        """Get orchestration statistics."""
        return self.router.get_routing_stats()


# Factory function for easy instantiation
def create_enhanced_router(
    use_hierarchical: bool = True, use_mcts: bool = True, **kwargs
) -> EnhancedRouter:
    """Create an enhanced router with hierarchical-MCTS capabilities.

    Example:
        router = create_enhanced_router(use_mcts=True, mcts_simulations=50)
        decision = router.route_with_hierarchy("Implement a distributed training system")
    """
    return EnhancedRouter(use_hierarchical=use_hierarchical, use_mcts=use_mcts, **kwargs)
