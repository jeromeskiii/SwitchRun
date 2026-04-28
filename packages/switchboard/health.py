"""Health check utilities for Switchboard."""

import sys
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class HealthStatus:
    """Health check result."""
    name: str
    healthy: bool
    message: str
    details: Optional[Dict] = None


class HealthChecker:
    """Performs health checks on Switchboard components."""

    def __init__(self):
        self.checks: Dict[str, callable] = {}

    def register(self, name: str, check_fn: callable) -> None:
        """Register a health check function."""
        self.checks[name] = check_fn

    def check(self, name: str) -> HealthStatus:
        """Run a specific health check."""
        if name not in self.checks:
            return HealthStatus(name, False, f"Unknown check: {name}")
        try:
            return self.checks[name]()
        except Exception as e:
            return HealthStatus(name, False, f"Check failed: {e}")

    def check_all(self) -> List[HealthStatus]:
        """Run all registered health checks."""
        results = []
        for name in sorted(self.checks.keys()):
            results.append(self.check(name))
        return results

    def is_healthy(self) -> bool:
        """Check if all components are healthy."""
        results = self.check_all()
        return all(r.healthy for r in results)


def check_classifier() -> HealthStatus:
    """Check if classifier is working."""
    try:
        from switchboard.classifier import Classifier

        classifier = Classifier()
        result = classifier.classify("test input")
        return HealthStatus(
            "classifier",
            True,
            f"Classifier operational (task_id={result.task_id.value})",
            {"confidence": result.confidence},
        )
    except Exception as e:
        return HealthStatus("classifier", False, f"Classifier error: {e}")


def check_router() -> HealthStatus:
    """Check if router is working."""
    try:
        from switchboard.router import Router

        router = Router()
        decision = router.route("test input")
        strategy = decision.plan.strategy if decision.plan else "unknown"
        task_id = decision.classification.task_id.value if decision.classification else "unknown"
        return HealthStatus(
            "router",
            True,
            f"Router operational (task={task_id})",
            {"strategy": strategy},
        )
    except Exception as e:
        return HealthStatus("router", False, f"Router error: {e}")


def check_telemetry() -> HealthStatus:
    """Check if telemetry is working."""
    try:
        from switchboard.telemetry import get_telemetry

        telemetry = get_telemetry()
        return HealthStatus(
            "telemetry",
            True,
            "Telemetry operational",
            {"metrics_available": True},
        )
    except Exception as e:
        return HealthStatus("telemetry", False, f"Telemetry error: {e}")


def check_agents() -> HealthStatus:
    """Check if agents are loadable."""
    try:
        from switchboard.canonical_ids import AgentID
        from switchboard.router import Router

        router = Router()
        available_agents = list(AgentID)
        return HealthStatus(
            "agents",
            True,
            f"Agents loadable ({len(available_agents)} agent types)",
            {"agent_count": len(available_agents)},
        )
    except Exception as e:
        return HealthStatus("agents", False, f"Agents error: {e}")


def check_models() -> HealthStatus:
    """Check if MCTS models are configured."""
    try:
        from switchboard.mcts_router import DEFAULT_MODELS

        return HealthStatus(
            "models",
            True,
            f"MCTS models configured ({len(DEFAULT_MODELS)} models)",
            {"model_count": len(DEFAULT_MODELS)},
        )
    except Exception as e:
        return HealthStatus("models", False, f"Models error: {e}")


def create_default_health_checker() -> HealthChecker:
    """Create a health checker with default checks."""
    checker = HealthChecker()
    checker.register("classifier", check_classifier)
    checker.register("router", check_router)
    checker.register("telemetry", check_telemetry)
    checker.register("agents", check_agents)
    checker.register("models", check_models)
    return checker


def print_health_report() -> int:
    """Print health report and return exit code."""
    checker = create_default_health_checker()
    results = checker.check_all()

    print("Switchboard Health Report")
    print("=" * 50)

    healthy_count = 0
    for result in results:
        status = "✓" if result.healthy else "✗"
        print(f"{status} {result.name}: {result.message}")
        if result.details:
            for key, value in result.details.items():
                print(f"    {key}: {value}")
        if result.healthy:
            healthy_count += 1

    print("=" * 50)
    print(f"Status: {healthy_count}/{len(results)} checks passed")

    return 0 if checker.is_healthy() else 1


if __name__ == "__main__":
    sys.exit(print_health_report())
