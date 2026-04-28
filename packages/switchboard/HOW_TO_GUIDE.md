# Switchboard How-To Guide

This guide explains how to install, run, configure, and use Switchboard in practice.

## What Switchboard Does

Switchboard routes an input prompt through four layers:

1. Intent classification
2. Optional MCTS-based model selection
3. Execution planning
4. Agent execution with retries and fallback handling

The package is designed for prompts that need one of the built-in agent roles such as coding, data analysis, documentation, reverse engineering, trading analysis, creative writing, or general fallback handling.

## Project Location

The package lives in:

`/Users/jm4/Desktop/Nexus board/switchboard`

Primary files you will use:

- `README.md` for the overview
- `HOW_TO_GUIDE.md` for operational usage
- `API.md` for reference-level API details
- `pyproject.toml` for installation and CLI entry points

## Install

From the package directory:

```bash
cd "/Users/jm4/Desktop/Nexus board/switchboard"
pip install -e .
```

For development dependencies:

```bash
pip install -e ".[dev]"
```

If you only want to inspect or run the code locally, editable install is the simplest path because it keeps your working tree and imports aligned.

## Run The CLI

The command-line entry point is `switchboard`, and the module entry point is `python -m switchboard`.

Basic usage:

```bash
switchboard --input "write python code to validate a csv file"
```

Equivalent:

```bash
python -m switchboard --input "write python code to validate a csv file"
```

You can also pass the prompt positionally:

```bash
switchboard write python code to validate a csv file
```

If no prompt is provided, Switchboard reads from standard input. If nothing is available there either, it prints a demo set of example prompts.

## Common CLI Flags

- `--input` or `-i`: prompt text
- `--force-agent`: force a specific agent category
- `--verbose` or `-v`: print routing metadata before execution
- `--debug`: enable debug logging
- `--json`: print the routing decision as JSON
- `--route-only`: show the routing decision and exit without executing
- `--hierarchical`: use the hierarchical router path

Examples:

```bash
switchboard --route-only --input "analyze this dataset"
switchboard --json --input "design a system"
switchboard --force-agent coding --input "refactor this module"
switchboard --hierarchical --input "plan a multi-step workflow"
```

If you set `SWITCHBOARD_HIERARCHICAL=1`, the CLI uses the hierarchical path without needing the flag.

## Use The Library API

The public API is exported from `switchboard`.

### Route a prompt

```python
from switchboard import route

decision = route("write tests for this module")
print(decision.classification.task_id)
print(decision.plan.strategy)
```

### Execute a prompt

```python
from switchboard import execute

result = execute("analyze this codebase and summarize the issues")
print(result.success)
print(result.output)
```

### Full router workflow

```python
from switchboard import Router, ExecutionEngine

router = Router()
decision = router.route("analyze the data and then create a report")

engine = ExecutionEngine(router)
result = engine.execute("analyze the data and then create a report")
```

Use `Router` when you only need the routing decision. Use `ExecutionEngine` when you want the full end-to-end flow.

## Configure Behavior

The main configuration object is `SwitchboardConfig`.

```python
from switchboard import SwitchboardConfig, Router

config = SwitchboardConfig(
    low_confidence_threshold=0.4,
    fallback_threshold=0.45,
    max_retries=2,
    validate_plans=True,
    dedupe_steps=True,
    use_mcts_routing=False,
    use_hierarchical=False,
)

router = Router(config=config)
```

Important settings:

- `low_confidence_threshold`: below this, routing falls back to general behavior
- `fallback_threshold`: execution fallback threshold
- `max_retries`: retry count before giving up
- `validate_plans`: sanity-check plans before returning them
- `dedupe_steps`: merge consecutive steps that target the same agent
- `use_mcts_routing`: enable MCTS model selection
- `mcts_budget`: number of MCTS simulations
- `use_hierarchical`: enable the hierarchical path

## Environment Variables

Switchboard reads local `.env` files automatically through `load_environment()`.

