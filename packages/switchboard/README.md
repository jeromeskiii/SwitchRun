# ██████╗ ███████╗███╗   ██╗ ██████╗ ██╗     ██╗ ██████╗████████╗
# ██╔══██╗██╔════╝████╗  ██║██╔════╝ ██║     ██║██╔════╝╚══██╔══╝
# ██████╔╝█████╗  ██╔██╗ ██║██║  ███╗██║     ██║██║        ██║
# ██╔═══╝ ██╔══╝  ██║╚██╗██║██║   ██║██║     ██║██║        ██║
# ██║     ███████╗██║ ╚████║╚██████╔╝███████╗██║╚██████╗   ██║
# ╚═╝     ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝ ╚═════╝   ╚═╝

# Intelligent LLM Routing System

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Tests](https://img.shields.io/badge/Tests-106+-green.svg)

**Switchboard** is an intelligent LLM routing system that routes any input to the optimal agent(s), selects the best LLM via MCTS, builds an execution plan, and safely executes it with fallback handling.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              SWITCHBOARD ARCHITECTURE                           │
│                                                                              │
│  ┌──────────────┐     ┌─────────────────────────────────────────────────────┐ │
│  │    Input    │────▶│  LAYER 1: Intent Classifier (TaskID)             │ │
│  │   Prompt   │     │  • Keyword-based pattern matching                 │ │
│  └──────────────┘     │  • Confidence scoring (0.0-1.0)                  │ │
│                       │  • Multi-step detection                            │ │
│                       └─────────────────────┬───────────────────────────────┘ │
│                                             │                                 │
│                       ┌─────────────────────▼───────────────────────────────┐ │
│                       │  LAYER 2: MCTS Model Router (Optional)          │ │
│                       │  • Task features → ModelSpec                     │ │
│                       │  • UCB1 selection with reward backprop            │ │
│                       │  • 11 pre-configured models                      │ │
│                       └─────────────────────┬───────────────────────────────┘ │
│                                             │                                 │
│                       ┌─────────────────────▼───────────────────────────────┐ │
│                       │  LAYER 3: Planner (ExecutionPlan)                │ │
│                       │  • Sequential or parallel execution               │ │
│                       │  • Step deduplication                            │ │
│                       │  • Fallback agent assignment                     │ │
│                       └─────────────────────┬───────────────────────────────┘ │
│                                             │                                 │
│                       ┌─────────────────────▼───────────────────────────────┐ │
│                       │  LAYER 4: Execution Engine                      │ │
│                       │  • Agent execution with retries                  │ │
│                       │  • Circuit breaker + rate limiting               │ │
│                       │  • Photonic event emission                      │ │
│                       └───────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
cd "/Users/jm4/Desktop/Nexus board/switchboard"

# Install dependencies
pip install -e .

# Route a task (auto-selects strategy)
python -m switchboard --input "review the repo and then implement the fix"

# Verbose routing metadata
python -m switchboard -v --input "analyze this dataset and then visualize it"

# Force specific agent
python -m switchboard --force-agent coding --input "analyze this"

# Force MasterAlpha for complex tasks
python -m switchboard --force-agent master_alpha --input "analyze this complex problem"

# JSON output
python -m switchboard --json --input "design a system" | jq .
```

For a more operational walkthrough, see [HOW_TO_GUIDE.md](HOW_TO_GUIDE.md).

## Routing Strategies

| Strategy | When Used | Latency | Agents |
|----------|----------|---------|--------|
| `fast` | Simple tasks (<0.3 complexity) | <50ms | 1 |
| `single` | Medium complexity, single step | <100ms | 1 |
| `hierarchical` | Multi-step without MCTS | 100-500ms | 2-5 |
| `mcts` | Complex workflows with MCTS search | 200ms-2s | 2-10 |

## Canonical Task IDs

| TaskID | Description | Typical Agent |
|--------|-------------|--------------|
| `reverse_engineering` | Code review, debugging | `reverse_engineering` |
| `system_design` | Architecture, scalability | `reverse_engineering` |
| `data_analysis` | Data processing, pandas | `data_analysis` |
| `visualization` | Charts, plots, dashboards | `data_analysis` |
| `coding` | Implementation, refactoring | `coding` |
| `testing` | Unit tests, integration tests | `coding` |
| `documentation` | Docs, README, guides | `documentation` |
| `reporting` | Summaries, reports, briefs | `documentation` |
| `self_upgrade` | Self-improvement | `self_upgrade` |
| `trading_analysis` | Market data, strategies | `trading_analysis` |
| `creative_writing` | Stories, prose, content | `creative_writing` |
| `general` | Fallback | `general` |

## Pre-configured Models (MCTS Router)

| Model | Provider | Cost/1K Tokens | Latency | Strengths |
|-------|----------|-----------------|---------|-----------|
| GPT-4o | OpenAI | $0.005 | 800ms | coding, reasoning, analysis |
| GPT-4o Mini | OpenAI | $0.00015 | 400ms | general, coding |
| Claude Sonnet 4 | Anthropic | $0.003 | 900ms | coding, analysis, writing |
| Claude 3.5 Sonnet | Anthropic | $0.003 | 900ms | coding, analysis |
| Claude 3 Haiku | Anthropic | $0.00025 | 350ms | general, quick |
| Gemini 2.0 Flash | Google | $0.0001 | 280ms | general, fast, coding |
| Gemini 1.5 Flash | Google | $0.000075 | 300ms | general, fast |
| Llama 3.3 70B | Meta | $0.0009 | 550ms | coding, reasoning |
| Llama 3.1 70B | Meta | $0.0009 | 600ms | coding, reasoning |
| DeepSeek V3 | DeepSeek | $0.00027 | 700ms | coding, reasoning |
| Qwen 2.5 72B | Alibaba | $0.0009 | 650ms | coding, reasoning |
| Mistral Large | Mistral | $0.002 | 750ms | coding, reasoning |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SWITCHBOARD_LLM_PROVIDER` | `openai` | Provider: openai, anthropic, openrouter |
| `SWITCHBOARD_LLM_MODEL` | `gpt-4o` | Model ID |
| `SWITCHBOARD_LLM_MAX_TOKENS` | `2048` | Max response tokens |
| `SWITCHBOARD_LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `SWITCHBOARD_OFFLINE` | unset | Set `1` to force placeholder responses |
| `SWITCHBOARD_HIERARCHICAL` | unset | Set `1` to enable hierarchical MCTS routing |

## Architecture Layers

### Layer 1: Intent Classifier

```python
from switchboard import Classifier

classifier = Classifier()
result = classifier.classify("write python code")

print(result.task_id)        # TaskID.CODING
print(result.confidence)       # 0.7+
print(result.alternatives)    # [TaskID.TESTING, ...]
```

### Layer 2: MCTS Model Router (Optional)

```python
from switchboard import create_mcts_router, TaskFeatures

router = create_mcts_router(budget=50)
features = TaskFeatures(
    complexity="high",
    estimated_tokens=2000,
    requires_code=True,
    requires_creativity=False,
    requires_reasoning=True,
    domain="coding",
    urgency="medium",
)
result = router.select_model(features)
print(result.model.name)      # Selected model
print(result.confidence)       # Selection confidence
```

### Layer 3: Planner

```python
from switchboard import Planner, Classifier

planner = Planner(Classifier(), dedupe_steps=True)
plan = planner.plan("analyze data and then visualize", classification)
print(plan.strategy)  # "single" or "sequential"
```

### Layer 4: Execution Engine

```python
from switchboard import Router, ExecutionEngine

router = Router()
engine = ExecutionEngine(router, max_retries=2, fallback_threshold=0.45)
result = engine.execute("analyze the system and then write tests")
print(result.success)
print(result.output)
print(result.fallback_used)
```

## Components

| Component | File | Purpose |
|-----------|------|---------|
| `Router` | `router.py` | Policy owner, routing decisions |
| `Classifier` | `classifier.py` | Intent detection + confidence |
| `Planner` | `planner.py` | Execution plan builder |
| `ExecutionEngine` | `execution.py` | Agent execution + fallback |
| `MCTS Router` | `mcts_router.py` | Model selection via MCTS |
| `Hybrid Router` | `hybrid_hierarchical_router.py` | 4-layer hierarchical routing |

## Configuration

```python
from switchboard.config import SwitchboardConfig

config = SwitchboardConfig(
    low_confidence_threshold=0.4,    # Override to general below this
    validate_plans=True,              # Sanity check plans
    debug_logging=False,             # Enable debug output
    dedupe_steps=True,               # Merge consecutive same-agent steps
    max_retries=2,                  # Retry attempts
    fallback_threshold=0.45,        # Confidence for fallback
    enable_audit_logging=True,      # Log to audit file
    use_mcts_routing=True,          # Enable MCTS model selection
    mcts_budget=50,                # MCTS simulations
)
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_routing.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# MCTS demo
python -m switchboard.mcts_demo
```

## Project Structure

```
switchboard/
├── __init__.py              # Public API exports
├── __main__.py              # CLI entry point
├── canonical_ids.py          # TaskID, AgentID enums
├── classifier.py             # Intent classification
├── planner.py                # Execution planning
├── execution.py              # Agent execution engine
├── router.py                 # Main router
├── mcts_router.py           # MCTS model selection
├── mcts_classifier.py       # MCTS-enhanced classifier
├── hybrid_hierarchical_router.py  # 4-layer router
├── agents.py                 # Agent implementations
├── llm_client.py            # LLM client wrapper
├── config.py                # Configuration
├── env.py                   # Environment loading
├── routing_memory.py         # Feedback learning
├── runtime_enforcement.py   # Rate limiting, circuit breakers
├── security_adapter.py      # Security policies
├── nexus_advisor.py         # Nexus integration
├── corpus_retrieval.py      # RAG retrieval
├── router_integration.py    # Enhanced router
├── pyproject.toml
├── README.md
└── tests/
    ├── test_routing.py
    ├── test_execution.py
    ├── test_mcts.py
    ├── test_policy.py
    ├── test_benchmarks.py
    └── ...
```

## Health Checks

Switchboard includes a health check system for monitoring component status:

```python
from switchboard import create_default_health_checker, print_health_report

# Print full health report
create_default_health_checker()
print_health_report()
```

Or programmatically:

```python
from switchboard import HealthChecker, check_classifier, check_router

checker = HealthChecker()
checker.register("classifier", check_classifier)
checker.register("router", check_router)

results = checker.check_all()
for result in results:
    print(f"{result.name}: {'✓' if result.healthy else '✗'} {result.message}")
```

### Available Health Checks

| Check | Description |
|-------|-------------|
| `classifier` | Verifies intent classification is working |
| `router` | Verifies routing engine is operational |
| `telemetry` | Verifies metrics collection is available |
| `agents` | Verifies all agent types are loadable |
| `models` | Verifies MCTS models are configured |

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## License

MIT License - Copyright 2026 Human Systems
