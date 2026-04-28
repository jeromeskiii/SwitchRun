# Copyright 2026 Human Systems. MIT License.
"""Regression tests for MCTS routing components."""

from switchboard.config import SwitchboardConfig
from switchboard.mcts_classifier import MCTSEnhancedClassifier
from switchboard.mcts_router import TaskFeatures, create_mcts_router
from switchboard.router import Router


class TestCreateMctsRouter:
    def test_returns_valid_model_selection_mcts(self):
        router = create_mcts_router(budget=10)
        assert router is not None
        assert len(router.models) > 0

    def test_budget_is_applied(self):
        router = create_mcts_router(budget=25)
        assert router.budget == 25

    def test_select_model_returns_selection_result(self):
        router = create_mcts_router(budget=10)
        features = TaskFeatures(
            complexity="medium",
            estimated_tokens=500,
            requires_code=True,
            requires_creativity=False,
            requires_reasoning=False,
            domain="coding",
            urgency="medium",
        )
        result = router.select_model(features)
        assert result.model is not None
        assert result.model.id in router.models
        assert 0.0 <= result.confidence <= 1.0
        assert result.simulations_run >= 0


class TestMCTSEnhancedClassifier:
    def test_attaches_mcts_metadata_to_result(self):
        classifier = MCTSEnhancedClassifier(use_mcts_routing=True, mcts_budget=10)
        result = classifier.classify("write a Python function to sort a list")
        assert result.metadata is not None
        assert "mcts_model_selection" in result.metadata
        info = result.metadata["mcts_model_selection"]
        assert "model_id" in info
        assert "model_name" in info
        assert "confidence" in info
        assert "expected_reward" in info
        assert "simulations" in info

    def test_no_metadata_when_mcts_disabled(self):
        classifier = MCTSEnhancedClassifier(use_mcts_routing=False)
        result = classifier.classify("write a Python function")
        # metadata should be absent or empty (no mcts key)
        if result.metadata is not None:
            assert "mcts_model_selection" not in result.metadata

    def test_task_classification_still_correct_with_mcts(self):
        from switchboard.canonical_ids import TaskID

        classifier = MCTSEnhancedClassifier(use_mcts_routing=True, mcts_budget=10)
        result = classifier.classify("write python code")
        assert result.task_id == TaskID.CODING


class TestUpdatePerformance:
    def test_update_performance_influences_historical_score(self):
        router = create_mcts_router(budget=5)
        model_id = list(router.models.keys())[0]

        # No history → neutral score of 0.5
        assert router._historical_score(model_id) == 0.5

        # Feed positive performance
        for _ in range(5):
            router.update_performance(model_id, 1.0)
        assert router._historical_score(model_id) > 0.5

    def test_update_performance_caps_history_at_100(self):
        router = create_mcts_router(budget=5)
        model_id = list(router.models.keys())[0]
        for i in range(150):
            router.update_performance(model_id, float(i % 2))
        assert len(router.model_performance[model_id]) == 100

    def test_negative_performance_lowers_historical_score(self):
        router = create_mcts_router(budget=5)
        model_id = list(router.models.keys())[0]
        for _ in range(5):
            router.update_performance(model_id, 0.0)
        assert router._historical_score(model_id) < 0.5


class TestRouterUsesMCTSWhenConfigured:
    def test_router_uses_base_classifier_by_default(self):
        from switchboard.classifier import Classifier

        router = Router()
        assert type(router.classifier) is Classifier

    def test_router_uses_mcts_classifier_when_config_enabled(self):
        config = SwitchboardConfig(use_mcts_routing=True, mcts_budget=10)
        router = Router(config=config)
        assert isinstance(router.classifier, MCTSEnhancedClassifier)

    def test_router_still_routes_correctly_with_mcts(self):
        config = SwitchboardConfig(use_mcts_routing=True, mcts_budget=10)
        router = Router(config=config)
        decision = router.route("write python code")
        assert decision.classification is not None
        assert decision.plan is not None
        assert decision.plan.steps

    def test_explicit_classifier_overrides_config(self):
        from switchboard.classifier import Classifier

        explicit = Classifier()
        config = SwitchboardConfig(use_mcts_routing=True, mcts_budget=10)
        router = Router(classifier=explicit, config=config)
        # Explicit classifier wins — config.use_mcts_routing is ignored
        assert router.classifier is explicit


