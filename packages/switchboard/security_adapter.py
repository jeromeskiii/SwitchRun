# Copyright 2026 Human Systems. MIT License.
"""Security Adapter for Switchboard Router

Integrates Governed Runtime security layer with MasterNexusZero switchboard.
Wraps routing and execution with policy evaluation and audit trails.

Usage:
    from switchboard.security_adapter import SecureRouter, SecureExecutionEngine

    # Wrap existing router
    router = SecureRouter(base_router)

    # Route with security checks
    decision = router.route(input_text, user_id="user-123")

    # Execute with sandboxing
    engine = SecureExecutionEngine(router)
    result = engine.execute(input_text, user_id="user-123")
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import os

# nexus_memory is optional — degrade gracefully if not installed.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from nexus_memory import NexusMemory as _NexusMemory  # type: ignore[import]
    _NEXUS_MEMORY_AVAILABLE = True
except ImportError:
    _NexusMemory = None  # type: ignore[assignment,misc]
    _NEXUS_MEMORY_AVAILABLE = False

# Switchboard imports
from switchboard.router import Router, RoutingDecision
from switchboard.execution import ExecutionEngine, ExecutionResult
from switchboard.canonical_ids import AgentID
from switchboard.config import SwitchboardConfig

logger = logging.getLogger(__name__)


@dataclass
class SecurityPolicy:
    """Security policy for agent execution."""

    agent_tier: str = "domain"  # core, domain, utility, meta
    allow_file_read: list[str] = field(default_factory=lambda: ["./**/*"])
    allow_file_write: list[str] = field(default_factory=list)
    allow_commands: list[str] = field(default_factory=list)
    allow_shell: bool = False
    max_execution_time: int = 120000  # 2 minutes
    require_approval: bool = False


@dataclass
class SecurityDecision:
    """Result of security policy evaluation."""

    outcome: str  # "allow", "deny", "ask"
    agent_id: str
    reason: Optional[str] = None
    policy: Optional[SecurityPolicy] = None
    requires_approval: bool = False
    audit_event_id: Optional[str] = None


class SecurityAdapter:
    """Adapts Governed Runtime security for switchboard integration."""

    # Agent tier mapping
    AGENT_TIERS = {
        # Core agents - full access
        "hephaestus": "core",
        "sisyphus": "core",
        "prometheus": "core",
        "ultrawork": "core",
        "mcts-e": "core",
        # Domain agents - restricted
        "coding": "domain",
        "data_analysis": "domain",
        "reverse_engineering": "domain",
        "documentation": "domain",
        "trading_analysis": "domain",
        "creative_writing": "domain",
        "self_upgrade": "domain",
        # Utility agents - minimal
        "file_reader": "utility",
        "formatter": "utility",
        # Meta agents - read-only
        "mnemosyne": "meta",
        "auditor": "meta",
        "observer": "meta",
        # Default
        "general": "domain",
    }

    # Tier capabilities
    TIER_POLICIES = {
        "core": SecurityPolicy(
            agent_tier="core",
            allow_file_read=["**/*"],
            allow_file_write=["**/*"],
            allow_commands=[
                "python3", "python", "node", "npm", "pnpm", "yarn",
                "git", "pip", "pip3", "ruff", "pyright",
                "ruff", "mypy", "pytest", "ruff",
                "cargo", "go", "make", "cmake",
            ],
            allow_shell=True,
            max_execution_time=300000,
            require_approval=False,
        ),
        "domain": SecurityPolicy(
            agent_tier="domain",
            allow_file_read=["data/**/*", "src/**/*", "docs/**/*", "config/**/*"],
            allow_file_write=["output/**/*", "temp/**/*", "logs/**/*"],
            allow_commands=["git", "npm", "node", "pip", "grep", "ls", "find", "wc"],
            allow_shell=False,
            max_execution_time=120000,
            require_approval=False,
        ),
        "utility": SecurityPolicy(
            agent_tier="utility",
            allow_file_read=["input/**/*"],
            allow_file_write=["output/**/*"],
            allow_commands=["cat", "grep", "wc", "head", "tail"],
            allow_shell=False,
            max_execution_time=30000,
            require_approval=False,
        ),
        "meta": SecurityPolicy(
            agent_tier="meta",
            allow_file_read=["logs/**/*", "metrics/**/*", "audit/**/*"],
            allow_file_write=["reports/**/*"],
            allow_commands=["ls", "cat", "ps", "top", "df"],
            allow_shell=False,
            max_execution_time=10000,
            require_approval=True,
        ),
    }

    def __init__(self, memory: Optional[Any] = None):
        self.memory = memory
        if self.memory is None and _NEXUS_MEMORY_AVAILABLE:
            self.memory = _NexusMemory()
        self.audit_events: list[dict] = []

    def get_agent_tier(self, agent_id: str) -> str:
        """Get security tier for an agent."""
        return self.AGENT_TIERS.get(agent_id.lower(), "domain")

    def get_policy(self, agent_id: str) -> SecurityPolicy:
        """Get security policy for an agent."""
        tier = self.get_agent_tier(agent_id)
        return self.TIER_POLICIES.get(tier, self.TIER_POLICIES["domain"])

    def evaluate_policy(
        self, agent_id: str, action: str, args: dict[str, Any], user_id: Optional[str] = None
    ) -> SecurityDecision:
        """Evaluate security policy for an action.

        Args:
            agent_id: The agent performing the action
            action: The action type (e.g., "read_file", "run_command")
            args: Action arguments
            user_id: Optional user ID for context

        Returns:
            SecurityDecision with outcome and policy
        """
        policy = self.get_policy(agent_id)

        # Check file operations
        if action == "read_file":
            path = args.get("path", "")
            if not self._path_allowed(path, policy.allow_file_read):
                return SecurityDecision(
                    outcome="deny",
                    agent_id=agent_id,
                    reason=f"Path '{path}' not in read allowlist",
                    policy=policy,
                )

        if action == "write_file":
            path = args.get("path", "")
            if not self._path_allowed(path, policy.allow_file_write):
                return SecurityDecision(
                    outcome="deny",
                    agent_id=agent_id,
                    reason=f"Path '{path}' not in write allowlist",
                    policy=policy,
                )

        # Check command execution
        if action == "run_command":
            cmd = args.get("cmd", "")
            command = cmd.split()[0] if cmd else ""

            # Check shell operators
            if not policy.allow_shell and self._has_shell_operators(cmd):
                return SecurityDecision(
                    outcome="deny",
                    agent_id=agent_id,
                    reason="Shell operators not allowed",
                    policy=policy,
                )

            # Check command whitelist
            if "*" not in policy.allow_commands and command not in policy.allow_commands:
                return SecurityDecision(
                    outcome="deny",
                    agent_id=agent_id,
                    reason=f"Command '{command}' not in allowlist",
                    policy=policy,
                )

        # Check approval requirement
        if policy.require_approval:
            return SecurityDecision(
                outcome="ask",
                agent_id=agent_id,
                reason="Agent tier requires approval",
                policy=policy,
                requires_approval=True,
            )

        return SecurityDecision(outcome="allow", agent_id=agent_id, policy=policy)

    def record_audit(
        self,
        event_type: str,
        agent_id: str,
        action: str,
        outcome: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Record audit event to NexusMemory.

        Returns:
            Event ID
        """
        event_id = f"{datetime.now(timezone.utc).isoformat()}-{agent_id}"

        event = {
            "id": event_id,
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "action": action,
            "outcome": outcome,
            "user_id": user_id,
            "metadata": metadata or {},
        }

        self.audit_events.append(event)

        # Record to NexusMemory
        if user_id and self.memory is not None:
            self.memory.record_agent_performance(
                agent_id=agent_id,
                task_type=action,
                task_summary=json.dumps(metadata or {}),
                success=(outcome == "allow"),
                user_feedback=event.get("reason", ""),
            )

        return event_id

    def _path_allowed(self, path: str, patterns: list[str]) -> bool:
        """Check if path matches any allowed pattern. Resolves symlinks for containment checks."""
        import fnmatch
        from pathlib import Path

        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError):
            return False

        for pattern in patterns:
            if fnmatch.fnmatch(str(resolved), pattern):
                return True
            if fnmatch.fnmatch(path, pattern):
                return True
            if pattern.endswith("/*") or pattern.endswith("/**/*"):
                prefix = pattern.rstrip("/*")
                try:
                    prefix_resolved = Path(prefix).resolve()
                    try:
                        resolved.relative_to(prefix_resolved)
                        return True
                    except ValueError:
                        pass
                except (OSError, RuntimeError):
                    pass
        return False

    def _has_shell_operators(self, cmd: str) -> bool:
        """Check for dangerous shell operators."""
        import re

        dangerous_pattern = re.compile(
            r"[;\|\&\`\$\(\)\{\}\<\>!]|"
            r"\$\{[^}]+\}|"
            r"\$\[[^\]]+\]|"
            r"\\.|"
            r"^\s*\|"
        )
        return bool(dangerous_pattern.search(cmd))


