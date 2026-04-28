#!/usr/bin/env python3
"""Demo of MCTS-based model routing for Switchboard.

Usage:
    python -m switchboard.mcts_demo
"""

from switchboard.mcts_router import (
    ModelSelectionMCTS,
    TaskFeatures,
    DEFAULT_MODELS,
    create_mcts_router,
)
from switchboard.mcts_classifier import MCTSEnhancedClassifier


def demo_basic_mcts():
    """Demonstrate basic MCTS model selection."""
    print("=" * 60)
    print("MCTS Model Router Demo")
    print("=" * 60)

    # Create router
    router = create_mcts_router(budget=100)

    print("\n📊 Available Models:")
    print("-" * 40)
    for model in DEFAULT_MODELS:
        print(
            f"  {model.id:20} | ${model.cost_per_1k_tokens:>7}/1K | {model.avg_latency_ms}ms"
        )

    # Test different task types
    test_tasks = [
        TaskFeatures(
            complexity="high",
            estimated_tokens=2000,
            requires_code=True,
            requires_creativity=False,
            requires_reasoning=True,
            domain="coding",
            urgency="medium",
        ),
        TaskFeatures(
            complexity="low",
            estimated_tokens=500,
            requires_code=False,
            requires_creativity=False,
            requires_reasoning=False,
            domain="general",
            urgency="high",
        ),
        TaskFeatures(
            complexity="medium",
            estimated_tokens=1500,
            requires_code=False,
            requires_creativity=True,
            requires_reasoning=True,
            domain="writing",
            urgency="low",
        ),
        TaskFeatures(
            complexity="high",
            estimated_tokens=5000,
            requires_code=True,
            requires_creativity=False,
            requires_reasoning=True,
            domain="coding",
            urgency="low",
        ),
    ]

    task_names = [
        "Complex coding task",
        "Quick general query",
        "Creative writing",
        "Large code review",
    ]

    print("\n🎯 Model Selection Results:")
    print("-" * 60)

    for name, features in zip(task_names, test_tasks):
        result = router.select_model(features)

        print(f"\n  Task: {name}")
        print(f"    Domain: {features.domain}, Complexity: {features.complexity}")
        print(f"    Tokens: {features.estimated_tokens}, Urgency: {features.urgency}")
        print(f"    → Selected: {result.model.name} ({result.model.id})")
        print(f"    → Confidence: {result.confidence:.2%}")
        print(f"    → Expected Reward: {result.expected_reward:.3f}")
        print(f"    → Simulations: {result.simulations_run}")
        print(f"    → Selection Path: {' → '.join(result.selection_path)}")


def demo_with_classifier():
    """Demonstrate MCTS-enhanced classifier."""
    print("\n" + "=" * 60)
    print("MCTS-Enhanced Classifier Demo")
    print("=" * 60)

    classifier = MCTSEnhancedClassifier(use_mcts_routing=True, mcts_budget=50)

    test_inputs = [
        "Write a Python function to implement quicksort",
        "Explain quantum computing in simple terms",
        "Quick: what's 2+2?",
        "Analyze this dataset and create visualizations",
        "Design a scalable microservices architecture",
    ]

    print("\n📝 Text Classification + Model Selection:")
    print("-" * 60)

    for text in test_inputs:
        result = classifier.classify(text)
        mcts_info = (
            result.metadata.get("mcts_model_selection", {}) if result.metadata else {}
        )

        print(
            f'\n  Input: "{text[:50]}..." '
            if len(text) > 50
            else f'\n  Input: "{text}"'
        )
        print(f"    Task: {result.task_id.value}")
        print(f"    Confidence: {result.confidence:.2f}")
        if mcts_info:
            print(
                f"    → Model: {mcts_info.get('model_name')} ({mcts_info.get('model_id')})"
            )
            print(f"    → MCTS Confidence: {mcts_info.get('confidence', 0):.2%}")
            print(f"    → Simulations: {mcts_info.get('simulations', 0)}")


def demo_performance_learning():
    """Demonstrate online learning from actual performance."""
    print("\n" + "=" * 60)
    print("Online Performance Learning Demo")
    print("=" * 60)

    router = create_mcts_router(budget=50)

    features = TaskFeatures(
        complexity="medium",
        estimated_tokens=1000,
        requires_code=True,
        requires_creativity=False,
        requires_reasoning=True,
        domain="coding",
        urgency="medium",
    )

    print("\n📈 Initial Selection (No History):")
    result1 = router.select_model(features)
    print(f"  → Selected: {result1.model.name}")
    print(f"  → Expected Reward: {result1.expected_reward:.3f}")

    # Simulate some performance feedback
    print("\n🔄 Simulating Performance Feedback:")

    # Model performed well
    router.update_performance(result1.model.id, 0.95)
    print(f"  → {result1.model.id}: High performance (0.95)")

    # Another model performed poorly
    other_model = [m for m in DEFAULT_MODELS if m.id != result1.model.id][0]
    router.update_performance(other_model.id, 0.3)
    print(f"  → {other_model.id}: Low performance (0.30)")

    print("\n📈 Selection After Learning:")
    result2 = router.select_model(features)
    print(f"  → Selected: {result2.model.name}")
    print(f"  → Expected Reward: {result2.expected_reward:.3f}")
    print(
        f"  → Historical Influence: {'Yes' if result2.expected_reward != result1.expected_reward else 'No'}"
    )


def main():
    """Run all demos."""
    demo_basic_mcts()
    demo_with_classifier()
    demo_performance_learning()

    print("\n" + "=" * 60)
    print("✅ Demo Complete!")
    print("=" * 60)
    print("\nTo use MCTS routing in your code:")
    print("  from switchboard.mcts_classifier import MCTSEnhancedClassifier")
    print("  classifier = MCTSEnhancedClassifier(use_mcts_routing=True)")
    print("  result = classifier.classify('your task here')")


if __name__ == "__main__":
    main()