class TestLLMConfigFromMCTSSelection:
    def test_known_model_id_maps_correctly(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "gpt-4o"})
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"

    def test_anthropic_model_maps_correctly(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "claude-3-5-sonnet"})
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"

    def test_openrouter_model_maps_correctly(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "deepseek-v3"})
        assert cfg.provider == "openrouter"
        assert cfg.model == "deepseek/deepseek-chat-v3-0324"

    def test_unknown_model_id_falls_back_to_openai(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "some-unknown-model"})
        assert cfg.provider == "openai"
        assert cfg.model == "some-unknown-model"

    def test_unknown_claude_id_infers_anthropic_provider(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "claude-4-opus"})
        assert cfg.provider == "anthropic"

    def test_unknown_gemini_id_infers_openrouter_provider(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "gemini-3-turbo"})
        assert cfg.provider == "openrouter"

    def test_unknown_llama_id_infers_openrouter_provider(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({"model_id": "llama-4-405b"})
        assert cfg.provider == "openrouter"

    def test_missing_model_id_defaults_to_gpt4o(self):
        from switchboard.llm_client import LLMConfig

        cfg = LLMConfig.from_mcts_selection({})
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"

    def test_all_known_models_resolve_without_error(self):
        from switchboard.llm_client import LLMConfig, _MODEL_ID_MAP

        for model_id in _MODEL_ID_MAP:
            cfg = LLMConfig.from_mcts_selection({"model_id": model_id})
            assert cfg.provider in {"openai", "anthropic", "openrouter"}
            assert cfg.model != ""


class TestExtractMCTSLLMConfig:
    def test_extracts_config_from_mcts_metadata(self):
        from switchboard.execution import ExecutionEngine
        from switchboard.classifier import ClassificationResult
        from switchboard.canonical_ids import TaskID
        from switchboard.router import RoutingDecision, RoutingMetadata
        from switchboard.planner import ExecutionPlan, ExecutionStep
        from switchboard.canonical_ids import AgentID

        classification = ClassificationResult(
            task_id=TaskID.CODING,
            confidence=0.8,
            reason="test",
            alternatives=[],
            metadata={"mcts_model_selection": {"model_id": "claude-3-5-sonnet"}},
        )
        plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    task_id=TaskID.CODING,
                    agent_id=AgentID.CODING,
                    input_text="test",
                    confidence=0.8,
                    reason="test",
                )
            ],
            strategy="single",
            confidence=0.8,
            fallback_agent_id=AgentID.GENERAL,
        )
        decision = RoutingDecision(classification=classification, plan=plan)
        cfg = ExecutionEngine._extract_mcts_llm_config(decision)

        assert cfg is not None
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"

    def test_returns_none_without_mcts_metadata(self):
        from switchboard.execution import ExecutionEngine
        from switchboard.classifier import ClassificationResult
        from switchboard.canonical_ids import TaskID, AgentID
        from switchboard.router import RoutingDecision
        from switchboard.planner import ExecutionPlan, ExecutionStep

        classification = ClassificationResult(
            task_id=TaskID.CODING,
            confidence=0.8,
            reason="test",
            alternatives=[],
        )
        plan = ExecutionPlan(
            steps=[
                ExecutionStep(
                    task_id=TaskID.CODING,
                    agent_id=AgentID.CODING,
                    input_text="test",
                    confidence=0.8,
                    reason="test",
                )
            ],
            strategy="single",
            confidence=0.8,
            fallback_agent_id=AgentID.GENERAL,
        )
        decision = RoutingDecision(classification=classification, plan=plan)
        cfg = ExecutionEngine._extract_mcts_llm_config(decision)

        assert cfg is None


