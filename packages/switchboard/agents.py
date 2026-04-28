# Copyright 2026 Human Systems. MIT License.
"""Agent interface for Switchboard routing system."""

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from switchboard.env import ECOSYSTEM_ROOT, FUSION_ROOT, offline_mode_enabled
from switchboard.llm_client import LLMConfig, call_llm

# Import centralised ecosystem config (root-level config.py, not switchboard/config.py).
# When PYTHONPATH includes the project root (set by nexus_zero) this resolves immediately.
# Fall back to a path-based import for contexts where PYTHONPATH is not set (e.g. tests).
def _is_path_under_root(path: Path, root: Path) -> bool:
    """Return True if path is contained within root (resolving symlinks)."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (ValueError, OSError):
        return False


try:
    import importlib.util as _ilu

    _raw_config_path = os.environ.get("ECOSYSTEM_CONFIG_PATH", str(FUSION_ROOT / "config.py"))
    _config_path = Path(_raw_config_path).resolve()
    _allowed_root = FUSION_ROOT.resolve()

    if not _is_path_under_root(_config_path, _allowed_root):
        import logging

        _log = logging.getLogger(__name__)
        _log.warning(
            "ECOSYSTEM_CONFIG_PATH %s is outside allowed root %s; skipping dynamic load.",
            _config_path,
            _allowed_root,
        )
        ECOSYSTEM_CONFIG = None  # type: ignore[assignment]
    elif _config_path.exists():
        _spec = _ilu.spec_from_file_location("_root_config", _config_path)
        _root_config = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_root_config)  # type: ignore[union-attr]
        ECOSYSTEM_CONFIG = _root_config.ECOSYSTEM_CONFIG
    else:
        ECOSYSTEM_CONFIG = None  # type: ignore[assignment]
except Exception:
    ECOSYSTEM_CONFIG = None  # type: ignore[assignment]


_CLI_ARG_MAX_BYTES = 10_000
_INJECTION_PATTERN = re.compile(
    r"[;\|\&\`\$\(\)\{\}\<\>!]|"
    r"\$\{[^}]+\}|"
    r"\$\[[^\]]+\]|"
    r"^\s*\|"
)


def _sanitize_arg(value: str, name: str) -> str:
    """Sanitize a value before passing it as a CLI argument.

    Rejects values that contain shell metacharacters or exceed the byte limit.
    Raises ValueError on rejection.
    """
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    if len(value.encode("utf-8")) > _CLI_ARG_MAX_BYTES:
        raise ValueError(f"{name} exceeds maximum byte length of {_CLI_ARG_MAX_BYTES}")
    if _INJECTION_PATTERN.search(value):
        raise ValueError(f"{name} contains disallowed shell metacharacters")
    return value


def _resolve_llm_config(
    instance_config: Optional[LLMConfig],
    override_config: Optional[LLMConfig],
    task_type: str = "general",
    use_nexus: bool = True,
) -> Optional[LLMConfig]:
    """Resolve LLM config with Nexus fallback.

    Priority:
    1. override_config (if provided)
    2. instance_config (if provided)
    3. Nexus recommendation (if use_nexus=True)
    4. Environment-based default
    """
    if override_config is not None:
        return override_config
    if instance_config is not None:
        return instance_config
    if offline_mode_enabled():
        return None
    if use_nexus:
        try:
            return LLMConfig.from_nexus_recommendation(task_type)
        except Exception:
            pass
    return None


@dataclass
class AgentResult:
    """Result from an agent execution."""

    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[dict] = None


class Agent(ABC):
    """Base interface for all agents in the routing system.

    All agents must define `name` and `description` as class-level
    attributes and implement a run() method that takes input text
    and returns an AgentResult. This keeps agents decoupled from
    the routing logic.
    """

    name: str
    description: str

    @abstractmethod
    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the agent on the given input.

        Args:
            input_text: The user's input to process
            llm_config: Optional LLM config override (e.g. from MCTS selection)

        Returns:
            AgentResult with success status, output, and optional metadata
        """
        pass

    @abstractmethod
    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the agent on the given input.

        Args:
            input_text: The user's input to process
            llm_config: Optional LLM config override (e.g. from MCTS selection)

        Returns:
            AgentResult with success status, output, and optional metadata
        """
        pass

    def supports(self, classification: str) -> bool:
        """Check if this agent can handle the given classification.

        Override this method to specify which classifications
        an agent can handle.

        Args:
            classification: The task classification from the classifier

        Returns:
            True if this agent can handle the classification
        """
        return True


# Concrete agent implementations for common task types

# To add a new agent:
# 1. Create the class below
# 2. Add it to get_all_agents() list
# 3. Add AgentID entry in canonical_ids.py


def get_all_agents() -> list[type[Agent]]:
    return [
        ReverseEngineeringAgent,
        DataAnalysisAgent,
        CodingAgent,
        DocumentationAgent,
        SelfUpgradeAgent,
        TradingAnalysisAgent,
        CreativeWritingAgent,
        MasterAlphaAgent,
        NexusAgent,
        AgentRuntimeAgent,
        MythosAgent,
        PantheonAgent,
        GeneralAgent,
    ]


class LLMAgent(Agent):
    """Base class for agents backed by an LLM call.

    Subclasses must define SYSTEM_PROMPT as a class-level string.
    The run() method is shared by all LLM-backed agents.

    Subclasses can set `CORPUS_TOP_K` to a positive int to have the shared
    unified corpus (`Nexus00/data/_corpus.csv`) consulted for each input and
    a compact markdown context block prepended to the user prompt. Results
    respect the content policy (`data/_policy.py`).
    """

    SYSTEM_PROMPT: str = ""
    CORPUS_TOP_K: Optional[int] = None

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self._llm_config = llm_config

    def _augment_input(self, input_text: str) -> tuple[str, dict]:
        """Prepend corpus context when `CORPUS_TOP_K` is set. Fail-soft.

        Honors `SWITCHBOARD_CORPUS_DISABLE` (truthy values disable injection
        globally for A/B rollouts or emergency rollback).
        """
        if not self.CORPUS_TOP_K or self.CORPUS_TOP_K <= 0:
            return input_text, {}
        if os.environ.get("SWITCHBOARD_CORPUS_DISABLE", "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            return input_text, {"corpus_disabled": True}
        try:
            from switchboard import corpus_retrieval as cr
            items = cr.retrieve(input_text, top_k=int(self.CORPUS_TOP_K))
        except Exception as e:
            return input_text, {"corpus_error": f"{type(e).__name__}: {e}"}
        if not items:
            return input_text, {"corpus_hits": 0}
        block = cr.format_for_prompt(items)
        augmented = (
            "### Corpus context (unified Nexus corpus)\n"
            f"{block}\n\n"
            "### User request\n"
            f"{input_text}"
        )
        meta = {
            "corpus_hits": len(items),
            "corpus_identifiers": [it.identifier for it in items],
            "corpus_warnings": sum(1 for it in items if it.content_warning),
        }
        return augmented, meta

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        try:
            cfg = _resolve_llm_config(self._llm_config, llm_config, task_type=self.name)
            prompt, corpus_meta = self._augment_input(input_text)
            output = call_llm(self.SYSTEM_PROMPT, prompt, cfg)
            return AgentResult(
                success=True,
                output=output,
                metadata={"agent": self.name, **corpus_meta},
            )
        except (ConnectionError, TimeoutError) as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )


class ReverseEngineeringAgent(LLMAgent):
    SYSTEM_PROMPT = (
        "You are an expert reverse engineer and system architect. "
        "Analyze the given input to understand system structure, identify components, "
        "trace data flows, and produce clear technical analysis. "
        "When debugging, reason step by step about root causes. "
        "When designing, propose concrete architectures with trade-off analysis. "
        "When corpus context is provided, cite relevant items by identifier and "
        "surface any content warnings before relying on them."
    )
    CORPUS_TOP_K = 3
    name = "reverse_engineering"
    description = "Specialized in understanding, reverse engineering, and designing systems"

    def supports(self, classification: str) -> bool:
        return classification in {
            "reverse_engineering",
            "system_design",
            "architecture",
            "debugging",
        }


class DataAnalysisAgent(LLMAgent):
    """Agent specialized in pandas and data analysis tasks."""

    SYSTEM_PROMPT = (
        "You are an expert data analyst proficient in pandas, numpy, and statistical methods. "
        "Provide clear analysis, write idiomatic Python code for data manipulation, "
        "explain statistical results, and suggest visualizations when relevant. "
        "Always include reasoning behind analytical decisions. "
        "When corpus context is provided, cite relevant items by identifier and "
        "surface any content warnings before relying on them."
    )
    CORPUS_TOP_K = 3
    name = "data_analysis"
    description = "Specialized in data analysis, pandas operations, and data manipulation"

    def supports(self, classification: str) -> bool:
        return classification in {
            "data_analysis",
            "pandas",
            "data_manipulation",
            "statistics",
            "visualization",
        }


class CodingAgent(LLMAgent):
    """Agent specialized in general coding tasks."""

    SYSTEM_PROMPT = (
        "You are an expert software engineer. Write clean, well-structured code "
        "that follows best practices. When implementing features, consider edge cases "
        "and error handling. When refactoring, explain the improvements. "
        "When writing tests, ensure thorough coverage of critical paths."
    )

    name = "coding"
    description = "General purpose coding assistant"

    def supports(self, classification: str) -> bool:
        return classification in {
            "coding",
            "implementation",
            "refactoring",
            "testing",
        }


class DocumentationAgent(LLMAgent):
    """Agent specialized in documentation, reports, and summaries."""

    SYSTEM_PROMPT = (
        "You are an expert technical writer. Produce clear, well-organized documentation, "
        "reports, and summaries. Use precise language, proper formatting, and ensure "
        "information is accessible to the target audience. When summarizing, "
        "distill key points without losing essential context. "
        "When corpus context is provided, cite relevant items by identifier and "
        "respect any content warnings before referencing them."
    )
    CORPUS_TOP_K = 3

    name = "documentation"
    description = "Specialized in documentation, reporting, and concise summaries"

    def supports(self, classification: str) -> bool:
        return classification in {
            "documentation",
            "reporting",
            "summarization",
        }


class GeneralAgent(LLMAgent):
    """Default general-purpose agent for unclassified tasks."""

    SYSTEM_PROMPT = (
        "You are the Generalist Agent for the Switchboard orchestration system. "
        "Your mission is to provide high-quality, reliable assistance for a wide range of tasks "
        "that fall outside specialized agent domains.\n\n"
        "Guidelines:\n"
        "1. Accuracy: Provide factual, well-reasoned answers.\n"
        "2. Context Awareness: You are part of a multi-agent system (MZero/Nexus). Maintain a professional and helpful tone.\n"
        "3. Decisive Action: If a request is ambiguous, state your assumptions clearly and proceed with the most likely intent.\n"
        "4. Specialist Referral: If you detect a task is significantly better suited for a specialist agent (e.g., Coding, Data Analysis, Trading, Reverse Engineering), "
        "complete the general aspects of the request and recommend the specific specialist for further deep-dive.\n"
        "5. Corpus Grounding: When corpus context is provided, cite relevant items by identifier and respect any content warnings before referencing them."
    )
    CORPUS_TOP_K = 3

    name = "general"
    description = "General purpose agent for any task"

    def supports(self, classification: str) -> bool:
        return True


class SelfUpgradeAgent(LLMAgent):
    """Agent specialized in self-improvement, personal growth, and habit systems.

    This agent implements the Self Upgrade skill - a meta-skill for treating
    personal growth as a repeatable life operating system. It detects current
    stats, identifies highest-leverage leaks, runs micro-experiments, and
    converts results into compounding upgrades.
    """

    SYSTEM_PROMPT = (
        "You are a self-improvement orchestrator. You detect current personal stats, "
        "identify the highest-leverage leak, run small experiments, and convert the "
        "results into compounding upgrades across body, mind, emotions, habits, and skills.\n\n"
        "Core Principles:\n"
        "1. Audit first, optimize second.\n"
        "2. Improve one high-leverage weakness at a time.\n"
        "3. Prefer micro-experiments over motivational resets.\n"
        "4. Track evidence instead of relying on memory.\n"
        "5. Treat streaks as consistency infrastructure, not identity.\n\n"
        "Your output format for each interaction:\n"
        "1. Detection Result: Current domain, highest-leverage leak, evidence used\n"
        "2. Applied Upgrade: Selected level target, rationale, requirement remaining\n"
        "3. Micro-Experiment: Action, duration, success condition, evidence to capture\n"
        "4. Risk Flags: Ambiguities, avoidance patterns, overload conditions\n"
        "5. Preservation Guarantees: No vague motivation, no upgrade without proof"
    )

    name = "self_upgrade"
    description = "Self-improvement orchestrator for personal growth systems"

    def supports(self, classification: str) -> bool:
        return classification in {
            "self_upgrade",
            "self_improvement",
            "personal_growth",
            "habits",
            "productivity",
            "life_hacks",
            "self_audit",
            "daily_audit",
        }


class MasterAlphaAgent(Agent):
    """Agent that routes tasks to MasterAlpha AI brain for MCTS-based routing."""

    MASTERALPHA_PATH = os.environ.get(
        "MASTERALPHA_PATH",
        str(ECOSYSTEM_ROOT / "MasterAlpha"),
    )

    def __init__(self, llm_config: Optional[LLMConfig] = None, num_sims: int = 60):
        self._llm_config = llm_config
        self._num_sims = num_sims

    name = "master_alpha"
    description = "Routes tasks to MasterAlpha MCTS-based AI brain for advanced decision making"

    def supports(self, classification: str) -> bool:
        # MasterAlpha can handle any task type with its MCTS engine
        return True

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the task via MasterAlpha CLI."""
        try:
            safe_input = _sanitize_arg(input_text, "input_text")
        except ValueError as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )

        try:
            cmd = [
                "python3",
                "-m",
                "apps.cli.main",
                safe_input,
                "--task-type",
                "general",
                "--sims",
                str(self._num_sims),
            ]

            # Run MasterAlpha CLI
            result = subprocess.run(
                cmd,
                cwd=self.MASTERALPHA_PATH,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                # Parse JSON output
                try:
                    output_data = json.loads(result.stdout)
                    output_text = json.dumps(output_data, indent=2)
                except json.JSONDecodeError:
                    output_text = result.stdout

                return AgentResult(
                    success=True,
                    output=output_text,
                    metadata={
                        "agent": self.name,
                        "masteralpha_path": self.MASTERALPHA_PATH,
                    },
                )
            else:
                return AgentResult(
                    success=False,
                    output="",
                    error=f"MasterAlpha exited with code {result.returncode}: {result.stderr}",
                    metadata={"agent": self.name},
                )

        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output="",
                error="MasterAlpha execution timed out after 120 seconds",
                metadata={"agent": self.name},
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output="",
                error=f"MasterAlpha not found at {self.MASTERALPHA_PATH}",
                metadata={"agent": self.name},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )


