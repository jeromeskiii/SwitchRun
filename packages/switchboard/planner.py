# Copyright 2026 Human Systems. MIT License.
"""Planner module for building execution plans from classified tasks."""

from dataclasses import dataclass
import re

from switchboard.canonical_ids import AgentID, TaskID, resolve_task_to_agent
from switchboard.classifier import ClassificationResult, Classifier


@dataclass
class ExecutionStep:
    """A single step in an execution plan."""

    task_id: TaskID  # The classified task type
    agent_id: AgentID  # The resolved agent to run
    input_text: str
    confidence: float = 0.0
    alternatives: list[TaskID] | None = None
    reason: str = ""

    @property
    def task(self) -> str:
        """Backward compatibility: return task_id as string."""
        return self.task_id.value

    @property
    def agent_name(self) -> str:
        """Backward compatibility: return agent_id as string."""
        return self.agent_id.value


@dataclass
class ExecutionPlan:
    """Structured representation of how a task will run."""

    strategy: str  # "single" or "sequential"
    steps: list[ExecutionStep]
    fallback_agent_id: AgentID = AgentID.GENERAL
    confidence: float = 0.0

    @property
    def fallback_agent_name(self) -> str:
        """Backward compatibility: return fallback_agent_id as string."""
        return self.fallback_agent_id.value


