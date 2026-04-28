# Copyright 2026 Human Systems. MIT License.
"""Execution engine for running agents with fallback handling."""

from __future__ import annotations

import json
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from switchboard.agents import AgentResult
from switchboard.canonical_ids import AgentID
from switchboard.classifier import ClassificationResult
from switchboard.config import SwitchboardConfig
from switchboard.llm_client import LLMConfig
from switchboard.planner import ExecutionPlan, ExecutionStep
from switchboard.router import Router, RoutingMetadata
from switchboard.runtime_enforcement import RuntimeEnforcement

from switchboard.hybrid_hierarchical_router import (
    ExecutionMetrics as HierarchicalMetrics,
    HybridRoutingDecision,
    SubTask,
)

try:
    from photonic import EXECUTION_COMPLETED, ROUTING_DECISION, PhotonicBus, PhotonicEvent

    _PHOTONIC_AVAILABLE = True
except ImportError:
    _PHOTONIC_AVAILABLE = False
    ROUTING_DECISION = "routing.decision"
    EXECUTION_COMPLETED = "execution.completed"

if TYPE_CHECKING:
    from switchboard.router import RoutingDecision

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of executing a task through the routing system."""

    success: bool
    output: str
    primary_agent_id: AgentID
    fallback_used: bool = False
    error: Optional[str] = None
    metadata: Optional[dict] = None
    step_results: Optional[list[AgentResult]] = None

    @property
    def primary_agent_name(self) -> str:
        """Backward compatibility: return primary_agent_id as string."""
        return self.primary_agent_id.value


class ExecutionEngine:
    """Executes tasks through the routing system with error handling.

    The execution engine is responsible for:
    - Running the selected primary agent
    - Detecting failures and triggering fallbacks
    - Handling multi-step execution chains
    - Providing detailed execution metadata
    """

    def __init__(
        self,
        router: Router,
        config: Optional[SwitchboardConfig] = None,
        # Legacy parameters for backward compatibility
        max_retries: Optional[int] = None,
        fallback_threshold: Optional[float] = None,
        routing_memory: Optional[Any] = None,
    ):
        """Initialize the execution engine.

        Args:
            router: The router to use for agent selection
            config: Configuration object with thresholds and settings
            max_retries: (Legacy) Maximum number of retry attempts
            fallback_threshold: (Legacy) Confidence threshold for fallback
        """
        self.router = router
        self.routing_memory = routing_memory
        if config is not None:
            self.config = config
        else:
            self.config = SwitchboardConfig(
                max_retries=max_retries if max_retries is not None else 2,
                fallback_threshold=fallback_threshold if fallback_threshold is not None else 0.45,
            )
        try:
            from switchboard.agents import ECOSYSTEM_CONFIG
            self.enforcement = RuntimeEnforcement(ECOSYSTEM_CONFIG)
        except Exception:
            self.enforcement = None

    @staticmethod
    def _extract_mcts_llm_config(decision: RoutingDecision) -> Optional[LLMConfig]:
        metadata = getattr(decision.classification, "metadata", None)
        if metadata and "mcts_model_selection" in metadata:
            return LLMConfig.from_mcts_selection(metadata["mcts_model_selection"])
        return None

    def _record_mcts_feedback(self, decision: RoutingDecision, reward: float) -> None:
        """Record execution outcome back to the MCTS router for future model selection."""
        mcts_meta = getattr(decision.classification, "metadata", None)
        if not mcts_meta or "mcts_model_selection" not in mcts_meta:
            return
        model_id = mcts_meta.get("mcts_model_selection", {}).get("model_id")
        if not model_id:
            return
        mcts_cls = getattr(self.router, "mcts_classifier", None)
        if mcts_cls is None:
            return
        mcts_router = getattr(mcts_cls, "mcts_router", None)
        if mcts_router is None:
            return
        try:
            mcts_router.update_performance(model_id, reward)
        except Exception:
            pass

    @staticmethod
    def _scrub_secrets(text: str) -> str:
        """Redact common secret patterns from text before logging."""
        import re
        patterns = [
            (re.compile(r"(?i)(api[_-]?key|secret[_-]?key|auth[_-]?token|bearer)\s*[:=]\s*['\"]?([\w\-]{8,})['\"]?"), r"\1=[REDACTED]"),
            (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{4,})['\"]?"), r"\1=[REDACTED]"),
            (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY]"),
        ]
        for pattern, replacement in patterns:
            text = pattern.sub(replacement, text)
        return text

    def _log_audit_event(self, event_type: str, input_text: str, result: ExecutionResult, metadata: Optional[dict] = None) -> None:
        """Log execution event to audit log if enabled.

        Args:
            event_type: Type of event (execute, fallback, error)
            input_text: The input that was processed
            result: The execution result
            metadata: Additional metadata to log
        """
        if not self.config.enable_audit_logging:
            return

        # Truncate input if too long and scrub secrets
        max_input_log = 500
        safe_input = self._scrub_secrets(input_text)
        truncated_input = safe_input[:max_input_log] + "..." if len(safe_input) > max_input_log else safe_input

        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "input": truncated_input,
            "input_length": len(input_text),
            "success": result.success,
            "agent_id": result.primary_agent_id.value,
            "fallback_used": result.fallback_used,
            "error": result.error,
            **(metadata or {}),
        }

        try:
            with open(self.config.audit_log_path, "a") as f:
                f.write(json.dumps(audit_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def _create_safe_fallback_decision(self, input_text: str) -> RoutingDecision:
        """Create a safe fallback routing decision when routing fails.
        
        This ensures the system degrades gracefully instead of crashing
        when the routing layer encounters an error.
        
        Args:
            input_text: The original input that failed to route
            
        Returns:
            RoutingDecision routing to general agent
        """
        from switchboard.canonical_ids import TaskID
        
        fallback_classification = ClassificationResult(
            task_id=TaskID.GENERAL,
            confidence=0.0,
            alternatives=[],
            reasoning="Routing failed, falling back to general agent",
        )
        
        fallback_step = ExecutionStep(
            step_id="fallback_0",
            agent_id=AgentID.GENERAL,
            task_description=input_text,
            dependencies=[],
            confidence=0.0,
            estimated_complexity=0.5,
            input_text=input_text,
        )
        
        fallback_plan = ExecutionPlan(
            steps=[fallback_step],
            strategy="single",
            fallback_agent_id=AgentID.GENERAL,
            confidence=0.0,
        )
        
        return RoutingDecision(
            classification=fallback_classification,
            plan=fallback_plan,
            metadata=RoutingMetadata(
                confidence=0.0,
                alternatives=[],
                mcts_used=False,
                fallback_used=True,
                reasoning="Routing layer failure - safe fallback",
            ),
        )
        
    def _photonic_emit(self, event_type: str, trace_id: str, payload: dict) -> None:
        """Emit a photonic event; silently skipped if photonic is unavailable."""
        if not _PHOTONIC_AVAILABLE:
            return
        try:
            PhotonicBus.instance().emit(
                PhotonicEvent(type=event_type, source="switchboard", trace_id=trace_id, payload=payload)
            )
        except Exception as exc:
            logger.debug("photonic emit failed: %s", exc)

    def execute(self, input_text: str, force_agent: Optional[str] = None) -> ExecutionResult:
        """Execute a task through the routing system.

        Args:
            input_text: The user's input to process
            force_agent: Optional agent name to force

        Returns:
            ExecutionResult with output and execution metadata

        Raises:
            ValueError: If input exceeds max_input_length
        """
        # Validate input length
        if len(input_text) > self.config.max_input_length:
            error_result = ExecutionResult(
                success=False,
                output="",
                primary_agent_id=AgentID.GENERAL,
                error=f"Input exceeds maximum length of {self.config.max_input_length} characters",
            )
            self._log_audit_event("input_rejected", input_text, error_result, {"reason": "input_too_long"})
            return error_result

        if self.enforcement and not self.enforcement.check_rate_limit():
            error_result = ExecutionResult(
                success=False,
                output="",
                primary_agent_id=AgentID.GENERAL,
                error="Rate limit exceeded",
            )
            return error_result

        if self.enforcement:
            cached = self.enforcement.get_cached(RuntimeEnforcement.cache_key(input_text))
            if cached is not None:
                return ExecutionResult(
                    success=True,
                    output=cached,
                    primary_agent_id=AgentID.GENERAL,
                    metadata={"cached": True},
                )

        t0 = time.monotonic()
        
        try:
            decision = self.router.route(input_text, force_agent)
            mcts_llm_config = self._extract_mcts_llm_config(decision)
        except Exception as e:
            logger.error(f"Routing failed: {e}", exc_info=True)
            # Create safe fallback decision
            decision = self._create_safe_fallback_decision(input_text)
            mcts_llm_config = None

        trace_id = str(uuid.uuid4())

        # Emit routing decision so any subscriber can react immediately.
        primary_step_agent = decision.plan.steps[0].agent_id if decision.plan.steps else AgentID.GENERAL
        self._photonic_emit(
            ROUTING_DECISION,
            trace_id=trace_id,
            payload={
                "agent": primary_step_agent.value,
                "strategy": decision.plan.strategy,
                "confidence": decision.plan.confidence,
                "task_type": decision.classification.task_id.value,
                "complexity": decision.classification.estimated_complexity,
                "input_len": len(input_text),
            },
        )

        if decision.plan.strategy == "single":
            result = self._execute_single(
                input_text, decision, retry_count=0, llm_config=mcts_llm_config
            )
        else:
            result = self._execute_multi_step(input_text, decision, llm_config=mcts_llm_config)

        latency_ms = (time.monotonic() - t0) * 1000
        self._log_audit_event("execute", input_text, result, {
            "strategy": decision.plan.strategy,
            "plan_confidence": decision.plan.confidence,
        })

        # Emit execution outcome for monitoring / downstream consumers.
        self._photonic_emit(
            EXECUTION_COMPLETED,
            trace_id=trace_id,
            payload={
                "agent": result.primary_agent_id.value,
                "success": result.success,
                "fallback_used": result.fallback_used,
                "latency_ms": round(latency_ms, 2),
                "error": result.error,
            },
        )

        if self.routing_memory is not None:
            try:
                task_type = decision.classification.task_id.value
                agent_id = result.primary_agent_id.value
                self.routing_memory.record(
                    agent_id=agent_id,
                    task_type=task_type,
                    success=result.success,
                    reward=1.0 if result.success else 0.0,
                )
            except Exception as e:
                logger.warning("Failed to record routing feedback: %s", e)

        if self.enforcement and result.success and result.output:
            self.enforcement.set_cached(RuntimeEnforcement.cache_key(input_text), result.output)

        return result

    def _execute_single(
        self,
        input_text: str,
        decision: RoutingDecision,
        retry_count: int,
        llm_config: Optional[LLMConfig] = None,
    ) -> ExecutionResult:
        """Execute a single-step task with fallback support.

        Args:
            input_text: The user's input
            decision: The routing decision
            retry_count: Current retry attempt number
            llm_config: Optional LLM config from MCTS selection

        Returns:
            ExecutionResult from the agent execution
        """
        step = decision.plan.steps[0]
        primary_agent_id = step.agent_id
        primary = self.router.get_agent(primary_agent_id)
        step_input = step.input_text

        if self.enforcement and not self.enforcement.check_circuit_breaker(primary_agent_id.value):
            if retry_count < self.config.max_retries:
                return self._execute_with_fallback(
                    step_input, decision, retry_count, llm_config=llm_config
                )
            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=primary_agent_id,
                error=f"Circuit breaker open for agent {primary_agent_id.value}",
            )

        try:
            result = primary.run(step_input, llm_config=llm_config)

            if result.success:
                if self.enforcement:
                    self.enforcement.record_success(primary_agent_id.value)
                self._record_mcts_feedback(decision, reward=1.0)
                return ExecutionResult(
                    success=True,
                    output=result.output,
                    primary_agent_id=primary_agent_id,
                    fallback_used=False,
                    metadata=result.metadata,
                )

            if retry_count < self.config.max_retries:
                if self.enforcement:
                    self.enforcement.record_failure(primary_agent_id.value)
                return self._execute_with_fallback(
                    step_input, decision, retry_count, llm_config=llm_config
                )

            self._record_mcts_feedback(decision, reward=0.0)
            # All retries exhausted
            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=primary_agent_id,
                fallback_used=False,
                error=result.error or "Agent execution failed",
                metadata=result.metadata,
            )

        except Exception as e:
            # Catch all unexpected errors (not just Connection/Timeout/Runtime).
            # Try fallback if retries remain, otherwise surface the error.
            if retry_count < self.config.max_retries:
                return self._execute_with_fallback(
                    step_input, decision, retry_count, llm_config=llm_config
                )

            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=primary_agent_id,
                fallback_used=False,
                error=str(e),
            )

    def _execute_with_fallback(
        self,
        input_text: str,
        decision: RoutingDecision,
        retry_count: int,
        llm_config: Optional[LLMConfig] = None,
    ) -> ExecutionResult:
        """Execute with fallback agent.

        Args:
            input_text: The user's input
            decision: The routing decision
            retry_count: Current retry attempt number
            llm_config: Optional LLM config from MCTS selection

        Returns:
            ExecutionResult from the fallback agent
        """
        fallback_agent_id = decision.plan.fallback_agent_id
        fallback = self.router.get_agent(fallback_agent_id)

        try:
            result = fallback.run(input_text, llm_config=llm_config)

            return ExecutionResult(
                success=result.success,
                output=result.output,
                primary_agent_id=decision.plan.steps[0].agent_id,
                fallback_used=True,
                error=result.error if not result.success else None,
                metadata=result.metadata,
            )

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            # Fallback also failed - retry primary if retries left
            if retry_count < self.config.max_retries - 1:
                backoff = min(2.0 ** (retry_count + 1), 30.0)
                jitter = backoff * 0.1 * random.random()
                time.sleep(backoff + jitter)
                return self._execute_single(
                    input_text, decision, retry_count=retry_count + 1, llm_config=llm_config
                )

            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=decision.plan.steps[0].agent_id,
                fallback_used=True,
                error=f"Both primary and fallback failed: {str(e)}",
            )

    def _execute_multi_step(
        self,
        input_text: str,
        decision: RoutingDecision,
        llm_config: Optional[LLMConfig] = None,
    ) -> ExecutionResult:
        """Execute a multi-step task by running agents in sequence.

        Args:
            input_text: The user's input
            decision: The routing decision with step_sequence

        Returns:
            ExecutionResult with aggregated results from all steps
        """
        step_results: list[AgentResult] = []
        outputs: list[str] = []
        # Track per-step outcome independently of step_results, which may contain
        # both a failed primary and its fallback for the same logical step.
        step_succeeded: list[bool] = []
        # Track which agent actually executed each step (primary or fallback)
        executed_agents: list[str] = []
        fallback_used = False

        # Get the step sequence from plan
        steps = decision.plan.steps

        for i, step in enumerate(steps):
            agent = self.router.get_agent(step.agent_id)
            try:
                current_input = self._build_step_input(input_text, step, outputs)

                result = agent.run(current_input, llm_config=llm_config)
                result.metadata = {
                    **(result.metadata or {}),
                    "step": i + 1,
                    "planned_agent": step.agent_id.value,
                    "planned_confidence": step.confidence,
                }
                step_results.append(result)

                if result.success:
                    outputs.append(result.output)
                    executed_agents.append(step.agent_id.value)
                    step_succeeded.append(True)
                else:
                    if step.confidence < self.config.fallback_threshold or i == len(steps) - 1:
                        fallback_result = self._run_fallback(
                            current_input, decision, llm_config=llm_config
                        )
                        fallback_agent_id = decision.plan.fallback_agent_id
                        fallback_result.metadata = {
                            **(fallback_result.metadata or {}),
                            "fallback": True,
                            "step": i + 1,
                            "planned_agent": step.agent_id.value,
                            "fallback_agent": fallback_agent_id.value,
                        }
                        step_results.append(fallback_result)
                        if fallback_result.success:
                            fallback_used = True
                            outputs.append(fallback_result.output)
                            executed_agents.append(fallback_agent_id.value)
                            step_succeeded.append(True)
                        else:
                            outputs.append(f"Fallback also failed: {fallback_result.error}")
                            executed_agents.append(f"{fallback_agent_id.value} (failed)")
                            step_succeeded.append(False)
                    else:
                        outputs.append(f"[Step {i + 1} failed: {result.error}]")
                        executed_agents.append(f"{step.agent_id.value} (failed)")
                        step_succeeded.append(False)

            except (ConnectionError, TimeoutError, RuntimeError) as e:
                step_results.append(
                    AgentResult(
                        success=False,
                        output="",
                        error=str(e),
                        metadata={"step": i + 1, "agent": agent.name},
                    )
                )
                outputs.append(f"[Step {i + 1} error: {str(e)}]")
                executed_agents.append(f"{agent.name} (error)")
                step_succeeded.append(False)

        # Determine overall success based on per-step outcomes, not raw step_results
        # (step_results may contain both a failed primary and its successful fallback
        # for the same logical step, so iterating it would double-count failures).
        failed_steps = [i + 1 for i, ok in enumerate(step_succeeded) if not ok]
        all_success = len(failed_steps) == 0

        # Build error message if any steps failed
        error_message = None
        if failed_steps:
            failed_details = [
                f"Step {i + 1}: {r.error or 'Unknown error'}"
                for i, r in enumerate(step_results)
                if not r.success
            ]
            error_message = f"Multi-step execution failed. Failed steps: {', '.join(f'Step {s}' for s in failed_steps)}. Details: {'; '.join(failed_details)}"

        return ExecutionResult(
            success=all_success,
            output="\n\n".join(outputs) if all_success else "",
            primary_agent_id=steps[0].agent_id if steps else AgentID.GENERAL,
            fallback_used=fallback_used,
            error=error_message,
            metadata={
                "num_steps": len(steps),
                "plan_confidence": decision.plan.confidence,
                "planned_agents": [s.agent_id.value for s in steps],
                "executed_agents": executed_agents,
                "step_confidences": [s.confidence for s in steps],
                "step_summary": [
                    f"Step {i + 1}: {'✓' if ok else '✗'}" for i, ok in enumerate(step_succeeded)
                ],
                "failed_steps": failed_steps if failed_steps else None,
            },
            step_results=step_results,
        )

    def _run_fallback(
        self, input_text: str, decision: RoutingDecision, llm_config: Optional[LLMConfig] = None
    ) -> AgentResult:
        fallback_agent_id = decision.plan.fallback_agent_id
        fallback = self.router.get_agent(fallback_agent_id)
        if fallback:
            try:
                return fallback.run(input_text, llm_config=llm_config)
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                return AgentResult(
                    success=False,
                    output="",
                    error=str(e),
                )
        return AgentResult(
            success=False,
            output="",
            error="No fallback agent configured",
        )

    def _build_step_input(
        self, original_input: str, step: ExecutionStep, previous_outputs: list[str]
    ) -> str:
        """Build the input for a plan step with prior outputs as context."""
        if not previous_outputs:
            return step.input_text

        context = "\n\n".join(
            f"Step {index + 1} output:\n{output}" for index, output in enumerate(previous_outputs)
        )
        return (
            f"Original request:\n{original_input}\n\n"
            f"Previous step outputs:\n{context}\n\n"
            f"Current step:\n{step.input_text}"
        )


class HierarchicalExecutor:
    """Executes HybridRoutingDecision objects produced by the hybrid hierarchical router.

    Handles subtask dependency ordering, per-subtask agent execution, metric
    collection, Photonic event emission, and feedback recording.
    """

    def __init__(self, router: Router, hierarchical_router: Optional[Any] = None):
        self.router = router
        self.hierarchical_router = hierarchical_router
        try:
            from switchboard.agents import ECOSYSTEM_CONFIG
            self.enforcement = RuntimeEnforcement(ECOSYSTEM_CONFIG)
        except Exception:
            self.enforcement = None

    def execute(self, decision: HybridRoutingDecision, input_text: str) -> ExecutionResult:
        trace_id = str(uuid.uuid4())
        t0 = time.monotonic()

        if self.enforcement and not self.enforcement.check_circuit_breaker(decision.primary_agent.value):
            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=decision.primary_agent,
                error=f"Circuit breaker open for agent {decision.primary_agent.value}",
            )

        self._photonic_emit(
            ROUTING_DECISION,
            trace_id=trace_id,
            payload={
                "agent": decision.primary_agent.value,
                "strategy": decision.strategy,
                "confidence": decision.confidence,
                "task_type": decision.metadata.get("classification", "general"),
                "complexity": decision.metadata.get("complexity_score", 0.0),
                "input_len": len(input_text),
            },
        )

        if not decision.subtasks:
            result = self._execute_single_subtask(
                decision.primary_agent, input_text, trace_id
            )
        else:
            result = self._execute_subtasks(decision, input_text, trace_id)

        latency_ms = (time.monotonic() - t0) * 1000

        self._photonic_emit(
            EXECUTION_COMPLETED,
            trace_id=trace_id,
            payload={
                "agent": decision.primary_agent.value,
                "success": result.success,
                "fallback_used": result.fallback_used,
                "latency_ms": round(latency_ms, 2),
                "error": result.error,
            },
        )

        if self.hierarchical_router is not None:
            try:
                metrics = HierarchicalMetrics(
                    actual_latency_ms=int(latency_ms),
                    success=result.success,
                    quality_score=1.0 if result.success else 0.0,
                )
                self.hierarchical_router.record_feedback(decision, metrics)
            except Exception as e:
                logger.warning("Failed to record hierarchical feedback: %s", e)

        return result

    def _execute_single_subtask(
        self, agent_id: AgentID, input_text: str, trace_id: str
    ) -> ExecutionResult:
        agent = self.router.get_agent(agent_id)
        try:
            agent_result = agent.run(input_text)
            return ExecutionResult(
                success=agent_result.success,
                output=agent_result.output,
                primary_agent_id=agent_id,
                error=agent_result.error if not agent_result.success else None,
                metadata=agent_result.metadata,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                primary_agent_id=agent_id,
                error=str(e),
            )

    def _execute_subtasks(
        self, decision: HybridRoutingDecision, input_text: str, trace_id: str
    ) -> ExecutionResult:
        completed_ids: set[str] = set()
        outputs: dict[str, str] = {}
        step_results: list[AgentResult] = []
        fallback_used = False
        failed_subtasks: list[str] = []

        sorted_subtasks = self._topological_sort(decision.subtasks)

        for subtask in sorted_subtasks:
            unresolved = [d for d in subtask.dependencies if d not in completed_ids]
            if unresolved:
                failed_subtasks.append(subtask.id)
                continue

            context = self._build_context(input_text, subtask, outputs)
            agent_id = subtask.assigned_agent or decision.primary_agent
            agent = self.router.get_agent(agent_id)

            try:
                agent_result = agent.run(context)
                step_results.append(agent_result)
                if agent_result.success:
                    outputs[subtask.id] = agent_result.output
                    completed_ids.add(subtask.id)
                    subtask.status = "completed"
                    subtask.result = agent_result.output
                else:
                    fallback_agent = self.router.get_agent(AgentID.GENERAL)
                    try:
                        fb_result = fallback_agent.run(context)
                        if fb_result.success:
                            outputs[subtask.id] = fb_result.output
                            completed_ids.add(subtask.id)
                            subtask.status = "completed"
                            subtask.result = fb_result.output
                            fallback_used = True
                        else:
                            failed_subtasks.append(subtask.id)
                            subtask.status = "failed"
                    except Exception:
                        failed_subtasks.append(subtask.id)
                        subtask.status = "failed"
            except Exception as e:
                step_results.append(
                    AgentResult(success=False, output="", error=str(e))
                )
                failed_subtasks.append(subtask.id)
                subtask.status = "failed"

        all_success = len(failed_subtasks) == 0
        combined_output = "\n\n".join(
            outputs[st.id] for st in sorted_subtasks if st.id in outputs
        )

        error_msg = None
        if failed_subtasks:
            error_msg = f"Subtasks failed: {', '.join(failed_subtasks)}"

        return ExecutionResult(
            success=all_success,
            output=combined_output if all_success else "",
            primary_agent_id=decision.primary_agent,
            fallback_used=fallback_used,
            error=error_msg,
            metadata={
                "num_subtasks": len(sorted_subtasks),
                "failed_subtasks": failed_subtasks or None,
            },
            step_results=step_results if step_results else None,
        )

    def _topological_sort(self, subtasks: list[SubTask]) -> list[SubTask]:
        by_id = {st.id: st for st in subtasks}
        visited: set[str] = set()
        visiting: set[str] = set()
        order: list[SubTask] = []
        cycle: list[str] = []

        def visit(sid: str) -> bool:
            if sid in visited:
                return False
            if sid in visiting:
                cycle.append(sid)
                return True
            visiting.add(sid)
            st = by_id[sid]
            for dep in st.dependencies:
                if visit(dep):
                    return True
            visiting.remove(sid)
            visited.add(sid)
            order.append(st)
            return False

        for st in subtasks:
            if visit(st.id):
                logger.error("Cycle detected in subtask dependencies: %s", cycle)
                return []

        return order

    def _build_context(
        self, original_input: str, subtask: SubTask, outputs: dict[str, str]
    ) -> str:
        dep_outputs = [
            f"Dependency {d} output:\n{outputs[d]}"
            for d in subtask.dependencies
            if d in outputs
        ]
        if not dep_outputs:
            return subtask.description
        return (
            f"Original request:\n{original_input}\n\n"
            + "\n\n".join(dep_outputs)
            + f"\n\nCurrent subtask:\n{subtask.description}"
        )

    def _photonic_emit(self, event_type: str, trace_id: str, payload: dict) -> None:
        if not _PHOTONIC_AVAILABLE:
            return
        try:
            PhotonicBus.instance().emit(
                PhotonicEvent(type=event_type, source="hierarchical_executor", trace_id=trace_id, payload=payload)
            )
        except Exception as exc:
            logger.debug("photonic emit failed: %s", exc)