class TestAgentReceivesMCTSConfig:
    def test_agent_run_receives_llm_config_override(self):
        from switchboard.agents import CodingAgent, AgentResult
        from switchboard.llm_client import LLMConfig
        from unittest.mock import patch

        agent = CodingAgent()
        override = LLMConfig(provider="anthropic", model="claude-sonnet-4-20250514")

        with patch("switchboard.agents.call_llm", return_value="mocked output") as mock_call:
            result = agent.run("test input", llm_config=override)

        assert result.success is True
        assert result.output == "mocked output"
        called_config = mock_call.call_args[0][2]
        assert called_config.provider == "anthropic"
        assert called_config.model == "claude-sonnet-4-20250514"

    def test_agent_run_uses_instance_config_when_no_override(self):
        from switchboard.agents import CodingAgent
        from switchboard.llm_client import LLMConfig
        from unittest.mock import patch

        instance_cfg = LLMConfig(provider="openai", model="gpt-4o-mini")
        agent = CodingAgent(llm_config=instance_cfg)

        with patch("switchboard.agents.call_llm", return_value="mocked") as mock_call:
            agent.run("test input")

        called_config = mock_call.call_args[0][2]
        assert called_config.provider == "openai"
        assert called_config.model == "gpt-4o-mini"

    def test_agent_run_uses_env_default_when_no_configs(self):
        from switchboard.agents import CodingAgent
        from unittest.mock import patch

        agent = CodingAgent()

        with patch("switchboard.agents.call_llm", return_value="mocked") as mock_call:
            agent.run("test input")

        called_config = mock_call.call_args[0][2]
        assert called_config is None


class TestEndToEndMCTSExecution:
    def test_mcts_config_propagates_through_execution(self):
        from switchboard.config import SwitchboardConfig
        from switchboard.execution import ExecutionEngine
        from unittest.mock import patch, MagicMock

        config = SwitchboardConfig(use_mcts_routing=True, mcts_budget=10)
        router = Router(config=config)
        engine = ExecutionEngine(router)

        with patch("switchboard.agents.call_llm", return_value="mcts output") as mock_call:
            result = engine.execute("write python code")

        assert result.success is True
        assert result.output == "mcts output"
        called_config = mock_call.call_args[0][2]
        if called_config is not None:
            assert called_config.provider in {"openai", "anthropic", "openrouter"}


class TestOpenRouterProviderRouting:
    def test_call_llm_routes_openrouter_to_correct_function(self):
        from switchboard.llm_client import call_llm, LLMConfig
        from unittest.mock import patch

        cfg = LLMConfig(provider="openrouter", model="deepseek/deepseek-chat-v3-0324")

        with patch(
            "switchboard.llm_client._call_openrouter", return_value="openrouter response"
        ) as mock_or:
            with patch.dict(
                "os.environ",
                {"OPENROUTER_API_KEY": "sk-or-test-key", "SWITCHBOARD_OFFLINE": ""},
            ):
                result = call_llm("system", "user", cfg)

        assert result == "openrouter response"
        mock_or.assert_called_once()

    def test_openrouter_config_from_env(self):
        from switchboard.llm_client import LLMConfig
        from unittest.mock import patch

        cfg = LLMConfig(provider="openrouter", model="test-model")
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-test"}):
            assert cfg.api_key == "sk-or-test"

    def test_openrouter_not_configured_uses_placeholder(self):
        from switchboard.llm_client import call_llm, LLMConfig
        from unittest.mock import patch

        cfg = LLMConfig(provider="openrouter", model="test-model")
        with patch.dict("os.environ", {}, clear=True):
            result = call_llm("system prompt", "user prompt", cfg)

        assert "Processed:" in result