class NexusAgent(Agent):
    """Agent that routes tasks to Nexus MCTS model orchestration system.

    Nexus selects the optimal LLM model for a task using MCTS-based
    algorithms (UCB1, PUCT, Gumbel, GA, reasoning) with cost-aware
    routing across Anthropic, OpenAI, and OpenRouter providers.
    """

    NEXUS_ROUTER_PATH = os.environ.get(
        "NEXUS_ROUTER_PATH",
        str(ECOSYSTEM_ROOT / "Nexus" / "router"),
    )
    NEXUS_CORE_PATH = os.environ.get(
        "NEXUS_CORE_PATH",
        str(ECOSYSTEM_ROOT / "Nexus" / "core"),
    )
    DEFAULT_FRAMEWORK = "coder"

    FRAMEWORK_MAP = {
        "coding": "coder",
        "implementation": "coder",
        "refactoring": "coder",
        "testing": "coder",
        "system_design": "architect",
        "architecture": "architect",
        "reverse_engineering": "reviewer",
        "debugging": "reviewer",
        "documentation": "writer",
        "reporting": "writer",
        "summarization": "writer",
        "data_analysis": "reasoning",
        "trading_analysis": "reasoning",
        "creative_writing": "creative",
        "general": "planner",
    }

    def __init__(self, llm_config: Optional[LLMConfig] = None, algorithm: str = "auto"):
        self._llm_config = llm_config
        self._algorithm = algorithm

    name = "nexus"
    description = "Routes tasks to Nexus MCTS model orchestration for optimal LLM selection"

    def supports(self, classification: str) -> bool:
        return True

    def _resolve_framework(self, classification: str) -> str:
        return self.FRAMEWORK_MAP.get(classification, self.DEFAULT_FRAMEWORK)

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the task via Nexus router CLI."""
        try:
            # Try the unified router first, fall back to core CLI
            result = self._run_router(input_text)
            if result is None:
                result = self._run_core(input_text)
            return result
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output="",
                error="Nexus execution timed out after 120 seconds",
                metadata={"agent": self.name},
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output="",
                error=f"Nexus not found at {self.NEXUS_ROUTER_PATH}",
                metadata={"agent": self.name},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )

    def _run_router(self, input_text: str) -> Optional[AgentResult]:
        """Run via the unified Nexus router CLI."""
        try:
            safe_input = _sanitize_arg(input_text, "input_text")
        except ValueError:
            return None

        cmd = [
            "node",
            "dist/cli.js",
            "select",
            "--prompt",
            safe_input,
            "--algorithm",
            self._algorithm,
            "--dry-run",
        ]

        result = subprocess.run(
            cmd,
            cwd=self.NEXUS_ROUTER_PATH,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return None

        try:
            output_data = json.loads(result.stdout)
            output_text = json.dumps(output_data, indent=2)
        except json.JSONDecodeError:
            output_text = result.stdout

        return AgentResult(
            success=True,
            output=output_text,
            metadata={
                "agent": self.name,
                "backend": "router",
                "nexus_path": self.NEXUS_ROUTER_PATH,
            },
        )

    def _run_core(self, input_text: str) -> AgentResult:
        """Run via the Nexus core CLI as fallback."""
        framework = self.DEFAULT_FRAMEWORK

        try:
            safe_input = _sanitize_arg(input_text, "input_text")
        except ValueError:
            return AgentResult(
                success=False,
                output="",
                error="input_text contains disallowed shell metacharacters",
                metadata={"agent": self.name},
            )

        cmd = [
            "npx",
            "tsx",
            "src/index.ts",
            "select",
            "--framework",
            framework,
            "--task",
            safe_input,
        ]

        result = subprocess.run(
            cmd,
            cwd=self.NEXUS_CORE_PATH,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            try:
                output_data = json.loads(result.stdout)
                output_text = json.dumps(output_data, indent=2)
            except json.JSONDecodeError:
                output_text = result.stdout

            return AgentResult(
                success=True,
                output=output_text,
                metadata={
                    "agent": self.name,
                    "backend": "core",
                    "nexus_path": self.NEXUS_CORE_PATH,
                },
            )
        else:
            return AgentResult(
                success=False,
                output="",
                error=f"Nexus core exited with code {result.returncode}: {result.stderr}",
                metadata={"agent": self.name},
            )


class TradingAnalysisAgent(LLMAgent):
    SYSTEM_PROMPT = (
        "You are an expert quantitative trading analyst and financial engineer. "
        "Analyze market data, evaluate trading strategies, perform backtesting analysis, "
        "and provide risk assessments. Use precise quantitative reasoning with proper "
        "statistical methods. When evaluating strategies, consider transaction costs, "
        "slippage, drawdown risk, and Sharpe ratios. When analyzing markets, identify "
        "trends, support/resistance levels, and relevant technical indicators."
    )

    name = "trading_analysis"
    description = "Specialized in trading analysis, market data, and quantitative strategies"

    def supports(self, classification: str) -> bool:
        return classification in {
            "trading_analysis",
            "market_analysis",
            "backtesting",
            "portfolio",
            "quantitative",
        }


class CreativeWritingAgent(LLMAgent):
    SYSTEM_PROMPT = (
        "You are an expert creative writer with mastery of storytelling, prose, poetry, "
        "and narrative craft. Write vivid, engaging content that demonstrates strong "
        "voice, compelling characters, and effective use of literary techniques. "
        "When crafting stories, consider structure, pacing, tension, and theme. "
        "When writing poetry, attend to rhythm, imagery, and emotional resonance. "
        "Adapt your style to match the requested genre and tone."
    )

    name = "creative_writing"
    description = "Specialized in creative writing, storytelling, poetry, and narrative craft"

    def supports(self, classification: str) -> bool:
        return classification in {
            "creative_writing",
            "storytelling",
            "fiction",
            "poetry",
            "narrative",
        }


class AgentRuntimeAgent(Agent):
    """Agent that routes tasks to TypeScript-based Agent Runtime for tool execution.

    Agent Runtime provides low-level tools like read, glob, bash, and switchboard.route
    for filesystem operations and bidirectional routing.
    """

    AGENT_RUNTIME_PATH = os.environ.get(
        "AGENT_RUNTIME_PATH",
        str(ECOSYSTEM_ROOT / "packages" / "agent-runtime"),
    )

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self._llm_config = llm_config

    name = "agent_runtime"
    description = "Routes tasks to Agent Runtime for TypeScript-based tool execution"

    def supports(self, classification: str) -> bool:
        return classification in {
            "agent_runtime",
            "tool_execution",
            "filesystem",
            "routing",
        }

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the task via Agent Runtime CLI."""
        try:
            # Determine which command to use based on input
            tool_name = self._detect_tool(input_text)

            if tool_name:
                return self._run_tool(tool_name, input_text)

            # Default: treat as a general input
            return self._run_general(input_text)

        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output="",
                error="Agent Runtime execution timed out after 60 seconds",
                metadata={"agent": self.name},
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output="",
                error=f"Agent Runtime not found at {self.AGENT_RUNTIME_PATH}",
                metadata={"agent": self.name},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )

    def _detect_tool(self, input_text: str) -> Optional[str]:
        """Detect which tool to use based on input patterns."""
        # Simple pattern matching for common operations
        if input_text.startswith("read ") or "read the file" in input_text.lower():
            return "read"
        if input_text.startswith("glob ") or "find files" in input_text.lower():
            return "glob"
        if input_text.startswith("bash ") or "run command" in input_text.lower():
            return "bash"
        return None

    def _run_tool(self, tool_name: str, input_text: str) -> AgentResult:
        """Run a specific tool via Agent Runtime."""
        # Extract the actual argument from input
        arg = input_text
        for prefix in ["read ", "glob ", "bash ", "run command ", "find files ", "read the file "]:
            if arg.lower().startswith(prefix):
                arg = arg[len(prefix) :].strip()
                break

        # Build tool input
        if tool_name == "read":
            tool_input = {"path": _sanitize_arg(arg, "path")}
        elif tool_name == "glob":
            tool_input = {"pattern": _sanitize_arg(arg, "pattern")}
        elif tool_name == "bash":
            tool_input = {"command": _sanitize_arg(arg, "command")}
        else:
            tool_input = {}

        cmd = [
            "node",
            "dist/index.js",
            "run",
            tool_name,
            json.dumps(tool_input),
        ]

        result = subprocess.run(
            cmd,
            cwd=self.AGENT_RUNTIME_PATH,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            try:
                output_data = json.loads(result.stdout)
                output_text = json.dumps(output_data, indent=2)
            except json.JSONDecodeError:
                output_text = result.stdout

            return AgentResult(
                success=True,
                output=output_text,
                metadata={
                    "agent": self.name,
                    "tool": tool_name,
                    "runtime_path": self.AGENT_RUNTIME_PATH,
                },
            )
        else:
            return AgentResult(
                success=False,
                output="",
                error=f"Agent Runtime exited with code {result.returncode}: {result.stderr}",
                metadata={"agent": self.name, "tool": tool_name},
            )

    def _run_general(self, input_text: str) -> AgentResult:
        """Run a general query through Agent Runtime."""
        # Guard: switchboard.route re-enters switchboard which would select
        # agent_runtime again for routing/tool_execution tasks — infinite loop.
        # Fall back to a direct LLM call instead.
        return AgentResult(
            success=False,
            output="",
            error=(
                "AgentRuntimeAgent cannot route general inputs back through "
                "switchboard.route (circular routing). "
                "Use a specific tool (read/glob/bash) or a different agent."
            ),
            metadata={"agent": self.name, "loop_guard": True},
        )


class MythosAgent(Agent):
    """Agent that routes tasks to Mythos Greek Pantheon AI system.

    Mythos provides MCTS-based model selection (Mnemosyne engine) and
    skilled execution via Greek mythology agents:
    - Prometheus: Strategic planning
    - Hephaestus: Deep code implementation
    - Sisyphus: Multi-stream orchestration
    - Ultrawork: Full activation chain
    """

    MYTHOS_PATH = os.environ.get(
        "MYTHOS_PATH",
        str(ECOSYSTEM_ROOT / "Mythos"),
    )
    MYTHOS_API_URL = os.environ.get(
        "MYTHOS_API_URL",
        "http://localhost:3001",
    )
    # Route non-skill tasks through Nexus/core MCTS for model selection
    SWITCHBOARD_URL = os.environ.get(
        "MYTHOS_SWITCHBOARD_URL",
        f"http://localhost:{ECOSYSTEM_CONFIG.ports.nexus_core if ECOSYSTEM_CONFIG else 8080}",
    )

    SKILL_TRIGGERS = {
        "plan this": "prometheus",
        "think through": "prometheus",
        "implement": "hephaestus",
        "fix this": "hephaestus",
        "build the feature": "hephaestus",
        "end-to-end": "sisyphus",
        "make it happen": "sisyphus",
        "don't stop until it's done": "sisyphus",
        "ultrawork": "ultrawork",
        "ulw": "ultrawork",
        "full send": "ultrawork",
        "just handle it": "ultrawork",
    }

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self._llm_config = llm_config

    name = "mythos"
    description = "Routes tasks to Mythos Greek Pantheon with MCTS model selection"

    def supports(self, classification: str) -> bool:
        return classification in {
            "mythos",
            "mcts_selection",
            "model_routing",
            "skill_execution",
            "greek_pantheon",
        }

    def _detect_skill(self, input_text: str) -> Optional[str]:
        """Detect which Mythos skill to activate based on trigger words."""
        text_lower = input_text.lower()
        for trigger, skill in self.SKILL_TRIGGERS.items():
            if trigger in text_lower:
                return skill
        return None

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        """Execute the task via Mythos API."""
        try:
            # Check if there's a skill trigger
            skill = self._detect_skill(input_text)

            if skill:
                return self._execute_skill(skill, input_text)

            # Otherwise do MCTS model selection
            return self._mcts_select(input_text)

        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output="",
                error="Mythos execution timed out after 60 seconds",
                metadata={"agent": self.name},
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output="",
                error=f"Mythos not found at {self.MYTHOS_PATH}",
                metadata={"agent": self.name},
            )
        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                metadata={"agent": self.name},
            )

    def _execute_skill(self, skill_name: str, input_text: str) -> AgentResult:
        """Execute a specific Mythos skill."""
        import urllib.request
        import urllib.error

        payload = json.dumps(
            {
                "skill": skill_name,
                "input": input_text,
                "context": {},
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.MYTHOS_API_URL}/api/skill/execute",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                return AgentResult(
                    success=result.get("success", True),
                    output=json.dumps(result, indent=2),
                    metadata={
                        "agent": self.name,
                        "skill": skill_name,
                        "mythos_path": self.MYTHOS_PATH,
                    },
                )
        except urllib.error.HTTPError as e:
            return AgentResult(
                success=False,
                output="",
                error=f"Mythos API error: {e.code} - {e.reason}",
                metadata={"agent": self.name, "skill": skill_name},
            )
        except urllib.error.URLError as e:
            return AgentResult(
                success=False,
                output="",
                error=f"Cannot connect to Mythos API at {self.MYTHOS_API_URL}: {e.reason}",
                metadata={"agent": self.name, "skill": skill_name},
            )

    def _mcts_select(self, input_text: str) -> AgentResult:
        """Use Mythos MCTS to select best model for the task."""
        import urllib.request
        import urllib.error

        # Derive task type from input for context-aware model selection
        text_lower = input_text.lower()
        if any(kw in text_lower for kw in ("code", "implement", "function", "class", "debug", "fix")):
            task_type = "coding"
        elif any(kw in text_lower for kw in ("data", "analyze", "pandas", "plot", "chart")):
            task_type = "data_analysis"
        elif any(kw in text_lower for kw in ("write", "story", "poem", "creative", "fiction")):
            task_type = "creative_writing"
        elif any(kw in text_lower for kw in ("trade", "market", "stock", "portfolio", "backtest")):
            task_type = "trading_analysis"
        elif any(kw in text_lower for kw in ("document", "summarize", "report")):
            task_type = "documentation"
        else:
            task_type = "general"

        # Estimate complexity from input length as a rough proxy
        word_count = len(input_text.split())
        complexity = min(1.0, word_count / 100)

        payload = json.dumps(
            {
                "taskType": task_type,
                "framework": task_type,
                "language": "typescript",
                "complexity": complexity,
                "simulations": 60,
                "input": input_text,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.SWITCHBOARD_URL}/select",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                return AgentResult(
                    success=result.get("success", True),
                    output=json.dumps(result, indent=2),
                    metadata={
                        "agent": self.name,
                        "mythos_path": self.MYTHOS_PATH,
                    },
                )
        except urllib.error.HTTPError as e:
            return AgentResult(
                success=False,
                output="",
                error=f"Mythos MCTS error: {e.code} - {e.reason}",
                metadata={"agent": self.name},
            )
        except urllib.error.URLError as e:
            # Server may not be running - return helpful message
            return AgentResult(
                success=False,
                output="",
                error=(
                    f"Mythos MCTS server not available at {self.SWITCHBOARD_URL}. "
                    f"Start with: cd {self.MYTHOS_PATH} && npm run dev:core"
                ),
                metadata={"agent": self.name},
            )


