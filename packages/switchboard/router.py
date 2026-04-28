# Copyright 2026 Human Systems. MIT License.
"""Router component that coordinates classification and planning."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from switchboard.execution import ExecutionResult

from switchboard.env import load_environment
from switchboard.canonical_ids import AgentID, TaskID, resolve_task_to_agent
from switchboard.classifier import Classifier, ClassificationResult
from switchboard.config import SwitchboardConfig
from switchboard.mcts_classifier import MCTSEnhancedClassifier
from switchboard.planner import Planner, ExecutionPlan
from switchboard.agents import (
    Agent,
    ReverseEngineeringAgent,
    DataAnalysisAgent,
    CodingAgent,
    DocumentationAgent,
    GeneralAgent,
    SelfUpgradeAgent,
    TradingAnalysisAgent,
    CreativeWritingAgent,
)

# Configure module-level logger
logger = logging.getLogger(__name__)


@dataclass
class RoutingMetadata:
    """Metadata about routing decisions for debugging and observability."""

    low_confidence_override: bool = False
    forced_agent_used: bool = False
    forced_agent_valid: bool = True
    plan_validated: bool = True
    validation_errors: list[str] = field(default_factory=list)
    original_task_id: Optional[TaskID] = None
    original_confidence: Optional[float] = None
    security_override: bool = False
    security_reason: Optional[str] = None
    strategy: str = "single"
    complexity_score: float = 0.0
    subtask_count: int = 0
    mcts_used: bool = False
    mcts_tree_summary: Optional[dict] = None
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0


@dataclass
class RoutingDecision:
    """The result of a routing process."""

    classification: ClassificationResult
    plan: ExecutionPlan
    metadata: RoutingMetadata = field(default_factory=RoutingMetadata)


class Router:
    """Main routing engine that determines how to process input.

    The Router combines classification and planning to create
    a complete RoutingDecision for the Execution Engine.

    Policy Controls (via SwitchboardConfig):
    - low_confidence_threshold: Classifications below this fallback to general
    - validate_plans: Run sanity checks on plans before returning
    - debug_logging: Enable detailed routing decision logging
    - dedupe_steps: Whether to merge consecutive steps with the same agent
    """

    def __init__(
        self,
        classifier: Optional[Classifier] = None,
        planner: Optional[Planner] = None,
        config: Optional[SwitchboardConfig] = None,
        # Legacy parameters for backward compatibility
        low_confidence_threshold: Optional[float] = None,
        validate_plans: Optional[bool] = None,
        debug_logging: Optional[bool] = None,
    ):
        # Build config from legacy parameters or use provided config
        if config is not None:
            self.config = config
        else:
            self.config = SwitchboardConfig(
                low_confidence_threshold=(
                    low_confidence_threshold if low_confidence_threshold is not None else 0.4
                ),
                validate_plans=validate_plans if validate_plans is not None else True,
                debug_logging=debug_logging if debug_logging is not None else False,
            )

        self.classifier = classifier or (
            MCTSEnhancedClassifier(mcts_budget=self.config.mcts_budget)
            if self.config.use_mcts_routing
            else Classifier()
        )
        self.planner = planner or Planner(self.classifier, dedupe_steps=self.config.dedupe_steps)
        self.agents = self._build_agent_registry()

        if self.config.debug_logging:
            if not logging.getLogger().handlers:
                logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)

    def _build_agent_registry(self) -> dict[AgentID, Agent]:
        from switchboard.agents import get_all_agents

        registry = {}
        failed_agents: list[tuple[str, str]] = []
        
        for cls in get_all_agents():
            try:
                instance = cls()
                agent_id = AgentID(instance.name)
                registry[agent_id] = instance
                logger.debug(f"Initialized agent: {agent_id.value}")
            except ValueError as e:
                failed_agents.append((cls.__name__, f"Invalid AgentID: {e}"))
                logger.warning(f"Failed to initialize {cls.__name__}: Invalid AgentID - {e}")
            except Exception as e:
                failed_agents.append((cls.__name__, str(e)))
                logger.warning(f"Failed to initialize {cls.__name__}: {e}")

        if registry:
            logger.info(f"Agent registry initialized with {len(registry)} agents")
            return registry

        # Fallback to hardcoded agents with error logging
        logger.error(
            f"No agents initialized from get_all_agents(). "
            f"Failed agents: {failed_agents}. Falling back to hardcoded registry."
        )
        
        return {
            AgentID.REVERSE_ENGINEERING: ReverseEngineeringAgent(),
            AgentID.DATA_ANALYSIS: DataAnalysisAgent(),
            AgentID.CODING: CodingAgent(),
            AgentID.DOCUMENTATION: DocumentationAgent(),
            AgentID.SELF_UPGRADE: SelfUpgradeAgent(),
            AgentID.TRADING_ANALYSIS: TradingAnalysisAgent(),
            AgentID.CREATIVE_WRITING: CreativeWritingAgent(),
            AgentID.GENERAL: GeneralAgent(),
        }

    def route(self, input_text: str, force_agent: Optional[str] = None) -> RoutingDecision:
        """Determines the routing path for the given input.

        Policy decisions made here:
        1. If force_agent is invalid, log warning and ignore
        2. If classification confidence is low, override to general
        3. Validate plan before returning (if enabled)

        Args:
            input_text: The user's input to route
            force_agent: Optional agent ID to force (must be valid AgentID)

        Returns:
            RoutingDecision with classification, plan, and metadata
        """
        metadata = RoutingMetadata()
        classification = self.classifier.classify(input_text)
        forced_agent_id: Optional[AgentID] = None

        # Store original values before any overrides
        metadata.original_task_id = classification.task_id
        metadata.original_confidence = classification.confidence

        # Handle force_agent
        if force_agent:
            agent_id = AgentID.from_string(force_agent)
            metadata.forced_agent_used = True

            # Check if the forced agent is valid
            if agent_id == AgentID.GENERAL and force_agent != "general":
                # from_string returned GENERAL because the string wasn't valid
                metadata.forced_agent_valid = False
                metadata.validation_errors.append(f"Invalid force_agent '{force_agent}'; ignoring")
                logger.warning("Invalid force_agent '%s' requested; ignoring", force_agent)
            else:
                metadata.forced_agent_valid = True
                forced_agent_id = agent_id
                logger.debug("Forcing agent to %s", force_agent)

        # Low-confidence override to general agent
        if (
            classification.confidence < self.config.low_confidence_threshold
            and not forced_agent_id  # Don't override if agent is forced
        ):
            metadata.low_confidence_override = True
            logger.debug(
                "Low confidence %.2f < threshold %.2f; overriding to general",
                classification.confidence,
                self.config.low_confidence_threshold,
            )
            classification = ClassificationResult(
                task_id=TaskID.GENERAL,
                confidence=classification.confidence,
                reason=f"Low confidence ({classification.confidence:.2f}); falling back to general",
                alternatives=classification.alternatives,
                requires_multi_step=classification.requires_multi_step,
            )

        plan = self.planner.plan(input_text, classification, forced_agent_id=forced_agent_id)

        # Validate plan
        if self.config.validate_plans:
            validation_errors = self._validate_plan(plan)
            if validation_errors:
                metadata.validation_errors.extend(validation_errors)
                metadata.plan_validated = False
                logger.warning("Plan validation issues: %s", validation_errors)
            else:
                metadata.plan_validated = True
                logger.debug("Plan validated successfully")

        decision = RoutingDecision(
            classification=classification,
            plan=plan,
            metadata=metadata,
        )

        if self.config.debug_logging:
            logger.debug("Routing decision: %s", asdict(decision))

        return decision

    def _validate_plan(self, plan: ExecutionPlan) -> list[str]:
        """Validate an execution plan for sanity.

        Checks:
        - Plan has at least one step
        - All agent IDs are valid
        - Strategy matches step count

        Args:
            plan: The plan to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not plan.steps:
            errors.append("Plan has no steps")
            return errors

        for i, step in enumerate(plan.steps):
            if not AgentID.is_valid(step.agent_id.value):
                errors.append(f"Step {i + 1} has invalid agent_id: {step.agent_id.value}")

        expected_strategy = "sequential" if len(plan.steps) > 1 else "single"
        if plan.strategy != expected_strategy:
            errors.append(f"Strategy mismatch: {plan.strategy} for {len(plan.steps)} steps")

        return errors

    def get_agent(self, agent_id: AgentID | str) -> Agent:
        """Returns the agent instance for the given AgentID.

        Args:
            agent_id: An AgentID enum or string representation

        Returns:
            The agent instance, or GeneralAgent if not found
        """
        if isinstance(agent_id, str):
            agent_id = AgentID.from_string(agent_id)
        return self.agents.get(agent_id, self.agents[AgentID.GENERAL])