class SecureRouter:
    """Router with security policy enforcement.

    Wraps the base Router and adds:
    - Pre-routing security checks
    - Agent capability validation
    - Audit trail logging
    """

    def __init__(
        self,
        base_router: Router,
        security_adapter: Optional[SecurityAdapter] = None,
        config: Optional[SwitchboardConfig] = None,
    ):
        self.router = base_router
        self.security = security_adapter or SecurityAdapter()
        self.config = config or SwitchboardConfig()
        self.memory = _NexusMemory() if _NEXUS_MEMORY_AVAILABLE else None

    def route(
        self, input_text: str, user_id: Optional[str] = None, force_agent: Optional[str] = None
    ) -> RoutingDecision:
        """Route with security checks.

        Args:
            input_text: The user's input
            user_id: Optional user ID for audit trails
            force_agent: Optional agent to force

        Returns:
            RoutingDecision with security metadata
        """
        # Get routing decision
        decision = self.router.route(input_text, force_agent)

        # Get primary agent
        agent_id = decision.classification.task_id.value

        # Security check
        security_decision = self.security.evaluate_policy(
            agent_id=agent_id,
            action="route_task",
            args={"input": input_text[:100]},  # Truncate for privacy
            user_id=user_id,
        )

        # Record audit
        event_id = self.security.record_audit(
            event_type="routing",
            agent_id=agent_id,
            action="route",
            outcome=security_decision.outcome,
            user_id=user_id,
            metadata={
                "input_length": len(input_text),
                "confidence": decision.classification.confidence,
                "strategy": decision.plan.strategy,
            },
        )

        if security_decision.outcome == "deny":
            logger.warning("Routing denied for agent %s: %s", agent_id, security_decision.reason)
            # Override to general agent
            from switchboard.classifier import ClassificationResult
            from switchboard.canonical_ids import TaskID

            decision.classification = ClassificationResult(
                task_id=TaskID.GENERAL,
                confidence=0.5,
                reason=f"Security override: {security_decision.reason}",
                requires_multi_step=decision.classification.requires_multi_step,
            )
            decision.metadata.security_override = True
            decision.metadata.security_reason = security_decision.reason        # Store decision in memory
        if user_id and self.memory is not None:
            self.memory.add_message(
                user_id=user_id,
                role="system",
                content=f"Routed to {agent_id}",
                metadata={
                    "action": "route",
                    "agent_id": agent_id,
                    "confidence": decision.classification.confidence,
                    "security_outcome": security_decision.outcome,
                },
            )

        return decision

    def get_agent(self, agent_id: AgentID) -> Any:
        """Get agent from base router."""
        return self.router.get_agent(agent_id)