class Planner:
    """Detects multi-step inputs and builds execution plans.

    The Planner is responsible for:
    - Identifying if an input requires sequential execution
    - Mapping tasks to appropriate agents via resolve_task_to_agent
    - Building the ordered sequence of execution steps
    - Deduplicating consecutive steps with the same agent
    - Normalizing split sub-tasks
    """

    def __init__(self, classifier: Classifier, dedupe_steps: bool = True):
        self.classifier = classifier
        self.dedupe_steps = dedupe_steps
        self.default_task = TaskID.GENERAL

    def plan(
        self,
        input_text: str,
        classification: ClassificationResult,
        forced_agent_id: AgentID | None = None,
    ) -> ExecutionPlan:
        """Builds an execution plan based on input text and classification.

        Args:
            input_text: The user's input
            classification: The classification result
            forced_agent_id: Optional agent ID to force (overrides task resolution)
        """
        is_multi = classification.requires_multi_step or self._detect_multi_step(
            input_text
        )

        # Determine agent_id: use forced_agent_id if provided, otherwise resolve from task
        agent_id = (
            forced_agent_id
            if forced_agent_id
            else resolve_task_to_agent(classification.task_id)
        )

        if is_multi:
            # Multi-step: parse input on delimiters to extract sub-tasks
            steps = []
            sub_tasks = self._split_multi_step(input_text)

            for sub_task_text in sub_tasks:
                # Normalize the sub-task text
                normalized_text = self._normalize_sub_task(sub_task_text)
                if not normalized_text:
                    continue

                sub_classification = self.classifier.classify(normalized_text)
                steps.append(
                    ExecutionStep(
                        task_id=sub_classification.task_id,
                        agent_id=(
                            forced_agent_id
                            if forced_agent_id
                            else resolve_task_to_agent(sub_classification.task_id)
                        ),
                        input_text=normalized_text,
                        confidence=sub_classification.confidence,
                        alternatives=sub_classification.alternatives,
                        reason=sub_classification.reason,
                    )
                )

            # Deduplicate consecutive steps with the same agent
            if self.dedupe_steps and len(steps) > 1:
                steps = self._dedupe_steps(steps)

            # Guard: multi-step split must produce at least one step
            if not steps:
                steps = [
                    ExecutionStep(
                        task_id=TaskID.GENERAL,
                        agent_id=AgentID.GENERAL,
                        input_text=input_text,
                        confidence=classification.confidence,
                        alternatives=[],
                        reason="Multi-step split produced no valid steps",
                    )
                ]

            plan_confidence = (
                round(sum(step.confidence for step in steps) / len(steps), 3)
                if steps
                else classification.confidence
            )

            return ExecutionPlan(
                strategy="sequential" if len(steps) > 1 else "single",
                steps=steps,
                confidence=plan_confidence,
                fallback_agent_id=AgentID.GENERAL,
            )

        # Single-step path
        return ExecutionPlan(
            strategy="single",
            steps=[
                ExecutionStep(
                    task_id=classification.task_id,
                    agent_id=agent_id,
                    input_text=input_text,
                    confidence=classification.confidence,
                    alternatives=classification.alternatives,
                    reason=classification.reason,
                )
            ],
            confidence=classification.confidence,
        )

    def _detect_multi_step(self, input_text: str) -> bool:
        """Detect if the input contains multi-step indicators."""
        text = input_text.lower()
        multi_step_indicators = [
            "and then",
            "after that",
            "first",
            "then",
            "next",
            "finally",
            "followed by",
            "subsequently",
            "once done",
            "and afterwards",
        ]
        return any(indicator in text for indicator in multi_step_indicators)

    def _split_multi_step(self, input_text: str) -> list[str]:
        """Split input text on multi-step delimiters.

        Handles patterns like:
        - "first X then Y"
        - "X and then Y"
        - "X after that Y"
        - "X then Y then Z"
        - "first X, then Y, finally Z"
        """
        # Order matters: more specific patterns first
        split_patterns = [
            (r"^\s*first\s+", ""),  # Leading "first"
            (r"\s*,\s*finally\s+", ", "),  # ", finally" -> just separator
            (r"\s*,\s*then\s+", ", "),  # ", then" -> just separator
            (r"\s+and\s+then\s+", " "),  # "and then" -> separator
            (r"\s+after\s+that\s+", " "),  # "after that" -> separator
            (r"\s+followed\s+by\s+", " "),  # "followed by" -> separator
            (r"\s+subsequently\s+", " "),  # "subsequently" -> separator
            (r"\s+once\s+done[,\s]+", " "),  # "once done" -> separator
            (r"\s+and\s+afterwards\s+", " "),  # "and afterwards" -> separator
            (r"\s+finally\s+", " "),  # "finally" -> separator
            (r"\s+then\s+", " "),  # "then" -> separator (most common, last)
        ]

        parts = [input_text]
        for pattern, _ in split_patterns:
            new_parts = []
            for part in parts:
                split_result = re.split(pattern, part, flags=re.IGNORECASE)
                new_parts.extend(split_result)
            parts = new_parts

        # Clean up and filter empty parts
        cleaned = []
        for p in parts:
            p = p.strip(" ,;")
            if p and len(p) > 2:  # Minimum meaningful length
                cleaned.append(p)

        return cleaned

    def _normalize_sub_task(self, sub_task_text: str) -> str:
        """Normalize a sub-task string.

        - Strips leading/trailing whitespace
        - Removes leading ordinals (1st, 2nd, etc.)
        - Removes leading "first", "second", etc.
        - Consolidates multiple spaces
        """
        text = sub_task_text.strip(" ,;")

        # Remove leading ordinals
        text = re.sub(r"^\d+(?:st|nd|rd|th)[,\s]+", "", text, flags=re.IGNORECASE)

        # Remove leading order words
        text = re.sub(
            r"^(?:first|second|third|fourth|fifth|next|last)[,\s]+",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # Consolidate whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def _dedupe_steps(self, steps: list[ExecutionStep]) -> list[ExecutionStep]:
        """Deduplicate consecutive steps with the same agent_id.

        Merges consecutive steps that would run the same agent into a single step,
        combining their input text and averaging confidence.

        Args:
            steps: List of execution steps

        Returns:
            Deduplicated list of steps
        """
        if not steps:
            return steps

        deduped = []
        i = 0
        while i < len(steps):
            current = steps[i]

            # Look ahead for consecutive steps with same agent
            merge_indices = [i]
            j = i + 1
            while j < len(steps) and steps[j].agent_id == current.agent_id:
                merge_indices.append(j)
                j += 1

            if len(merge_indices) > 1:
                # Merge consecutive steps
                merged_input = " ".join(steps[k].input_text for k in merge_indices)
                merged_confidence = sum(
                    steps[k].confidence for k in merge_indices
                ) / len(merge_indices)

                deduped.append(
                    ExecutionStep(
                        task_id=current.task_id,
                        agent_id=current.agent_id,
                        input_text=merged_input,
                        confidence=round(merged_confidence, 3),
                        alternatives=current.alternatives,
                        reason=f"Merged {len(merge_indices)} consecutive steps",
                    )
                )
            else:
                deduped.append(current)

            i = j

        return deduped
