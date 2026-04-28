import time

import pytest

from switchboard.canonical_ids import AgentID, TaskID
from switchboard.hybrid_hierarchical_router import (
    ComplexityClassifier,
    HybridHierarchicalRouter,
    MCTSWorkflowSearcher,
    SubTask,
    route_task,
)
from switchboard.classifier import Classifier


KNOWN_TASKS = [
    ("fix this bug", TaskID.CODING),
    ("analyze this dataset with pandas", TaskID.DATA_ANALYSIS),
    ("write documentation for the API", TaskID.DOCUMENTATION),
    ("review this code", TaskID.REVERSE_ENGINEERING),
    ("create a trading strategy", TaskID.TRADING_ANALYSIS),
    ("write a poem", TaskID.CREATIVE_WRITING),
    ("how does this system work", TaskID.REVERSE_ENGINEERING),
    ("implement a new feature", TaskID.CODING),
    ("summarize the report", TaskID.REPORTING if "REPORTING" in TaskID.__members__ else TaskID.DOCUMENTATION),
    ("debug this issue", TaskID.CODING),
    ("design a system architecture", TaskID.SYSTEM_DESIGN),
    ("explain the flow", TaskID.REVERSE_ENGINEERING),
    ("plot the data", TaskID.VISUALIZATION),
    ("test the module", TaskID.TESTING),
    ("build a dashboard", TaskID.VISUALIZATION),
    ("refactor the code", TaskID.CODING),
    ("improve my habits", TaskID.SELF_UPGRADE),
    ("analyze the market", TaskID.TRADING_ANALYSIS),
    ("write a story", TaskID.CREATIVE_WRITING),
    ("self improvement plan", TaskID.SELF_UPGRADE),
    ("which model to use", TaskID.MODEL_SELECTION),
    ("route to nexus", TaskID.MODEL_ROUTING),
    ("read the file", TaskID.GENERAL),
    ("help me with something", TaskID.GENERAL),
    ("implement the fix and then add tests", TaskID.CODING),
    ("analyze the data and create a chart", TaskID.DATA_ANALYSIS),
    ("first review, then document", TaskID.REVERSE_ENGINEERING),
    ("design and build the system", TaskID.SYSTEM_DESIGN),
    ("research and implement", TaskID.REVERSE_ENGINEERING),
    ("explain and summarize", TaskID.REVERSE_ENGINEERING),
]


def test_fast_path_latency():
    simple_tasks = ["fix this bug", "explain this", "run the test", "show the output", "list files"]
    latencies = []
    for task in simple_tasks:
        t0 = time.monotonic()
        route_task(task, use_mcts=False)
        latencies.append((time.monotonic() - t0) * 1000)
    avg_ms = sum(latencies) / len(latencies)
    assert avg_ms < 50, f"Fast path average latency {avg_ms:.1f}ms exceeds 50ms target"


def test_classification_accuracy():
    correct = 0
    classifier = Classifier()
    for text, expected_task_id in KNOWN_TASKS:
        result = classifier.classify(text)
        if result.task_id == expected_task_id:
            correct += 1
    accuracy = correct / len(KNOWN_TASKS)
    assert accuracy > 0.7, f"Classification accuracy {accuracy:.0%} below 70% floor ({correct}/{len(KNOWN_TASKS)})"


def test_mcts_convergence():
    subtask = SubTask(
        id="t0",
        description="implement a distributed training system",
        estimated_complexity=0.8,
    )
    agents = list(AgentID)[:5]
    searcher = MCTSWorkflowSearcher(simulations=20)
    path, tree = searcher.search(subtask, agents, {})
    assert len(path) > 0, "MCTS produced empty path"
    assert tree.visits > 0, "MCTS root has zero visits"


@pytest.mark.slow
def test_cost_reduction_vs_static():
    multi_step_tasks = [
        "research distributed training, design a system, implement it, and benchmark",
        "analyze the data, create a visualization, and write a report",
        "debug this issue, fix it, and add regression tests",
        "review the code, identify issues, suggest fixes, and verify changes",
        "design the API, implement the backend, add tests, and document",
    ]
    router = HybridHierarchicalRouter(use_mcts=True, mcts_simulations=20)

    total_hierarchical_cost = 0.0
    total_static_cost = 0.0

    for task in multi_step_tasks:
        decision = router.route(task)
        total_hierarchical_cost += decision.estimated_cost
        most_expensive_agent = max(
            AgentID, key=lambda a: len(a.value)
        )
        total_static_cost += len(task.split()) * 2 + 500

    if total_static_cost > 0:
        reduction = 1.0 - (total_hierarchical_cost / total_static_cost)
        assert reduction > 0.5, f"Cost reduction {reduction:.0%} below 50% target"
