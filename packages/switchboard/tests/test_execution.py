import json

from switchboard.agents import Agent, AgentResult, PantheonAgent
from switchboard.canonical_ids import AgentID
from switchboard.execution import ExecutionEngine
from switchboard.llm_client import LLMConfig
from switchboard.router import Router


class StaticAgent(Agent):
    def __init__(self, agent_name: str, response: str, capture: dict | None = None):
        self._agent_name = agent_name
        self._response = response
        self._capture = capture

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def description(self) -> str:
        return f"Static agent for {self._agent_name}"

    def run(self, input_text: str, llm_config: LLMConfig | None = None) -> AgentResult:
        if self._capture is not None:
            self._capture["input_text"] = input_text
        return AgentResult(success=True, output=self._response, metadata={"agent": self.name})


class FailingAgent(Agent):
    def __init__(self, agent_name: str, error_message: str = "Agent failed"):
        self._agent_name = agent_name
        self._error_message = error_message

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def description(self) -> str:
        return f"Failing agent for {self._agent_name}"

    def run(self, input_text: str, llm_config: LLMConfig | None = None) -> AgentResult:
        return AgentResult(success=False, output="", error=self._error_message)


def test_multi_step_execution_chains_previous_output_into_next_step():
    router = Router()
    second_step_capture: dict[str, str] = {}
    # Use AgentID keys for the new registry
    router.agents[AgentID.REVERSE_ENGINEERING] = StaticAgent(
        "reverse_engineering", "analysis summary"
    )
    router.agents[AgentID.CODING] = StaticAgent("coding", "tests written", second_step_capture)

    result = ExecutionEngine(router).execute("analyze the system and then write tests")

    assert result.success is True
    assert (
        "Original request:\nanalyze the system and then write tests"
        in second_step_capture["input_text"]
    )
    assert (
        "Previous step outputs:\nStep 1 output:\nanalysis summary"
        in second_step_capture["input_text"]
    )
    assert second_step_capture["input_text"].endswith("Current step:\nwrite tests")


def test_multi_step_fallback_success_counts_as_success_for_logical_step():
    router = Router()
    router.agents[AgentID.REVERSE_ENGINEERING] = StaticAgent(
        "reverse_engineering", "analysis summary"
    )
    router.agents[AgentID.CODING] = FailingAgent("coding", "Primary failed")

    result = ExecutionEngine(router, fallback_threshold=0.9).execute(
        "review the repo and then implement the fix"
    )

    assert result.success is True
    assert result.fallback_used is True
    assert result.error is None
    assert result.output
    assert result.metadata == {
        "num_steps": 2,
        "plan_confidence": 0.75,
        "step_agents": ["reverse_engineering", "coding"],
        "step_confidences": [0.7, 0.8],
        "step_summary": ["Step 1: ✓", "Step 2: ✓"],
        "failed_steps": None,
    }


def test_pantheon_agent_selects_registry_match_without_runtime_dependency():
    result = PantheonAgent().run("implement auth system")

    assert result.success is True
    payload = json.loads(result.output)
    assert payload["selection"]["name"] == "Hephaestus"
    assert payload["route"]["switchboardAgent"] == "pantheon"
    assert payload["route"]["mythosSkill"] == "hephaestus"
