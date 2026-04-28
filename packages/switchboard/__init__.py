"""Public API for the Switchboard package."""

from switchboard.agents import Agent, AgentResult
from switchboard.agents import (
    AgentRuntimeAgent,
    CodingAgent,
    CreativeWritingAgent,
    DataAnalysisAgent,
    DocumentationAgent,
    GeneralAgent,
    MasterAlphaAgent,
    MythosAgent,
    NexusAgent,
    PantheonAgent,
    ReverseEngineeringAgent,
    SelfUpgradeAgent,
    TradingAnalysisAgent,
)
from switchboard.canonical_ids import (
    AgentID,
    TaskID,
    TASK_TO_AGENT,
    resolve_task_to_agent,
)
from switchboard.classifier import ClassificationResult, Classifier
from switchboard.config import SwitchboardConfig
from switchboard.execution import ExecutionEngine, ExecutionResult
from switchboard.health import (
    HealthChecker,
    HealthStatus,
    check_classifier,
    check_router,
    check_telemetry,
    create_default_health_checker,
    print_health_report,
)
from switchboard.planner import ExecutionPlan, ExecutionStep, Planner
from switchboard.router import Router, RoutingDecision, RoutingMetadata, execute, route, run

# Telemetry
from switchboard.telemetry import (
    SwitchboardTelemetry,
    get_telemetry,
    initialize,
    start_metrics_server,
)

# MCTS routing components
from switchboard.mcts_router import (
    ModelSelectionMCTS,
    ModelSpec,
    TaskFeatures,
    SelectionResult,
    DEFAULT_MODELS,
    create_mcts_router,
)
from switchboard.mcts_classifier import MCTSEnhancedClassifier

__all__ = [
    "Agent",
    "AgentID",
    "AgentResult",
    "AgentRuntimeAgent",
    "check_classifier",
    "check_router",
    "check_telemetry",
    "ClassificationResult",
    "Classifier",
    "CodingAgent",
    "create_default_health_checker",
    "create_mcts_router",
    "CreativeWritingAgent",
    "DataAnalysisAgent",
    "DocumentationAgent",
    "execute",
    "ExecutionEngine",
    "ExecutionPlan",
    "ExecutionResult",
    "ExecutionStep",
    "GeneralAgent",
    "get_telemetry",
    "HealthChecker",
    "HealthStatus",
    "initialize",
    "MasterAlphaAgent",
    "MCTSEnhancedClassifier",
    "ModelSelectionMCTS",
    "ModelSpec",
    "MythosAgent",
    "NexusAgent",
    "PantheonAgent",
    "Planner",
    "print_health_report",
    "resolve_task_to_agent",
    "ReverseEngineeringAgent",
    "route",
    "Router",
    "RoutingDecision",
    "RoutingMetadata",
    "run",
    "SelectionResult",
    "SelfUpgradeAgent",
    "start_metrics_server",
    "SwitchboardConfig",
    "SwitchboardTelemetry",
    "TASK_TO_AGENT",
    "TaskFeatures",
    "TaskID",
    "TradingAnalysisAgent",
]
