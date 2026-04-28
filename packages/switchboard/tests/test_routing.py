from switchboard import Router


def test_routes_review_analyze_then_implement_as_two_distinct_steps():
    decision = Router().route("review analyze then implement")

    assert decision.classification.requires_multi_step is True
    assert decision.plan.strategy == "sequential"
    # Both reverse_engineering and coding tasks resolve to matching agents
    assert [step.agent_id.value for step in decision.plan.steps] == [
        "reverse_engineering",
        "coding",
    ]
    assert all(step.confidence >= 0.7 for step in decision.plan.steps)


def test_routes_reporting_step_for_report_follow_up():
    decision = Router().route("first analyze the data, then create a report")

    assert decision.classification.classification == "data_analysis"
    assert decision.classification.requires_multi_step is True
    # Check that task IDs are correctly classified
    assert [step.task_id.value for step in decision.plan.steps] == [
        "data_analysis",
        "reporting",
    ]
    # And that they resolve to the correct agents
    assert [step.agent_id.value for step in decision.plan.steps] == [
        "data_analysis",
        "documentation",  # reporting resolves to documentation agent
    ]


def test_routes_visualization_and_system_design_subtasks():
    router = Router()

    visualization = router.route("analyze this dataset and then visualize it")
    system_design = router.route("design the system and then write tests")

    # Both data_analysis and visualization resolve to data_analysis agent
    # So deduplication merges them into one step
    assert [step.task_id.value for step in visualization.plan.steps] == [
        "data_analysis",  # visualization merged with data_analysis (same agent)
    ]
    # Agent ID is data_analysis for the merged step
    assert [step.agent_id.value for step in visualization.plan.steps] == [
        "data_analysis",
    ]

    # system_design and testing resolve to different agents (reverse_engineering and coding)
    # so they remain separate steps
    assert [step.task_id.value for step in system_design.plan.steps] == [
        "system_design",
        "testing",
    ]
    assert [step.agent_id.value for step in system_design.plan.steps] == [
        "reverse_engineering",
        "coding",
    ]


def test_clear_prompt_confidence_is_higher_than_general_fallback():
    router = Router()

    clear = router.route("quickly write code")
    ambiguous = router.route("do something interesting")

    assert clear.classification.classification == "coding"
    assert clear.classification.confidence >= 0.7
    assert ambiguous.classification.classification == "general"
    assert clear.classification.confidence > ambiguous.classification.confidence


def test_routes_trading_analysis_prompts():
    router = Router()

    decision = router.route("backtest my trading strategy on BTC")
    assert decision.classification.task_id.value == "trading_analysis"
    assert decision.plan.steps[0].agent_id.value == "trading_analysis"

    decision = router.route("analyze the portfolio Sharpe ratio and drawdown")
    assert decision.classification.task_id.value == "trading_analysis"


def test_routes_creative_writing_prompts():
    router = Router()

    decision = router.route("write a short story about a dragon")
    assert decision.classification.task_id.value == "creative_writing"
    assert decision.plan.steps[0].agent_id.value == "creative_writing"

    decision = router.route("compose a poem about the ocean")
    assert decision.classification.task_id.value == "creative_writing"


def test_trading_agent_produces_output():
    from switchboard.execution import ExecutionEngine

    router = Router()
    engine = ExecutionEngine(router)
    result = engine.execute("analyze this crypto trading strategy")

    assert result.success is True
    assert result.output
    assert result.primary_agent_id.value == "trading_analysis"


def test_creative_writing_agent_produces_output():
    from switchboard.execution import ExecutionEngine

    router = Router()
    engine = ExecutionEngine(router)
    result = engine.execute("write a poem about autumn leaves")

    assert result.success is True
    assert result.output
    assert result.primary_agent_id.value == "creative_writing"


def test_force_agent_trading_analysis():
    router = Router()
    decision = router.route("do something", force_agent="trading_analysis")

    assert decision.metadata.forced_agent_used is True
    assert decision.metadata.forced_agent_valid is True
    assert decision.plan.steps[0].agent_id.value == "trading_analysis"


def test_force_agent_creative_writing():
    router = Router()
    decision = router.route("do something", force_agent="creative_writing")

    assert decision.metadata.forced_agent_used is True
    assert decision.metadata.forced_agent_valid is True
    assert decision.plan.steps[0].agent_id.value == "creative_writing"


def test_expanded_model_registry_has_all_models():
    from switchboard.mcts_router import DEFAULT_MODELS

    model_ids = {m.id for m in DEFAULT_MODELS}
    expected = {
        "gpt-4o",
        "gpt-4o-mini",
        "claude-3-5-sonnet",
        "claude-3-haiku",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "llama-3.1-70b",
        "llama-3.3-70b",
        "deepseek-v3",
        "qwen-2.5-72b",
        "mistral-large",
    }
    assert expected.issubset(model_ids)


def test_mcts_router_uses_expanded_models():
    from switchboard.mcts_router import create_mcts_router

    router = create_mcts_router(budget=10)
    assert len(router.models) >= 11
    assert "deepseek-v3" in router.models
    assert "gemini-2.0-flash" in router.models
    assert "mistral-large" in router.models
