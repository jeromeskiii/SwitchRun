"""Prometheus telemetry for Switchboard routing metrics."""

import logging
from typing import Optional

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    start_http_server,
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
)

logger = logging.getLogger(__name__)

try:
    from photonic import PhotonicBus
    _PHOTONIC_AVAILABLE = True
except ImportError:
    _PHOTONIC_AVAILABLE = False


class SwitchboardTelemetry:
    """Prometheus metrics collector for Switchboard routing decisions."""

    NAMESPACE = "switchboard"

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self._registry = registry or CollectorRegistry()

        self._info = Info(
            "version",
            "Switchboard version info",
            registry=self._registry,
        )
        self._info.info({"version": "2.0.0", "architecture": "hybrid_hierarchical"})

        self._routing_decisions = Counter(
            "routing_decisions_total",
            "Total routing decisions",
            ["task_id", "agent_id", "strategy"],
            registry=self._registry,
        )

        self._routing_latency = Histogram(
            "routing_latency_seconds",
            "Routing decision latency",
            ["strategy"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self._registry,
        )

        self._model_selections = Counter(
            "model_selections_total",
            "Total model selections",
            ["model_name", "provider"],
            registry=self._registry,
        )

        self._execution_results = Counter(
            "execution_results_total",
            "Total execution results",
            ["success", "fallback_used"],
            registry=self._registry,
        )

        self._classifications = Counter(
            "task_classifications_total",
            "Total task classifications",
            ["task_id"],
            registry=self._registry,
        )

        self._cost_estimate = Gauge(
            "cost_estimate_dollars",
            "Estimated cost in dollars",
            ["model_name"],
            registry=self._registry,
        )

        self._active_requests = Gauge(
            "active_requests",
            "Number of active requests",
            registry=self._registry,
        )

        self._mcts_simulations = Histogram(
            "mcts_simulations_total",
            "MCTS simulation count per decision",
            buckets=(10, 20, 30, 50, 75, 100, 150, 200),
            registry=self._registry,
        )

        self._fallback_triggered = Counter(
            "fallback_triggered_total",
            "Total fallback agent triggers",
            ["original_agent", "fallback_agent"],
            registry=self._registry,
        )

        self._photonic_emitted = Gauge(
            "photonic_events_emitted_total",
            "Total events emitted through Photonic bus",
            registry=self._registry,
        )

        self._photonic_dropped = Gauge(
            "photonic_events_dropped_total",
            "Total events dropped by Photonic bus (backpressure)",
            registry=self._registry,
        )

        self._server = None

    def record_routing_decision(
        self,
        task_id: str,
        agent_id: str,
        strategy: str,
        latency_ms: float,
        confidence: float,
        mcts_used: bool = False,
    ) -> None:
        """Record a routing decision."""
        self._routing_decisions.labels(
            task_id=task_id,
            agent_id=agent_id,
            strategy=strategy,
        ).inc()

        self._routing_latency.labels(strategy=strategy).observe(latency_ms / 1000.0)

        if mcts_used:
            self._mcts_simulations.observe(50)

    def record_model_selection(
        self,
        model_name: str,
        provider: str,
        latency_ms: float,
        cost: float,
        confidence: float,
    ) -> None:
        """Record a model selection decision."""
        self._model_selections.labels(
            model_name=model_name,
            provider=provider,
        ).inc()

        self._cost_estimate.labels(model_name=model_name).set(cost)

    def record_execution(
        self,
        success: bool,
        fallback_used: bool,
        latency_ms: float,
    ) -> None:
        """Record an execution result."""
        self._execution_results.labels(
            success=str(success).lower(),
            fallback_used=str(fallback_used).lower(),
        ).inc()

    def record_classification(
        self,
        task_id: str,
        confidence: float,
    ) -> None:
        """Record a task classification."""
        self._classifications.labels(task_id=task_id).inc()

    def record_fallback(
        self,
        original_agent: str,
        fallback_agent: str,
    ) -> None:
        """Record a fallback trigger."""
        self._fallback_triggered.labels(
            original_agent=original_agent,
            fallback_agent=fallback_agent,
        ).inc()

    def record_mcts_simulation(self, simulations: int) -> None:
        """Record MCTS simulation count."""
        self._mcts_simulations.observe(simulations)

    def sync_photonic_metrics(self) -> None:
        """Pull current Photonic bus stats into Prometheus gauges."""
        if not _PHOTONIC_AVAILABLE:
            return
        try:
            metrics = PhotonicBus.instance().metrics()
            self._photonic_emitted.set(metrics.get("total_emitted", 0))
            self._photonic_dropped.set(metrics.get("total_dropped", 0))
        except Exception:
            pass

    def get_metrics(self) -> bytes:
        """Get current metrics in Prometheus format."""
        return generate_latest(self._registry)

    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        return CONTENT_TYPE_LATEST

    def start_server(self, port: int = 9100, host: str = "0.0.0.0") -> None:
        """Start Prometheus metrics HTTP server."""
        if self._server:
            logger.warning("Metrics server already started")
            return

        try:
            start_http_server(port, host=host, registry=self._registry)
            self._server = (host, port)
            logger.info(f"Prometheus metrics server started on {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            raise

    def stop_server(self) -> None:
        """Stop Prometheus metrics HTTP server."""
        if self._server:
            logger.info(f"Stopping metrics server on {self._server}")
            self._server = None

    def __enter__(self) -> "SwitchboardTelemetry":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_server()


_TELEMETRY: Optional[SwitchboardTelemetry] = None


def get_telemetry() -> SwitchboardTelemetry:
    """Get global telemetry instance."""
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = SwitchboardTelemetry()
    return _TELEMETRY


def initialize() -> SwitchboardTelemetry:
    """Initialize global telemetry instance."""
    return get_telemetry()


def start_metrics_server(port: int = 9100, host: str = "0.0.0.0") -> None:
    """Start the global metrics server."""
    get_telemetry().start_server(port=port, host=host)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Switchboard Prometheus Metrics")
    parser.add_argument("--port", type=int, default=9100, help="Port to serve metrics")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    telemetry = SwitchboardTelemetry()
    telemetry.start_server(port=args.port, host=args.host)

    import time

    while True:
        time.sleep(60)
