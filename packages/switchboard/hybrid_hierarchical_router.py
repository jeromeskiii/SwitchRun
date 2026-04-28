# Copyright 2026 Human Systems. MIT License.
"""Hybrid Hierarchical-MCTS Router

Implements a multi-layer routing architecture based on research from:
- HALO (2025): Hierarchical task decomposition + MCTS workflow search
- MASTER (2025): LLM-specialized MCTS for agent recruitment
- CASTER (2026): Context-aware cost-efficient routing
- TCAR (2026): Multi-label classification with collaborative execution

Architecture:
    Layer 1: Intent Classifier (fast path for simple tasks)
    Layer 2: Task Decomposer (HALO-style hierarchical decomposition)
    Layer 3: MCTS Workflow Search (MASTER-style agent coordination)
    Layer 4: Execution with feedback loop
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from switchboard.canonical_ids import AgentID, TaskID, resolve_task_to_agent
from switchboard.classifier import Classifier, ClassificationResult
from switchboard.routing_memory import RoutingMemory

logger = logging.getLogger(__name__)


@dataclass
class ComplexityScore:
    """Task complexity assessment for routing decisions."""

    score: float  # 0.0 to 1.0
    estimated_tokens: int
    estimated_steps: int
    reasoning: str

    @property
    def is_simple(self) -> bool:
        """Fast path: simple tasks skip expensive MCTS."""
        return self.score <= 0.3 and self.estimated_steps <= 2

    @property
    def is_complex(self) -> bool:
        """Complex tasks get full hierarchical+MCTS treatment."""
        return self.score > 0.6 or self.estimated_steps > 5


@dataclass
class SubTask:
    """A decomposed subtask from hierarchical planning."""

    id: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    estimated_complexity: float = 0.5
    required_capabilities: list[str] = field(default_factory=list)
    decomposition_strategy: str = "simple"  # How this subtask was created

    # Runtime fields
    assigned_agent: Optional[AgentID] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[str] = None


@dataclass
class MCTSNode:
    """Node in the MCTS search tree for workflow optimization."""

    state: dict[str, Any]  # Current partial solution state
    parent: Optional[MCTSNode] = None
    children: list[MCTSNode] = field(default_factory=list)

    # MCTS statistics
    visits: int = 0
    total_reward: float = 0.0

    # Action that led to this node
    action: Optional[dict] = None  # {agent: AgentID, message: str}

    def is_fully_expanded(self, available_actions: list[dict]) -> bool:
        return len(self.children) >= len(available_actions)

    def best_child(self, exploration_constant: float = 1.414) -> MCTSNode:
        """Select child with highest UCT score."""
        log_parent = math.log(self.visits) if self.visits > 0 else 0.0

        best_score = -1.0
        best = self.children[0]
        for child in self.children:
            if child.visits == 0:
                return child  # Unvisited child always selected first
            exploitation = child.total_reward / child.visits
            exploration = exploration_constant * math.sqrt(log_parent / child.visits)
            score = exploitation + exploration
            if score > best_score:
                best_score = score
                best = child
        return best

    def update(self, reward: float) -> None:
        self.visits += 1
        self.total_reward += reward


@dataclass
class HybridRoutingDecision:
    """Final routing decision with full context."""

    primary_agent: AgentID
    strategy: str  # "fast", "single", "hierarchical", "mcts"
    subtasks: list[SubTask] = field(default_factory=list)
    workflow_tree: Optional[MCTSNode] = None
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionMetrics:
    """Metrics from actual execution for learning."""

    actual_tokens: int = 0
    actual_latency_ms: int = 0
    actual_cost: float = 0.0
    success: bool = True
    quality_score: float = 0.0  # LLM-as-judge or heuristic

    def compute_reward(self) -> float:
        """Compute reward for MCTS update."""
        # Reward = quality - normalized cost
        cost_penalty = self.actual_cost * 0.01
        latency_penalty = self.actual_latency_ms * 0.0001
        return (self.quality_score * 10) - cost_penalty - latency_penalty


class ComplexityClassifier:
    """Layer 1: Fast complexity assessment for routing decisions."""

    # Complexity indicators
    COMPLEXITY_PATTERNS = {
        "high": [
            r"\band\s+then\s+",  # Multi-step
            r"\bfirst.*then.*finally\b",  # Sequential
            r"\banalyze.*implement.*test\b",  # Full workflow
            r"\bcompare\s+and\s+contrast\b",  # Analysis
            r"\bresearch.*synthesize.*present\b",  # Complex pipeline
            r",\s*(implement|design|build|create|test|benchmark)\b",  # Comma-separated action list
            r"\b(design|architect|build)\b.*\b(system|service|pipeline|framework)\b",  # System design
            r"\b(research|investigate|analyze)\b.*\b(implement|build|deploy)\b",  # Research-to-build
            r"\b\w+,\s*\w+,\s*(and\s+)?\w+\b.*\b(implement|build|create)\b",  # Multiple items + action
            r"\bmulti[- ]?(step|phase|stage)\b",  # Explicitly multi-phase
        ],
        "medium": [
            r"\bwith\s+",  # Has context
            r"\busing\s+",  # Has tool requirement
            r"\bbased\s+on\b",  # Requires reference
        ],
        "low": [
            r"^\s*\w+\s+this\s+",  # Simple action
            r"^\s*fix\s+",  # Direct fix
            r"^\s*explain\s+",  # Simple explanation
        ],
    }

    def __init__(self):
        """Pre-compile regex patterns for performance."""
        import re
        
        self._compiled_patterns = {
            "high": [re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_PATTERNS["high"]],
            "medium": [re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_PATTERNS["medium"]],
            "low": [re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_PATTERNS["low"]],
        }

    def classify(self, task_description: str) -> ComplexityScore:
        """Assess task complexity for routing decision."""
        task_lower = task_description.lower()
        complexity_score = 0.35  # Default: slightly above simple threshold
        reasoning_parts = []

        # Check complexity patterns using pre-compiled regexes
        high_matches = sum(1 for p in self._compiled_patterns["high"] if p.search(task_lower))
        medium_matches = sum(
            1 for p in self._compiled_patterns["medium"] if p.search(task_lower)
        )
        low_matches = sum(1 for p in self._compiled_patterns["low"] if p.search(task_lower))

        # Adjust score
        complexity_score += high_matches * 0.15
        complexity_score += medium_matches * 0.05
        complexity_score -= low_matches * 0.1
        complexity_score = max(0.0, min(1.0, complexity_score))

        if high_matches > 0:
            reasoning_parts.append(f"Found {high_matches} complexity indicators")
        if medium_matches > 0:
            reasoning_parts.append(f"Found {medium_matches} medium complexity indicators")
        if low_matches > 0:
            reasoning_parts.append(f"Found {low_matches} simplicity indicators")

        # Estimate tokens and steps
        word_count = len(task_description.split())
        estimated_tokens = word_count * 2 + 500  # Rough estimate
        estimated_steps = max(1, int(complexity_score * 8))

        return ComplexityScore(
            score=complexity_score,
            estimated_tokens=estimated_tokens,
            estimated_steps=estimated_steps,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "Default assessment",
        )


class TaskDecomposer:
    """Layer 2: Rule-based hierarchical task decomposition (LLM fallback is a future enhancement)."""

    def __init__(self, llm_client: Optional[Any] = None):
        import re
        
        self.llm_client = llm_client
        self.decomposition_patterns = {
            "code_review": ["analyze code", "identify issues", "suggest fixes", "verify changes"],
            "feature_implementation": [
                "design approach",
                "implement core logic",
                "add tests",
                "documentation",
            ],
            "debugging": ["reproduce issue", "isolate cause", "implement fix", "verify resolution"],
            "data_analysis": [
                "load data",
                "explore structure",
                "analyze patterns",
                "visualize results",
            ],
        }
        
        # Pre-compile regex patterns for task decomposition
        self._split_patterns = {
            "comma_and": re.compile(r"\s*,\s*(?:and\s+)?", re.IGNORECASE),
            "and_then": re.compile(r"\s+(?:and then|then|and finally|finally)\s+", re.IGNORECASE),
        }

    def decompose(self, task_description: str, complexity: ComplexityScore) -> list[SubTask]:
        """Decompose complex task into subtasks with explicit strategy tracking.
        
        Strategies (in order of preference):
        1. "trivial" - No decomposition needed (simple tasks)
        2. "pattern" - Known pattern matching (code_review, feature_impl, etc.)
        3. "llm" - LLM-based decomposition (if available and complexity > 0.5)
        4. "rule_based" - Regex-based splitting fallback
        """

        # Strategy 1: Trivial decomposition for simple tasks
        if complexity.is_simple:
            return [
                SubTask(
                    id="t0",
                    description=task_description,
                    estimated_complexity=complexity.score,
                    decomposition_strategy="trivial",
                )
            ]

        # Strategy 2: Try pattern matching for known task types
        task_lower = task_description.lower()
        for pattern, steps in self.decomposition_patterns.items():
            if pattern.replace("_", " ") in task_lower or any(s in task_lower for s in steps[:2]):
                logger.debug(f"Using pattern-based decomposition: {pattern}")
                subtasks = self._create_from_pattern(task_description, steps)
                # Mark all with pattern strategy
                for st in subtasks:
                    st.decomposition_strategy = "pattern"
                return subtasks

        # Strategy 3: LLM-based decomposition if available and complex enough
        if self.llm_client and complexity.score > 0.5:
            logger.debug("Using LLM-based decomposition")
            subtasks = self._llm_decompose(task_description)
            for st in subtasks:
                st.decomposition_strategy = "llm"
            return subtasks

        # Strategy 4: Rule-based (regex) decomposition fallback
        logger.debug("Using rule-based decomposition (fallback)")
        subtasks = self._simple_decomposition(task_description, complexity)
        for st in subtasks:
            st.decomposition_strategy = "rule_based"
        return subtasks

    def _create_from_pattern(self, task_description: str, steps: list[str]) -> list[SubTask]:
        """Create subtasks from known pattern."""
        subtasks = []
        for i, step in enumerate(steps):
            subtasks.append(
                SubTask(
                    id=f"t{i}",
                    description=step,
                    dependencies=[f"t{i - 1}"] if i > 0 else [],
                    estimated_complexity=0.4,
                )
            )
        return subtasks

    def _simple_decomposition(
        self, task_description: str, complexity: ComplexityScore
    ) -> list[SubTask]:
        """Simple rule-based decomposition using pre-compiled patterns."""
        # Try multiple splitting patterns
        # Pattern 1: "step1, step2, and step3" (using pre-compiled pattern)
        parts = self._split_patterns["comma_and"].split(task_description)

        # Pattern 2: "step1 and then step2" (using pre-compiled pattern)
        if len(parts) == 1:
            parts = self._split_patterns["and_then"].split(task_description)

        # Pattern 3: "step1; step2; step3" (simple split, no regex needed)
        if len(parts) == 1:
            parts = task_description.split(";")

        # Filter out empty parts and very short fragments
        parts = [p.strip() for p in parts if len(p.strip()) > 5]

        if len(parts) <= 1:
            # No decomposition needed/possible
            return [
                SubTask(
                    id="t0", description=task_description, estimated_complexity=complexity.score
                )
            ]

        subtasks = []
        for i, part in enumerate(parts):
            subtasks.append(
                SubTask(
                    id=f"t{i}",
                    description=part.strip(),
                    dependencies=[f"t{i - 1}"] if i > 0 else [],
                    estimated_complexity=complexity.score / len(parts),
                )
            )

        return subtasks

    def _llm_decompose(self, task_description: str) -> list[SubTask]:
        """Placeholder for LLM-based decomposition (not yet implemented)."""
        logger.info("LLM decomposition not yet implemented; falling back to rule-based splitting")
        return self._simple_decomposition(
            task_description, ComplexityScore(0.7, 1000, 3, "LLM fallback")
        )


class MCTSWorkflowSearcher:
    """Layer 3: MCTS workflow optimization with heuristic simulation and optional routing-memory bias."""

    def __init__(
        self,
        simulations: int = 20,  # Reduced from typical 100 for latency
        exploration_constant: float = 1.414,
        max_depth: int = 10,
        routing_memory: Optional[Any] = None,
    ):
        self.simulations = simulations
        self.exploration_constant = exploration_constant
        self.max_depth = max_depth
        self.routing_memory = routing_memory

    def search(
        self, subtask: SubTask, available_agents: list[AgentID], context: dict[str, Any]
    ) -> tuple[list[dict], MCTSNode]:
        """Search for optimal agent workflow using MCTS."""

        # Create root node
        root = MCTSNode(state={"subtask": subtask.id, "completed": False})

        # Generate available actions (agent selections)
        actions = self._generate_actions(subtask, available_agents)

        # Run MCTS simulations
        for sim in range(self.simulations):
            # Selection: traverse tree to leaf
            node = self._select(root, actions)

            # Expansion: add child if not terminal
            if not self._is_terminal(node) and not node.is_fully_expanded(actions):
                node = self._expand(node, actions)

            # Simulation: rollout to estimate reward
            reward = self._simulate(node, subtask, actions)

            # Backpropagation: update statistics
            self._backpropagate(node, reward)

        # Extract best path
        best_path = self._extract_best_path(root)
        return best_path, root

    def _generate_actions(self, subtask: SubTask, agents: list[AgentID]) -> list[dict]:
        """Generate possible actions (agent assignments).

        Collaboration variants are only included for explicitly complex subtasks
        to keep the action space tractable for the default simulation budget.
        With N=13 agents: simple → 13 actions, complex → 13 + 13×12 = 169.
        """
        actions = []
        for agent in agents:
            actions.append({"agent": agent, "action": "execute", "message": subtask.description})
        # Only add collaboration pairs when the subtask is genuinely complex
        if subtask.estimated_complexity > 0.6:
            for agent in agents:
                for other_agent in agents:
                    if other_agent != agent:
                        actions.append(
                            {
                                "agent": agent,
                                "collaborator": other_agent,
                                "action": "collaborate",
                                "message": subtask.description,
                            }
                        )
        return actions

    def _select(self, root: MCTSNode, actions: list[dict]) -> MCTSNode:
        """Select node using UCT until leaf reached."""
        node = root
        depth = 0

        while node.children and depth < self.max_depth:
            if not node.is_fully_expanded(actions):
                return node
            node = node.best_child(self.exploration_constant)
            depth += 1

        return node

    def _expand(self, node: MCTSNode, actions: list[dict]) -> MCTSNode:
        """Expand node with a new child."""
        tried_actions = [child.action for child in node.children]
        untried = [a for a in actions if a not in tried_actions]

        if not untried:
            return node

        action = random.choice(untried)
        child = MCTSNode(
            state={**node.state, "step": node.state.get("step", 0) + 1}, parent=node, action=action
        )
        node.children.append(child)
        return child

    def _is_terminal(self, node: MCTSNode) -> bool:
        """Check if node represents terminal state."""
        return node.state.get("completed", False) or node.state.get("step", 0) >= self.max_depth

    def _simulate(self, node: MCTSNode, subtask: SubTask, actions: list[dict]) -> float:
        """Heuristic simulation with routing-memory bias (LLM rollouts are a future enhancement)."""
        # Simplified simulation - in practice would use LLM or heuristic model
        if not node.action:
            return 0.5

        agent = node.action.get("agent", AgentID.GENERAL)

        # Base reward on agent-task fit
        base_reward = self._estimate_agent_fit(agent, subtask)

        # Add noise for exploration
        noise = random.gauss(0, 0.1)

        # Cost penalty (CASTER-style)
        cost_penalty = self._estimate_cost(node.action) * 0.01

        return max(0.0, min(1.0, base_reward + noise - cost_penalty))

    def _estimate_agent_fit(self, agent: AgentID, subtask: SubTask) -> float:
        """Estimate how well agent fits subtask, with historical bias."""
        # Simple heuristic matching
        agent_str = agent.value.lower()
        task_str = subtask.description.lower()

        score = 0.5
        if any(cap.lower() in task_str for cap in subtask.required_capabilities):
            score += 0.3
        if agent_str in task_str:
            score += 0.2

        # Historical performance bias from routing memory
        if self.routing_memory is not None:
            # Derive task_type from required_capabilities or use "general"
            task_type = subtask.required_capabilities[0] if subtask.required_capabilities else "general"
            score += self.routing_memory.agent_bias(agent.value, task_type)

        return max(0.0, min(1.0, score))

    def _estimate_cost(self, action: dict) -> float:
        """Estimate execution cost."""
        base_cost = 0.1
        if "collaborator" in action:
            base_cost += 0.15  # Collaboration costs more
        return base_cost

    def _backpropagate(self, node: MCTSNode, reward: float) -> None:
        """Backpropagate reward up the tree."""
        current: Optional[MCTSNode] = node
        while current:
            current.update(reward)
            current = current.parent

    def _extract_best_path(self, root: MCTSNode) -> list[dict]:
        """Extract best action path from root."""
        path = []
        node = root

        while node.children:
            best = max(node.children, key=lambda c: c.visits)
            if best.action:
                path.append(best.action)
            node = best

        return path


class HybridHierarchicalRouter:
    """Main router combining all layers."""

    def __init__(
        self,
        classifier: Optional[Classifier] = None,
        llm_client: Optional[Any] = None,
        use_mcts: bool = True,
        mcts_simulations: int = 20,
        routing_memory: Optional[Any] = None,
    ):
        self.classifier = classifier or Classifier()
        self.complexity_classifier = ComplexityClassifier()
        self.task_decomposer = TaskDecomposer(llm_client)
        self.routing_memory = routing_memory if routing_memory is not None else RoutingMemory()
        self.mcts_searcher = (
            MCTSWorkflowSearcher(
                simulations=mcts_simulations,
                routing_memory=self.routing_memory,
            ) if use_mcts else None
        )

        # Learning state (CASTER-style)
        self.routing_history: list[tuple[HybridRoutingDecision, ExecutionMetrics]] = []
        self.agent_performance: dict[AgentID, list[float]] = {}

    def route(
        self,
        task_description: str,
        available_agents: Optional[list[AgentID]] = None,
        force_complexity: Optional[str] = None,  # "simple", "complex", None=auto
    ) -> RoutingDecision:
        """Route task through hierarchical decision process."""

        start_time = time.time()
        available_agents = available_agents or list(AgentID)

        # Layer 1: Intent classification
        classification = self.classifier.classify(task_description)
        primary_agent = resolve_task_to_agent(classification.task_id)

        # Layer 1b: Complexity assessment
        complexity = self.complexity_classifier.classify(task_description)
        if force_complexity == "simple":
            complexity.score = 0.2
            complexity.estimated_steps = 1  # ensure is_simple fast-path triggers
        elif force_complexity == "complex":
            complexity.score = 0.8
            complexity.estimated_steps = max(complexity.estimated_steps, 6)  # ensure is_complex triggers

        logger.info(f"Task complexity: {complexity.score:.2f} - {complexity.reasoning}")

        # Fast path: simple tasks
        if complexity.is_simple:
            return HybridRoutingDecision(
                primary_agent=primary_agent,
                strategy="fast",
                estimated_cost=complexity.estimated_tokens * 0.0001,
                estimated_latency_ms=complexity.estimated_steps * 500,
                confidence=classification.confidence,
                metadata={
                    "classification": classification.task_id.value,
                    "complexity_score": complexity.score,
                    "rationale": "Fast path for simple task",
                },
            )

        # Layer 2: Task decomposition
        subtasks = self.task_decomposer.decompose(task_description, complexity)

        # Single subtask = single agent
        if len(subtasks) == 1:
            return HybridRoutingDecision(
                primary_agent=primary_agent,
                strategy="single",
                subtasks=subtasks,
                estimated_cost=complexity.estimated_tokens * 0.0001,
                estimated_latency_ms=complexity.estimated_steps * 1000,
                confidence=classification.confidence,
                metadata={
                    "classification": classification.task_id.value,
                    "complexity_score": complexity.score,
                },
            )

        # Layer 3: MCTS workflow search (for complex multi-step tasks)
        workflow_tree = None
        if self.mcts_searcher and complexity.is_complex:
            logger.info(f"Running MCTS search for {len(subtasks)} subtasks")

            for subtask in subtasks:
                path, tree = self.mcts_searcher.search(subtask, available_agents, {})
                subtask.assigned_agent = path[0].get("agent") if path else primary_agent
                if workflow_tree is None:
                    workflow_tree = tree
        else:
            # Hierarchical without MCTS
            for subtask in subtasks:
                subtask.assigned_agent = primary_agent

        latency_ms = int((time.time() - start_time) * 1000)

        mcts_used = complexity.is_complex and self.mcts_searcher is not None
        return HybridRoutingDecision(
            primary_agent=primary_agent,
            strategy="mcts" if mcts_used else "hierarchical",
            subtasks=subtasks,
            workflow_tree=workflow_tree,
            estimated_cost=sum(s.estimated_complexity * 1000 for s in subtasks) * 0.0001,
            estimated_latency_ms=latency_ms + complexity.estimated_steps * 1500,
            confidence=classification.confidence,
            metadata={
                "classification": classification.task_id.value,
                "complexity_score": complexity.score,
                "num_subtasks": len(subtasks),
                "mcts_used": mcts_used,
            },
        )

    def record_feedback(self, decision: HybridRoutingDecision, metrics: ExecutionMetrics) -> None:
        self.routing_history.append((decision, metrics))

        agent = decision.primary_agent
        if agent not in self.agent_performance:
            self.agent_performance[agent] = []
        self.agent_performance[agent].append(metrics.quality_score)

        reward = metrics.compute_reward()
        logger.info(
            f"Routing feedback: agent={agent.value}, reward={reward:.3f}, success={metrics.success}"
        )

        try:
            task_type = decision.metadata.get("classification", "general")
            self.routing_memory.record(
                agent_id=agent.value,
                task_type=task_type,
                success=metrics.success,
                reward=reward,
                latency_ms=metrics.actual_latency_ms,
            )
        except Exception as e:
            logger.warning("Failed to persist routing feedback: %s", e)

    def get_agent_stats(self) -> dict[str, dict[str, float]]:
        """Get performance statistics for each agent."""
        stats = {}
        for agent, scores in self.agent_performance.items():
            if scores:
                stats[agent.value] = {
                    "avg_quality": sum(scores) / len(scores),
                    "uses": len(scores),
                    "recent_avg": sum(scores[-5:]) / min(5, len(scores[-5:])),
                }
        return stats

    def export_state(self) -> dict:
        return {
            "routing_history_count": len(self.routing_history),
            "agent_performance": {k.value: v for k, v in self.agent_performance.items()},
            "stats": self.get_agent_stats(),
            "routing_memory_path": str(self.routing_memory.path),
        }


# Convenience function for direct use
def route_task(
    task_description: str,
    classifier: Optional[Classifier] = None,
    use_mcts: bool = True,
) -> HybridRoutingDecision:
    """Simple interface for routing a task."""
    router = HybridHierarchicalRouter(classifier=classifier, use_mcts=use_mcts)
    return router.route(task_description)