def run(input_text: str) -> str:
    """End-to-end execution of a task."""
    from switchboard.execution import ExecutionEngine

    router = Router()
    engine = ExecutionEngine(router)

    result = engine.execute(input_text)

    return result.output


def execute(input_text: str, force_agent: Optional[str] = None) -> "ExecutionResult":
    """Execute a task and return the structured execution result."""
    from switchboard.execution import ExecutionEngine

    router = Router()
    engine = ExecutionEngine(router)
    return engine.execute(input_text, force_agent=force_agent)


def route(input_text: str, force_agent: Optional[str] = None) -> RoutingDecision:
    """Convenience wrapper for creating a routing decision."""
    return Router().route(input_text, force_agent=force_agent)


def _print_demo() -> None:
    tests = [
        "analyze this dataset",
        "design a system for X",
        "write python code",
        "how does this work?",
        "analyze the system and then write tests",
        "first analyze the data, then create a report",
        "debug this API call",
    ]

    print("=" * 60)
    print("Switchboard Router v1")
    print("=" * 60 + "\n")

    for item in tests:
        result = execute(item)
        print(f"📝 Input: {item}")
        print(f"   Status: {'✅' if result.success else '❌'}")
        print(f"   Output: {result.output}")
        print("-" * 40)


def _decision_to_dict(decision: RoutingDecision) -> dict[str, Any]:
    """Convert RoutingDecision to a serializable dict for display."""
    return {
        "classification": {
            "task_id": decision.classification.task_id.value,
            "confidence": decision.classification.confidence,
            "reason": decision.classification.reason,
            "alternatives": [a.value for a in decision.classification.alternatives],
            "requires_multi_step": decision.classification.requires_multi_step,
        },
        "plan": {
            "strategy": decision.plan.strategy,
            "steps": [
                {
                    "task_id": step.task_id.value,
                    "agent_id": step.agent_id.value,
                    "input_text": step.input_text[:50] + "..."
                    if len(step.input_text) > 50
                    else step.input_text,
                    "confidence": step.confidence,
                }
                for step in decision.plan.steps
            ],
            "fallback_agent_id": decision.plan.fallback_agent_id.value,
        },
        "metadata": {
            "low_confidence_override": decision.metadata.low_confidence_override,
            "forced_agent_used": decision.metadata.forced_agent_used,
            "forced_agent_valid": decision.metadata.forced_agent_valid,
            "plan_validated": decision.metadata.plan_validated,
            "validation_errors": decision.metadata.validation_errors,
            "original_task_id": decision.metadata.original_task_id.value
            if decision.metadata.original_task_id
            else None,
            "original_confidence": decision.metadata.original_confidence,
            "security_override": decision.metadata.security_override,
            "security_reason": decision.metadata.security_reason,
            "strategy": decision.metadata.strategy,
            "complexity_score": decision.metadata.complexity_score,
            "subtask_count": decision.metadata.subtask_count,
            "mcts_used": decision.metadata.mcts_used,
            "mcts_tree_summary": decision.metadata.mcts_tree_summary,
            "estimated_cost": decision.metadata.estimated_cost,
            "estimated_latency_ms": decision.metadata.estimated_latency_ms,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for local execution."""
    load_environment()

    parser = argparse.ArgumentParser(description="Run Switchboard locally")
    parser.add_argument("prompt", nargs="*", help="Prompt text to route and execute")
    parser.add_argument("-i", "--input", dest="input_text", help="Prompt text")
    parser.add_argument("--force-agent", help="Force a specific agent/category")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show routing metadata")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Output routing decision as JSON"
    )
    parser.add_argument(
        "--route-only",
        action="store_true",
        help="Print routing decision and exit without executing",
    )
    parser.add_argument(
        "--hierarchical",
        action="store_true",
        help="Use hierarchical MCTS routing (EnhancedRouter)",
    )
    args = parser.parse_args(argv)

    input_text = args.input_text or " ".join(args.prompt).strip()
    if not input_text:
        if not sys.stdin.isatty():
            input_text = sys.stdin.read().strip()
        if not input_text:
            _print_demo()
            return 0

    import os as _os
    use_hierarchical = args.hierarchical or _os.environ.get("SWITCHBOARD_HIERARCHICAL", "").lower() in ("1", "true", "yes")

    if use_hierarchical:
        from switchboard.router_integration import EnhancedRouter
        router: Router = EnhancedRouter(debug_logging=args.debug)
    else:
        router = Router(debug_logging=args.debug)
    decision = router.route(input_text, force_agent=args.force_agent)

    if args.route_only or args.json_output:
        import json

        decision_dict = _decision_to_dict(decision)
        print(json.dumps(decision_dict, indent=2))
        if args.route_only:
            return 0

    from switchboard.execution import ExecutionEngine

    engine = ExecutionEngine(router)
    result = engine.execute(input_text, force_agent=args.force_agent)

    if args.verbose and not args.json_output:
        import json

        print("Routing decision:")
        print(json.dumps(_decision_to_dict(decision), indent=2))
        print()

    print(result.output)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