Supported variables include:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENROUTER_API_KEY`
- `SWITCHBOARD_LLM_PROVIDER`
- `SWITCHBOARD_LLM_MODEL`
- `SWITCHBOARD_LLM_MAX_TOKENS`
- `SWITCHBOARD_LLM_TEMPERATURE`
- `SWITCHBOARD_OFFLINE`
- `SWITCHBOARD_HIERARCHICAL`

Behavior notes:

- Set `SWITCHBOARD_OFFLINE=1` to force placeholder or offline-safe behavior where supported.
- Set `SWITCHBOARD_HIERARCHICAL=1` to use the hierarchical router path.
- The loader checks known local `.env` files and does not overwrite existing environment variables.

## Understand The Outputs

The routing decision contains:

- `classification`: the detected task type and confidence
- `plan`: the execution plan and step breakdown
- `metadata`: diagnostic routing details

Typical metadata fields include:

- low-confidence override state
- forced-agent usage
- validation errors
- original classification
- strategy
- complexity score
- MCTS usage
- estimated cost
- estimated latency

When you use `--json` or `--route-only`, the CLI prints the structured routing decision instead of the final execution output.

## Health Checks

Switchboard includes health checks for the core subsystems.

```python
from switchboard import create_default_health_checker, print_health_report

create_default_health_checker()
print_health_report()
```

Programmatic usage:

```python
from switchboard import HealthChecker, check_classifier, check_router

checker = HealthChecker()
checker.register("classifier", check_classifier)
checker.register("router", check_router)

results = checker.check_all()
for result in results:
    print(result.name, result.healthy, result.message)
```

Use health checks when:

- routing unexpectedly falls back to general
- model selection is not behaving as expected
- you need to verify agent loading or telemetry availability

## Testing

Run the full test suite:

```bash
pytest tests/ -v
```

Run a specific test file:

```bash
pytest tests/test_routing.py -v
```

Run with coverage:

```bash
pytest tests/ --cov=. --cov-report=html
```

If you are changing routing behavior, prioritize:

- `tests/test_routing.py`
- `tests/test_execution.py`
- `tests/test_mcts.py`
- `tests/test_policy.py`
- `tests/test_hierarchical_router.py`

## Troubleshooting

### No prompt output

If you run the CLI without input and without stdin, it prints demo prompts. Provide `--input`, positional text, or pipe input through stdin.

### Unexpected general fallback

Check:

- `low_confidence_threshold`
- classifier confidence
- whether a forced agent is set
- whether `SWITCHBOARD_HIERARCHICAL` changed the execution path

### Missing provider credentials

If live LLM-backed behavior is expected, confirm that the relevant API key exists in the environment or `.env` file.

### Want route inspection without execution

Use:

```bash
switchboard --route-only --verbose --input "your prompt here"
```

### Want deterministic local runs

Use offline mode or keep execution focused on routing output only:

```bash
SWITCHBOARD_OFFLINE=1 switchboard --route-only --input "test prompt"
```

## Recommended Workflow

1. Install in editable mode.
2. Run `switchboard --route-only` on a few representative prompts.
3. Add or adjust configuration if routing is too aggressive or too permissive.
4. Run the relevant tests.
5. Re-run the CLI with `--verbose` or `--json` to confirm the final behavior.

## Reference Map

- `switchboard/__init__.py`: public exports
- `switchboard/router.py`: CLI and routing orchestration
- `switchboard/config.py`: configuration model and validation
- `switchboard/env.py`: environment loading and offline mode
- `switchboard/execution.py`: execution engine
- `switchboard/planner.py`: plan construction
- `switchboard/classifier.py`: intent classification
- `switchboard/mcts_router.py`: MCTS model selection
- `switchboard/health.py`: health checks

## Minimal Example

```python
from switchboard import Router, ExecutionEngine

router = Router()
decision = router.route("analyze this code and write tests")

print(decision.classification.task_id)
print(decision.plan.strategy)

engine = ExecutionEngine(router)
result = engine.execute("analyze this code and write tests")
print(result.success)
print(result.output)
```

## Summary

Use `switchboard` for CLI execution, `Router` for routing-only workflows, and `ExecutionEngine` for full routing plus execution. Start with `--route-only` or `--json` when validating behavior, then move to full execution once the routing output matches what you expect.
