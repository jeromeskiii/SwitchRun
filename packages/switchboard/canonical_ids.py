# Copyright 2026 Human Systems. MIT License.
"""Canonical identifiers for tasks, agents, and their mappings.

This module defines the single source of truth for:
- Task IDs: what the classifier outputs
- Agent IDs: what the execution engine runs
- Task-to-Agent mapping: how tasks resolve to agents

Design principles:
- One canonical set of task IDs
- One canonical set of agent IDs
- Explicit mapping layer (no implicit aliasing across modules)
- All modules import from here for ID constants
"""

from enum import Enum
from typing import Final


class TaskID(str, Enum):
    """Canonical task identifiers output by the classifier.

    These represent the TYPES of work the system can classify.
    They are NOT agent names - they get mapped via TASK_TO_AGENT.
    """

    # Core task types
    REVERSE_ENGINEERING = "reverse_engineering"
    SYSTEM_DESIGN = "system_design"
    DATA_ANALYSIS = "data_analysis"
    VISUALIZATION = "visualization"
    CODING = "coding"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    REPORTING = "reporting"
    SELF_UPGRADE = "self_upgrade"
    TRADING_ANALYSIS = "trading_analysis"
    CREATIVE_WRITING = "creative_writing"

    # Model orchestration
    MODEL_ROUTING = "model_routing"
    MODEL_SELECTION = "model_selection"

    # Fallback
    GENERAL = "general"

    @classmethod
    def all(cls) -> set["TaskID"]:
        """Return all valid task IDs."""
        return set(cls)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid task ID."""
        try:
            cls(value)
            return True
        except ValueError:
            return False

    @classmethod
    def from_string(cls, value: str) -> "TaskID":
        """Convert string to TaskID, returning GENERAL for unknown values."""
        try:
            return cls(value)
        except ValueError:
            return cls.GENERAL


class AgentID(str, Enum):
    """Canonical agent identifiers used by the execution engine.

    These represent the ACTUAL AGENTS that can be executed.
    Each maps to a concrete Agent implementation.
    """

    REVERSE_ENGINEERING = "reverse_engineering"
    DATA_ANALYSIS = "data_analysis"
    CODING = "coding"
    DOCUMENTATION = "documentation"
    SELF_UPGRADE = "self_upgrade"
    TRADING_ANALYSIS = "trading_analysis"
    CREATIVE_WRITING = "creative_writing"
    MASTER_ALPHA = "master_alpha"
    NEXUS = "nexus"
    AGENT_RUNTIME = "agent_runtime"
    MYTHOS = "mythos"
    PANTHEON = "pantheon"
    GENERAL = "general"

    @classmethod
    def all(cls) -> set["AgentID"]:
        """Return all valid agent IDs."""
        return set(cls)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a string is a valid agent ID."""
        try:
            cls(value)
            return True
        except ValueError:
            return False

    @classmethod
    def from_string(cls, value: str) -> "AgentID":
        """Convert string to AgentID, returning GENERAL for unknown values."""
        try:
            return cls(value)
        except ValueError:
            return cls.GENERAL


# Canonical mapping from TaskID to AgentID
# This is the ONLY place where task->agent resolution happens
TASK_TO_AGENT: Final[dict[TaskID, AgentID]] = {
    # Reverse engineering handles multiple related tasks
    TaskID.REVERSE_ENGINEERING: AgentID.REVERSE_ENGINEERING,
    TaskID.SYSTEM_DESIGN: AgentID.REVERSE_ENGINEERING,
    # Data analysis handles data and visualization
    TaskID.DATA_ANALYSIS: AgentID.DATA_ANALYSIS,
    TaskID.VISUALIZATION: AgentID.DATA_ANALYSIS,
    # Coding handles implementation and testing
    TaskID.CODING: AgentID.CODING,
    TaskID.TESTING: AgentID.CODING,
    # Documentation handles docs and reports
    TaskID.DOCUMENTATION: AgentID.DOCUMENTATION,
    TaskID.REPORTING: AgentID.DOCUMENTATION,
    TaskID.SELF_UPGRADE: AgentID.SELF_UPGRADE,
    TaskID.TRADING_ANALYSIS: AgentID.TRADING_ANALYSIS,
    TaskID.CREATIVE_WRITING: AgentID.CREATIVE_WRITING,
    # MasterAlpha can handle any complex routing
    # Note: Access via force_agent="master_alpha"
    # Nexus handles model routing/orchestration tasks
    TaskID.MODEL_ROUTING: AgentID.NEXUS,
    TaskID.MODEL_SELECTION: AgentID.NEXUS,
    # Agent Runtime for tool execution
    # Note: Access via force_agent="agent_runtime"
    # Fallback
    TaskID.GENERAL: AgentID.GENERAL,
}


def resolve_task_to_agent(task_id: TaskID | str) -> AgentID:
    """Resolve a task ID to its corresponding agent ID.

    Args:
        task_id: A TaskID enum or string representation

    Returns:
        The AgentID that should handle this task

    Raises:
        TypeError: If task_id is not a TaskID or string
    """
    if isinstance(task_id, str):
        task_id = TaskID.from_string(task_id)
    return TASK_TO_AGENT.get(task_id, AgentID.GENERAL)


def get_agent_for_task(task: str) -> str:
    """Convenience function to get agent name for a task string.

    This is provided for backward compatibility during migration.

    Args:
        task: A task name string

    Returns:
        The agent name that should handle this task
    """
    task_id = TaskID.from_string(task)
    agent_id = resolve_task_to_agent(task_id)
    return agent_id.value
