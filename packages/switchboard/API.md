# Switchboard API Documentation

**Switchboard v2.0.0** - Intelligent LLM Routing System

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Classifier](#classifier)
3. [Router](#router)
4. [Planner](#planner)
5. [ExecutionEngine](#executionengine)
6. [MCTS Model Router](#mcts-model-router)
7. [Hybrid Hierarchical Router](#hybrid-hierarchical-router)
8. [Configuration](#configuration)
9. [Canonical IDs](#canonical-ids)
10. [Agents](#agents)
11. [Telemetry](#telemetry)

---

## Core Concepts

### Architecture Overview

Switchboard uses a 4-layer routing architecture:

```
Input → Intent Classifier → MCTS Model Router → Planner → Execution Engine
```

1. **Intent Classification** - Classifies input into canonical TaskIDs
2. **Model Selection** (Optional) - Uses MCTS to select optimal LLM
3. **Execution Planning** - Builds sequential/parallel execution plan
4. **Agent Execution** - Executes with retries, circuit breakers, fallback

### Routing Strategies

| Strategy | Complexity | Latency | Use Case |
|----------|------------|---------|----------|
| `fast` | < 0.3 | < 50ms | Simple single-step tasks |
| `single` | 0.3-0.5 | < 100ms | Medium complexity, single agent |
| `hierarchical` | 0.5-0.7 | 100-500ms | Multi-step without MCTS |
| `mcts` | > 0.7 | 200ms-2s | Complex workflows with model selection |

---

## Classifier

```python
from switchboard import Classifier, ClassificationResult

classifier = Classifier()
result = classifier.classify("write python code and then test it")
```

### Methods

#### `Classifier.__init__(**kwargs)`

Initialize classifier with optional overrides.

#### `Classifier.classify(input_text: str) -> ClassificationResult`

Classify input text into a TaskID.

**Parameters:**
- `input_text` (str): Input prompt to classify

**Returns:** `ClassificationResult`

### ClassificationResult

```python
@dataclass
class ClassificationResult:
    task_id: TaskID           # Canonical task identifier
    confidence: float         # Confidence score (0.0-1.0)
    alternatives: List[TaskID]  # Alternative task IDs
    reasoning: str            # Classification reasoning
```

---

## Router

```python
from switchboard import Router, RoutingDecision, RoutingMetadata

router = Router()
decision = router.route("analyze the codebase")
```

### Methods

#### `Router.__init__(config: Optional[SwitchboardConfig] = None)`

Initialize router with optional config.

#### `Router.route(input_text: str) -> RoutingDecision`

Route input to optimal agent(s).

**Parameters:**
- `input_text` (str): Input prompt

**Returns:** `RoutingDecision`

### RoutingDecision

```python
@dataclass
class RoutingDecision:
    task_id: TaskID
    agent_id: AgentID
    strategy: str
    estimated_cost: float
    estimated_latency_ms: float
    metadata: RoutingMetadata
    plan: Optional[ExecutionPlan]
```

### RoutingMetadata

```python
@dataclass
class RoutingMetadata:
    confidence: float
    alternatives: List[TaskID]
    mcts_used: bool
    fallback_used: bool
    reasoning: str
```

### Top-Level Functions

```python
from switchboard import route, execute, run

# Route only
decision = route("analyze this data")

# Route and execute
result = execute("write tests for this module")

# Async route and execute
result = await run("design a system")
```

---

## Planner

```python
from switchboard import Planner, ExecutionPlan, ExecutionStep

planner = Planner(classifier, dedupe_steps=True)
plan = planner.plan("analyze data and visualize", classification)
```

### Methods

#### `Planner.plan(input_text: str, classification: ClassificationResult) -> ExecutionPlan`

Build execution plan from classification.

### ExecutionPlan

```python
@dataclass
class ExecutionPlan:
    strategy: str              # "single", "sequential", "parallel"
    steps: List[ExecutionStep]
    estimated_cost: float
    estimated_latency_ms: float
```

### ExecutionStep

```python
@dataclass
class ExecutionStep:
    step_id: str
    agent_id: AgentID
    task_description: str
    dependencies: List[str]     # Step IDs this depends on
    estimated_complexity: float
```

---

## ExecutionEngine

```python
from switchboard import ExecutionEngine, Router

router = Router()
engine = ExecutionEngine(router, max_retries=2, fallback_threshold=0.45)
result = engine.execute("analyze and document this code")
```

### Methods

#### `ExecutionEngine.__init__(...)`

Initialize with:
- `router`: Router instance
- `max_retries`: Max retry attempts (default: 2)
- `fallback_threshold`: Confidence threshold for fallback (default: 0.45)

#### `ExecutionEngine.execute(input_text: str) -> ExecutionResult`

Execute routing and agent execution.

**Parameters:**
- `input_text` (str): Input prompt

**Returns:** `ExecutionResult`

### ExecutionResult

```python
@dataclass
class ExecutionResult:
    success: bool
    output: Optional[str]
    error: Optional[str]
    fallback_used: bool
    retries: int
    latency_ms: float
    metadata: Dict[str, Any]
```

---

## MCTS Model Router

```python
from switchboard import create_mcts_router, TaskFeatures, ModelSpec

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
```

### TaskFeatures

```python
@dataclass
class TaskFeatures:
    complexity: str            # "low", "medium", "high", "extreme"
    estimated_tokens: int
    requires_code: bool
    requires_creativity: bool
    requires_reasoning: bool
    domain: str                # "coding", "analysis", "writing", "general"
    urgency: str               # "low", "medium", "high"
```

### SelectionResult

```python
@dataclass
class SelectionResult:
    model: ModelSpec
    confidence: float
    reasoning: str
    alternatives: List[ModelSpec]
```

### ModelSpec

```python
@dataclass
class ModelSpec:
    name: str
    provider: str              # "openai", "anthropic", "google", "meta", "deepseek", "alibaba", "mistral"
    cost_per_1k_tokens: float
    latency_ms: float
    context_window: int
    strengths: List[str]
    max_tokens: int
```

### Default Models

| Model | Provider | Cost/1K Tokens | Latency |
|-------|----------|-----------------|---------|
| GPT-4o | OpenAI | $0.005 | 800ms |
| GPT-4o Mini | OpenAI | $0.00015 | 400ms |
| Claude Sonnet 4 | Anthropic | $0.003 | 900ms |
| Claude 3.5 Sonnet | Anthropic | $0.003 | 900ms |
| Claude 3 Haiku | Anthropic | $0.00025 | 350ms |
| Gemini 2.0 Flash | Google | $0.0001 | 280ms |
| Gemini 1.5 Flash | Google | $0.000075 | 300ms |
| Llama 3.3 70B | Meta | $0.0009 | 550ms |
| Llama 3.1 70B | Meta | $0.0009 | 600ms |
| DeepSeek V3 | DeepSeek | $0.00027 | 700ms |
| Qwen 2.5 72B | Alibaba | $0.0009 | 650ms |
| Mistral Large | Mistral | $0.002 | 750ms |

---

## Hybrid Hierarchical Router

```python
from switchboard.hybrid_hierarchical_router import (
    HybridHierarchicalRouter,
    ComplexityClassifier,
    route_task,
)

router = HybridHierarchicalRouter(use_mcts=True, mcts_simulations=50)
decision = router.route("analyze this system and then design improvements")

# Quick function
result = route_task("implement and test this feature", use_mcts=False)
```

### Components

#### ComplexityClassifier

Classifies task complexity (0.0-1.0) based on:
- Keyword indicators
- Step count estimation
- Domain detection

#### TaskDecomposer

Breaks multi-step tasks into SubTasks with dependencies.

#### MCTSWorkflowSearcher

Uses Monte Carlo Tree Search to find optimal agent workflow.

### route_task()

```python
def route_task(
    task: str,
    use_mcts: bool = True,
    mcts_simulations: int = 50,
) -> RoutingDecision
```

Quick routing function for common use cases.

---

## Configuration

```python
from switchboard.config import SwitchboardConfig

config = SwitchboardConfig(
    low_confidence_threshold=0.4,
    validate_plans=True,
    debug_logging=False,
    dedupe_steps=True,
    max_retries=2,
    fallback_threshold=0.45,
    enable_audit_logging=True,
    use_mcts_routing=True,
    mcts_budget=50,
)
```

### SwitchboardConfig Fields

| Field | Default | Description |
|-------|---------|-------------|
| `low_confidence_threshold` | 0.4 | Route to GENERAL below this |
| `validate_plans` | True | Sanity check plans |
| `debug_logging` | False | Enable debug output |
| `dedupe_steps` | True | Merge consecutive same-agent steps |
| `max_retries` | 2 | Retry attempts |
| `fallback_threshold` | 0.45 | Confidence for fallback agent |
| `enable_audit_logging` | True | Log to audit file |
| `use_mcts_routing` | True | Enable MCTS model selection |
| `mcts_budget` | 50 | MCTS simulation count |

---

## Canonical IDs

### TaskID Enum

```python
from switchboard import TaskID

TaskID.REVERSE_ENGINEERING  # Code review, debugging
TaskID.SYSTEM_DESIGN        # Architecture, scalability
TaskID.DATA_ANALYSIS        # Data processing, pandas
TaskID.VISUALIZATION        # Charts, plots, dashboards
TaskID.CODING               # Implementation, refactoring
TaskID.TESTING              # Unit tests, integration tests
TaskID.DOCUMENTATION        # Docs, README, guides
TaskID.REPORTING            # Summaries, reports, briefs
TaskID.SELF_UPGRADE         # Self-improvement
TaskID.TRADING_ANALYSIS     # Market data, strategies
TaskID.CREATIVE_WRITING     # Stories, prose, content
TaskID.MODEL_SELECTION      # Model routing decisions
TaskID.MODEL_ROUTING        # Advanced routing
TaskID.GENERAL              # Fallback
```

### AgentID Enum

```python
from switchboard import AgentID

AgentID.REVERSE_ENGINEERING
AgentID.CODING
AgentID.DATA_ANALYSIS
AgentID.DOCUMENTATION
AgentID.GENERAL
AgentID.MASTER_ALPHA
AgentID.MYTHOS
AgentID.NEXUS
AgentID.PANTHEON
AgentID.SELF_UPGRADE
AgentID.TRADING_ANALYSIS
AgentID.CREATIVE_WRITING
AgentID.AGENT_RUNTIME
```

### TASK_TO_AGENT Mapping

```python
from switchboard import TASK_TO_AGENT, resolve_task_to_agent

agent = TASK_TO_AGENT[TaskID.CODING]  # AgentID.CODING
agent = resolve_task_to_agent(TaskID.DATA_ANALYSIS)  # AgentID.DATA_ANALYSIS
```

---

## Agents

```python
from switchboard.agents import (
    Agent,
    AgentResult,
    CodingAgent,
    DataAnalysisAgent,
)

# Base agent interface
class Agent(ABC):
    @property
    def id(self) -> AgentID: ...
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    async def execute(self, task: str, context: Dict[str, Any]) -> AgentResult: ...
```

### AgentResult

```python
@dataclass
class AgentResult:
    success: bool
    output: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]
    latency_ms: float
```

---

## Telemetry

```python
from switchboard.telemetry import SwitchboardTelemetry

telemetry = SwitchboardTelemetry()
telemetry.initialize()

# Record metrics
telemetry.record_routing_decision(
    task_id="coding",
    agent_id="coding",
    strategy="hierarchical",
    latency_ms=150.5,
    confidence=0.85,
)

telemetry.record_model_selection(
    model_name="gpt-4o",
    provider="openai",
    latency_ms=800.0,
    cost=0.005,
)

# Get metrics
metrics = telemetry.get_metrics()
```

### Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `switchboard_routing_decisions_total` | Counter | Total routing decisions |
| `switchboard_routing_latency_seconds` | Histogram | Routing latency |
| `switchboard_model_selections_total` | Counter | Model selections by provider |
| `switchboard_execution_results_total` | Counter | Execution results |
| `switchboard_task_classifications_total` | Counter | Classifications by TaskID |
| `switchboard_cost_estimate_dollars` | Gauge | Estimated cost per model |

### CLI

```bash
# Start metrics server on port 9100
python -m switchboard.telemetry --port 9100

# Or programmatically
telemetry.start_server(port=9100)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SWITCHBOARD_LLM_PROVIDER` | `openai` | LLM provider |
| `SWITCHBOARD_LLM_MODEL` | `gpt-4o` | Model ID |
| `SWITCHBOARD_LLM_MAX_TOKENS` | `2048` | Max response tokens |
| `SWITCHBOARD_LLM_TEMPERATURE` | `0.3` | Sampling temperature |
| `SWITCHBOARD_OFFLINE` | unset | Force placeholder responses |
| `SWITCHBOARD_HIERARCHICAL` | unset | Enable hierarchical routing |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |

---

## Examples

### Basic Routing

```python
from switchboard import route

decision = route("analyze this dataset")
print(f"Agent: {decision.agent_id}")
print(f"Strategy: {decision.strategy}")
```

### Full Execution

```python
from switchboard import execute

result = execute("write unit tests for the router")
print(f"Success: {result.success}")
print(f"Output: {result.output}")
```

### MCTS Model Selection

```python
from switchboard import create_mcts_router, TaskFeatures

router = create_mcts_router(budget=100)
features = TaskFeatures(
    complexity="high",
    estimated_tokens=3000,
    requires_code=True,
    requires_reasoning=True,
    domain="coding",
    urgency="medium",
)
result = router.select_model(features)
print(f"Selected: {result.model.name}")
```

### Custom Configuration

```python
from switchboard import SwitchboardConfig, Router

config = SwitchboardConfig(
    low_confidence_threshold=0.5,
    use_mcts_routing=False,
    max_retries=3,
)
router = Router(config=config)
```