class PantheonAgent(Agent):
    """Agent that routes tasks through the Pantheon registry.

    Pantheon is a documentation-first registry of agent identities and triggers.
    This agent resolves a request to the best Pantheon agent based on the checked-in
    registry and, for compatible core agents, attempts an optional Mythos skill handoff.
    """

    PANTHEON_PATH = Path(os.environ.get("PANTHEON_PATH", str(ECOSYSTEM_ROOT / "Pantheon")))
    REGISTRY_PATH = PANTHEON_PATH / "agents.json"

    CORE_SKILL_MAP = {
        "Prometheus": "prometheus",
        "Hephaestus": "hephaestus",
        "Sisyphus": "sisyphus",
    }

    CATEGORY_AGENT_MAP = {
        "frontend": "coding",
        "backend": "coding",
        "data": "data_analysis",
        "devops": "reverse_engineering",
        "security": "reverse_engineering",
        "ai_ml": "coding",
        "mobile": "coding",
        "design": "documentation",
        "product": "documentation",
        "research": "reverse_engineering",
    }

    UTILITY_AGENT_MAP = {
        "Code_Formatter": "coding",
        "Git_Summoner": "coding",
        "Doc_Scribe": "documentation",
        "Test_Generator": "coding",
        "Dependency_Keeper": "coding",
        "Data_Analyst": "data_analysis",
        "Performance_Profiler": "reverse_engineering",
        "Complexity_Measurer": "reverse_engineering",
        "Meeting_Facilitator": "documentation",
        "Email_Drafter": "documentation",
        "API_Integrator": "coding",
        "Database_Migrator": "coding",
        "Code_Reviewer": "reverse_engineering",
        "Bug_Hunter": "reverse_engineering",
        "Accessibility_Checker": "documentation",
    }

    TIER_PRIORITY = {"core": 4, "domain": 3, "utility": 2, "meta": 1}

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self._llm_config = llm_config

    name = "pantheon"
    description = "Routes tasks through the Pantheon agent registry and optional Mythos handoff"

    def supports(self, classification: str) -> bool:
        return classification in {
            "pantheon",
            "routing",
            "agent_selection",
            "orchestration",
        }

    def run(self, input_text: str, llm_config: Optional[LLMConfig] = None) -> AgentResult:
        try:
            registry = self._load_registry()
            selection = self._select_agent(registry, input_text)
            route = self._build_route(selection)
            payload: dict[str, object] = {
                "pantheon": {
                    "path": str(self.PANTHEON_PATH),
                    "registry": str(self.REGISTRY_PATH),
                    "version": registry.get("version"),
                    "totalAgents": registry.get("totalAgents"),
                },
                "selection": selection,
                "route": route,
            }

            delegated = self._attempt_mythos_handoff(route, input_text)
            if delegated is not None:
                payload["delegated_execution"] = delegated

            return AgentResult(
                success=True,
                output=json.dumps(payload, indent=2),
                metadata={
                    "agent": self.name,
                    "selected_agent": selection["name"],
                    "pantheon_tier": selection["tier"],
                },
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                output="",
                error=f"Pantheon registry not found at {self.REGISTRY_PATH}",
                metadata={"agent": self.name},
            )
        except json.JSONDecodeError as exc:
            return AgentResult(
                success=False,
                output="",
                error=f"Pantheon registry is invalid JSON: {exc}",
                metadata={"agent": self.name},
            )
        except Exception as exc:
            return AgentResult(
                success=False,
                output="",
                error=str(exc),
                metadata={"agent": self.name},
            )

    def _load_registry(self) -> dict:
        with self.REGISTRY_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _iter_registry_agents(self, registry: dict) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []

        for agent in registry.get("tiers", {}).get("core", {}).get("agents", []):
            records.append({**agent, "tier": "core", "category": None})

        for category, agents in (
            registry.get("tiers", {}).get("domain", {}).get("categories", {}).items()
        ):
            for agent in agents:
                records.append({**agent, "tier": "domain", "category": category})

        for agent in registry.get("tiers", {}).get("utility", {}).get("agents", []):
            records.append({**agent, "tier": "utility", "category": None})

        for agent in registry.get("tiers", {}).get("meta", {}).get("agents", []):
            records.append({**agent, "tier": "meta", "category": None})

        return records

    def _select_agent(self, registry: dict, input_text: str) -> dict[str, object]:
        text = input_text.lower()
        best: Optional[tuple[int, int, dict[str, object], list[str]]] = None

        for agent in self._iter_registry_agents(registry):
            triggers = [
                trigger for trigger in agent.get("triggers", []) if isinstance(trigger, str)
            ]
            matches = [trigger for trigger in triggers if trigger.lower() in text]
            if not matches:
                continue

            trigger_score = sum(len(trigger) for trigger in matches)
            tier_score = self.TIER_PRIORITY.get(str(agent.get("tier")), 0)
            candidate = (len(matches), trigger_score + tier_score, agent, matches)

            if best is None or candidate[:2] > best[:2]:
                best = candidate

        selected_agent: dict[str, object]
        matched_triggers: list[str]
        if best is not None:
            _, _, selected_agent, matched_triggers = best
        else:
            selected_agent = {
                "id": "core-001",
                "name": "Prometheus",
                "domain": "strategy",
                "tier": "core",
                "category": None,
                "triggers": ["plan", "architect", "design system"],
            }
            matched_triggers = []

        return {
            "id": selected_agent["id"],
            "name": selected_agent["name"],
            "tier": selected_agent["tier"],
            "category": selected_agent.get("category"),
            "domain": selected_agent.get("domain"),
            "triggers": selected_agent.get("triggers", []),
            "matchedTriggers": matched_triggers,
            "fallbackUsed": best is None,
        }

    def _build_route(self, selection: dict[str, object]) -> dict[str, object]:
        name = str(selection["name"])
        tier = str(selection["tier"])
        category = selection.get("category")

        mythos_skill = self.CORE_SKILL_MAP.get(name)
        if mythos_skill:
            return {
                "strategy": "switchboard->pantheon->mythos",
                "switchboardAgent": "pantheon",
                "mythosSkill": mythos_skill,
                "suggestedSwitchboardFallback": "mythos",
            }

        if tier == "domain" and isinstance(category, str):
            fallback_agent = self.CATEGORY_AGENT_MAP.get(category, "general")
        elif tier == "utility":
            fallback_agent = self.UTILITY_AGENT_MAP.get(name, "general")
        elif tier == "meta":
            fallback_agent = "reverse_engineering"
        else:
            fallback_agent = "general"

        return {
            "strategy": "switchboard->pantheon->switchboard-agent",
            "switchboardAgent": "pantheon",
            "suggestedSwitchboardFallback": fallback_agent,
        }

    def _attempt_mythos_handoff(
        self, route: dict[str, object], input_text: str
    ) -> Optional[dict[str, object]]:
        mythos_skill = route.get("mythosSkill")
        if not isinstance(mythos_skill, str):
            return None

        delegated = MythosAgent(llm_config=self._llm_config)._execute_skill(
            mythos_skill, input_text
        )
        payload: dict[str, object] = {
            "attempted": True,
            "mythosSkill": mythos_skill,
            "success": delegated.success,
        }

        if delegated.success:
            try:
                payload["result"] = json.loads(delegated.output)
            except json.JSONDecodeError:
                payload["result"] = delegated.output
        elif delegated.error:
            payload["error"] = delegated.error

        return payload
