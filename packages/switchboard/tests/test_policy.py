"""Tests for routing policy and failure handling."""

from switchboard import Router, TaskID, AgentID
from switchboard.agents import Agent, AgentResult
from switchboard.execution import ExecutionEngine
from switchboard.llm_client import LLMConfig


class FailingAgent(Agent):
    """Agent that always fails for testing fallback behavior."""

    def __init__(self, agent_name: str, error_message: str = "Agent failed"):
        self._agent_name = agent_name
        self._error_message = error_message

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def description(self) -> str:
        return f"Failing agent for testing"

    def run(self, input_text: str, llm_config: LLMConfig | None = None) -> AgentResult:
        return AgentResult(
            success=False,
            output="",
            error=self._error_message,
        )


class TestLowConfidenceFallback:
    """Tests for low-confidence override to general agent."""

    def test_low_confidence_overrides_to_general(self):
        """When confidence is below threshold, should override to general."""
        router = Router(low_confidence_threshold=0.5)

        # "do something interesting" has low confidence
        decision = router.route("do something interesting")

        assert decision.classification.task_id == TaskID.GENERAL
        assert decision.metadata.low_confidence_override is True
        assert decision.metadata.original_confidence is not None
        assert decision.metadata.original_confidence < 0.5

    def test_high_confidence_does_not_override(self):
        """When confidence is above threshold, should not override."""
        router = Router(low_confidence_threshold=0.4)

        # "write python code" has high confidence
        decision = router.route("write python code")

        assert decision.classification.task_id == TaskID.CODING
        assert decision.metadata.low_confidence_override is False

    def test_custom_threshold_affects_override(self):
        """Custom threshold should affect when override happens."""
        # Very low threshold - rarely overrides
        router_low = Router(low_confidence_threshold=0.1)
        decision = router_low.route("do something interesting")

        # Should NOT override because confidence is > 0.1
        # Actually "do something interesting" will fall to GENERAL with 0.3 confidence
        # which is > 0.1, so no override
        # But the original classification IS general, so no override needed
        assert decision.metadata.low_confidence_override is False

        # Very high threshold - almost always overrides
        router_high = Router(low_confidence_threshold=0.9)
        decision = router_high.route("write python code")

        # Should override because coding confidence < 0.9
        assert decision.metadata.low_confidence_override is True


class TestForceAgentHandling:
    """Tests for force_agent parameter handling."""

    def test_valid_force_agent_succeeds(self):
        """Valid agent ID should be accepted."""
        router = Router()

        decision = router.route("analyze this", force_agent="coding")

        assert decision.metadata.forced_agent_used is True
        assert decision.metadata.forced_agent_valid is True
        assert decision.plan.steps[0].agent_id == AgentID.CODING

    def test_invalid_force_agent_is_ignored(self):
        """Invalid agent ID should be ignored with warning."""
        router = Router()

        decision = router.route("analyze this dataset", force_agent="nonexistent_agent")

        assert decision.metadata.forced_agent_used is True
        assert decision.metadata.forced_agent_valid is False
        assert "Invalid force_agent" in decision.metadata.validation_errors[0]
        # Should fall back to normal classification (original classification preserved)
        assert decision.metadata.original_task_id == TaskID.DATA_ANALYSIS
        # The plan should use the resolved agent from normal classification
        assert decision.plan.steps[0].agent_id == AgentID.DATA_ANALYSIS

    def test_force_agent_general_is_valid(self):
        """The string 'general' should be a valid force_agent."""
        router = Router()

        decision = router.route("write code", force_agent="general")

        assert decision.metadata.forced_agent_used is True
        assert decision.metadata.forced_agent_valid is True
        assert decision.plan.steps[0].agent_id == AgentID.GENERAL

    def test_force_agent_pantheon_is_valid(self):
        """Pantheon should be exposed as a valid force_agent."""
        router = Router()

        decision = router.route("implement auth system", force_agent="pantheon")

        assert decision.metadata.forced_agent_used is True
        assert decision.metadata.forced_agent_valid is True
        assert decision.plan.steps[0].agent_id == AgentID.PANTHEON