class SecureExecutionEngine:
    """Execution engine with security sandboxing.

    Wraps the base ExecutionEngine and adds:
    - Pre-execution security checks
    - Sandboxed execution (placeholder)
    - Enhanced audit logging
    """

    def __init__(
        self,
        router: SecureRouter,
        security_adapter: Optional[SecurityAdapter] = None,
        config: Optional[SwitchboardConfig] = None,
    ):
        self.router = router
        self.security = security_adapter or router.security
        self.config = config or SwitchboardConfig()
        self.memory = _NexusMemory() if _NEXUS_MEMORY_AVAILABLE else None
        self.base_engine = ExecutionEngine(router.router, config)

    def execute(
        self, input_text: str, user_id: Optional[str] = None, force_agent: Optional[str] = None
    ) -> ExecutionResult:
        """Execute with security checks.

        Args:
            input_text: The user's input
            user_id: Optional user ID for audit trails
            force_agent: Optional agent to force

        Returns:
            ExecutionResult with security metadata
        """
        # Validate input
        if len(input_text) > self.config.max_input_length:
            error_result = ExecutionResult(
                success=False,
                output="",
                primary_agent_id=AgentID.GENERAL,
                error=f"Input exceeds maximum length of {self.config.max_input_length}",
                metadata={"security_rejected": True},
            )
            return error_result

        # Route with security
        decision = self.router.route(input_text, user_id, force_agent)

        # Check if security overrode the decision — now a declared field.
        if decision.metadata.security_override:
            logger.info("Executing with security override: %s", decision.metadata.security_reason)

        # Execute with base engine
        result = self.base_engine.execute(input_text, force_agent)

        # Record execution in memory
        if user_id and self.memory is not None:
            self.memory.record_agent_performance(
                agent_id=result.primary_agent_id.value,
                task_type="execute",
                task_summary=input_text[:100],
                success=result.success,
                latency_ms=0,  # Would get from timing
                user_feedback=result.error if not result.success else None,
            )

        return result


# Convenience function for quick setup
def create_secure_router(config: Optional[SwitchboardConfig] = None, **kwargs) -> SecureRouter:
    """Create a secure router with all components.

    Args:
        config: Switchboard configuration
        **kwargs: Additional arguments for Router

    Returns:
        SecureRouter ready for use
    """
    base_router = Router(config=config, **kwargs)
    return SecureRouter(base_router, config=config)


def create_secure_execution_engine(
    router: Optional[SecureRouter] = None, config: Optional[SwitchboardConfig] = None, **kwargs
) -> SecureExecutionEngine:
    """Create a secure execution engine.

    Args:
        router: SecureRouter instance (created if None)
        config: Switchboard configuration
        **kwargs: Additional arguments

    Returns:
        SecureExecutionEngine ready for use
    """
    if router is None:
        router = create_secure_router(config, **kwargs)

    return SecureExecutionEngine(router, config=config)