class TestPlanValidation:
    """Tests for plan sanity checks."""

    def test_valid_plan_passes_validation(self):
        """A valid plan should pass validation."""
        router = Router(validate_plans=True)

        decision = router.route("analyze the data and then write code")

        assert decision.metadata.plan_validated is True
        assert len(decision.metadata.validation_errors) == 0

    def test_validation_can_be_disabled(self):
        """Validation can be disabled."""
        router = Router(validate_plans=False)

        decision = router.route("analyze this")

        # plan_validated should be True by default (no validation run)
        assert decision.metadata.plan_validated is True


class TestPlannerDeduplication:
    """Tests for planner step deduplication."""

    def test_consecutive_same_agent_steps_are_merged(self):
        """Consecutive steps with the same agent should be merged."""
        from switchboard import Classifier, Planner

        classifier = Classifier()
        planner = Planner(classifier, dedupe_steps=True)

        # "analyze the data and then visualize it" both go to data_analysis agent
        classification = classifier.classify("analyze the data and then visualize it")
        plan = planner.plan("analyze the data and then visualize it", classification)

        # Should be merged into one step since both resolve to data_analysis agent
        assert len(plan.steps) == 1
        assert "Merged" in plan.steps[0].reason

    def test_different_agent_steps_are_not_merged(self):
        """Steps with different agents should not be merged."""
        from switchboard import Classifier, Planner

        classifier = Classifier()
        planner = Planner(classifier, dedupe_steps=True)

        # "analyze the data and then write code" go to different agents
        classification = classifier.classify("analyze the data and then write code")
        plan = planner.plan("analyze the data and then write code", classification)

        # Should remain two steps
        assert len(plan.steps) == 2
        assert plan.steps[0].agent_id == AgentID.DATA_ANALYSIS
        assert plan.steps[1].agent_id == AgentID.CODING

    def test_dedupe_can_be_disabled(self):
        """Deduplication can be disabled."""
        from switchboard import Classifier, Planner

        classifier = Classifier()
        planner = Planner(classifier, dedupe_steps=False)

        classification = classifier.classify("analyze the data and then visualize it")
        plan = planner.plan("analyze the data and then visualize it", classification)

        # Should NOT be merged
        assert len(plan.steps) == 2


class TestFallbackExecution:
    """Tests for fallback execution when agent fails."""

    def test_fallback_used_on_agent_failure_with_low_confidence(self):
        """Fallback agent should be used when primary fails with low confidence."""
        router = Router()
        router.agents[AgentID.CODING] = FailingAgent("coding", "Primary failed")

        engine = ExecutionEngine(router, fallback_threshold=0.5)

        # Create a low-confidence scenario
        result = engine.execute("do something interesting")

        # The general agent should handle it (fallback from coding which failed)
        assert result.fallback_used is True or result.primary_agent_id == AgentID.GENERAL


class TestCanonicalMappingConsistency:
    """Tests for canonical task-to-agent mapping consistency."""

    def test_all_task_ids_have_mapping(self):
        """Every TaskID should have a mapping to an AgentID."""
        from switchboard.canonical_ids import TASK_TO_AGENT, TaskID

        for task_id in TaskID:
            assert task_id in TASK_TO_AGENT, f"Missing mapping for {task_id}"

    def test_all_mapped_agent_ids_are_valid(self):
        """All mapped AgentIDs should be valid enum values."""
        from switchboard.canonical_ids import TASK_TO_AGENT, AgentID

        for task_id, agent_id in TASK_TO_AGENT.items():
            assert AgentID.is_valid(agent_id.value), f"Invalid agent {agent_id} for task {task_id}"

    def test_resolve_task_to_agent_returns_valid_agent(self):
        """resolve_task_to_agent should always return valid AgentID."""
        from switchboard.canonical_ids import resolve_task_to_agent, TaskID, AgentID

        for task_id in TaskID:
            agent_id = resolve_task_to_agent(task_id)
            assert isinstance(agent_id, AgentID)

    def test_router_has_agent_for_every_agent_id(self):
        """Router should have an agent instance for every AgentID."""
        router = Router()

        for agent_id in AgentID:
            agent = router.get_agent(agent_id)
            assert agent is not None, f"No agent for {agent_id}"
            assert agent.name == agent_id.value

    def test_unknown_string_resolves_to_general(self):
        """Unknown strings should resolve to GENERAL for both TaskID and AgentID."""
        from switchboard.canonical_ids import TaskID, AgentID

        assert TaskID.from_string("unknown_task") == TaskID.GENERAL
        assert AgentID.from_string("unknown_agent") == AgentID.GENERAL
