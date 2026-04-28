# Copyright 2026 Human Systems. MIT License.
"""LLM client for agent execution.

Provides a thin wrapper around OpenAI and Anthropic APIs with a unified interface.
Falls back to a deterministic placeholder when no API key is configured.
"""

from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass
from typing import Optional, Dict, List
from collections import deque

from switchboard.env import load_environment, offline_mode_enabled

load_environment()

# Nexus model ID mapping
_NEXUS_MODEL_MAP: dict[str, tuple[str, str]] = {
    # Anthropic models
    "anthropic/claude-opus-4.6": ("anthropic", "claude-opus-4-20250514"),
    "anthropic/claude-sonnet-4.6": ("anthropic", "claude-sonnet-4-20250514"),
    "anthropic/claude-4.5-sonnet": ("anthropic", "claude-sonnet-4-20250514"),
    "anthropic/claude-haiku-4.5": ("anthropic", "claude-3-haiku-20240307"),
    "anthropic/claude-3-opus": ("anthropic", "claude-opus-4-20250514"),
    # OpenAI models
    "openai/gpt-5.1-codex": ("openai", "gpt-4o"),
    "openai/gpt-4o": ("openai", "gpt-4o"),
    "openai/gpt-4o-mini": ("openai", "gpt-4o-mini"),
    # OpenRouter models
    "openrouter/anthropic/claude-opus-4.6": ("openrouter", "anthropic/claude-opus-4-20250514"),
    "openrouter/anthropic/claude-sonnet-4.6": ("openrouter", "anthropic/claude-sonnet-4-20250514"),
    "openrouter/anthropic/claude-haiku-4.5": ("openrouter", "anthropic/claude-3-haiku-20240307"),
    "openrouter/qwen/qwen3-coder": ("openrouter", "qwen/qwen-2.5-72b-instruct"),
    "openrouter/deepseek/deepseek-r1": ("openrouter", "deepseek/deepseek-chat-v3-0324"),
    "openrouter/google/gemini-2.5-pro": ("openrouter", "google/gemini-2.0-flash-001"),
    "openrouter/meta-llama/llama-3.3-70b-instruct:free": ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
}


# ---------------------------------------------------------------------------
# MCTS model-ID → (provider, api_model_id) mapping.
# Lives outside the frozen dataclass to avoid mutable-default errors.
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-1.5-flash",
    "meta": "meta-llama/llama-3.1-70b-instruct",
    "openrouter": "openrouter/auto",
    "zai": "zai-default",
}

_MODEL_ID_MAP: dict[str, tuple[str, str]] = {
    "gpt-4o": ("openai", "gpt-4o"),
    "gpt-4o-mini": ("openai", "gpt-4o-mini"),
    "claude-3-5-sonnet": ("anthropic", "claude-sonnet-4-20250514"),
    "claude-3-haiku": ("anthropic", "claude-3-haiku-20240307"),
    "gemini-1.5-flash": ("openrouter", "google/gemini-flash-1.5"),
    "gemini-2.0-flash": ("openrouter", "google/gemini-2.0-flash-001"),
    "llama-3.1-70b": ("openrouter", "meta-llama/llama-3.1-70b-instruct"),
    "llama-3.3-70b": ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
    "deepseek-v3": ("openrouter", "deepseek/deepseek-chat-v3-0324"),
    "qwen-2.5-72b": ("openrouter", "qwen/qwen-2.5-72b-instruct"),
    "zai-default": ("zai", "default"),
    "mistral-large": ("openrouter", "mistralai/mistral-large-2411"),
}

# Rate limiting state per provider
_rate_limit_state: Dict[str, deque] = {}
_rate_limit_lock = threading.Lock()


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM calls.

    Attributes:
        provider: "openai", "anthropic", "openrouter", "google", or "meta"
        model: Model identifier (e.g. "gpt-4o", "claude-sonnet-4-20250514")
        max_tokens: Maximum tokens in the response
        temperature: Sampling temperature (0.0-2.0)
        timeout: Request timeout in seconds
        rate_limit_calls: Max calls per minute (0 = disabled)
    """

    provider: str = "openai"
    model: str = "gpt-4o"
    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = 30.0
    rate_limit_calls: int = 60  # 60 calls per minute default

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Build config from environment variables."""
        provider = os.environ.get("SWITCHBOARD_LLM_PROVIDER", "openai")
        if provider == "anthropic":
            model = os.environ.get("SWITCHBOARD_LLM_MODEL", "claude-sonnet-4-20250514")
            default_timeout = 30.0
        elif provider == "openrouter":
            model = os.environ.get("SWITCHBOARD_LLM_MODEL", "openrouter/auto")
            default_timeout = 60.0
        elif provider == "zai":
            model = os.environ.get("SWITCHBOARD_LLM_MODEL", "zai-default")
            default_timeout = 30.0
        else:
            model = os.environ.get("SWITCHBOARD_LLM_MODEL", "gpt-4o")
            default_timeout = 30.0
        return cls(
            provider=provider,
            model=model,
            max_tokens=int(os.environ.get("SWITCHBOARD_LLM_MAX_TOKENS", "2048")),
            temperature=float(os.environ.get("SWITCHBOARD_LLM_TEMPERATURE", "0.3")),
            timeout=float(os.environ.get("SWITCHBOARD_LLM_TIMEOUT", str(default_timeout))),
            rate_limit_calls=int(os.environ.get("SWITCHBOARD_RATE_LIMIT_CALLS", "60")),
        )

    @classmethod
    def from_mcts_selection(cls, mcts_metadata: dict) -> LLMConfig:
        """Build config from MCTS model selection metadata.

        The metadata dict is expected to have the shape produced by
        MCTSEnhancedClassifier, specifically the value stored at
        classification.metadata["mcts_model_selection"].

        Args:
            mcts_metadata: Dict with at least "model_id" key.

        Returns:
            LLMConfig configured for the MCTS-selected model.
        """
        model_id = mcts_metadata.get("model_id", "gpt-4o")

        if model_id in _MODEL_ID_MAP:
            provider, api_model = _MODEL_ID_MAP[model_id]
        else:
            # Fallback: try to infer provider from model_id prefix
            provider = "openai"
            api_model = model_id
            if "claude" in model_id:
                provider = "anthropic"
            elif "gemini" in model_id:
                provider = "openrouter"
            elif "llama" in model_id or "meta" in model_id:
                provider = "openrouter"

        return cls(
            provider=provider,
            model=api_model,
        )

    @classmethod
    def from_nexus_recommendation(cls, task_type: str = "general") -> "LLMConfig":
        """Build config from Nexus model advisor recommendation.

        Uses historical MCTS data from Nexus to select the best model
        for the given task type based on UCB1 scores.

        Args:
            task_type: Switchboard task type (coding, data_analysis, etc.)

        Returns:
            LLMConfig configured for the Nexus-recommended model,
            or default config if no Nexus data available.
        """
        try:
            from switchboard.nexus_advisor import recommend_model

            rec = recommend_model(task_type=task_type)
            if rec is None:
                return cls.from_env()

            nexus_model_id = rec.model

            # Map Nexus model ID to provider and API model
            if nexus_model_id in _NEXUS_MODEL_MAP:
                provider, api_model = _NEXUS_MODEL_MAP[nexus_model_id]
            else:
                # Infer from model ID
                provider = "openai"
                api_model = nexus_model_id
                if "claude" in nexus_model_id.lower():
                    provider = "anthropic"
                elif "openrouter" in nexus_model_id.lower():
                    provider = "openrouter"
                    api_model = nexus_model_id.replace("openrouter/", "")
                elif "zai" in nexus_model_id.lower():
                    provider = "zai"

            return cls(
                provider=provider,
                model=api_model,
            )
        except Exception:
            # Fallback to env-based config on any error
            return cls.from_env()

    @property
    def api_key(self) -> Optional[str]:
        if self.provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY")
        if self.provider == "openrouter":
            return os.environ.get("OPENROUTER_API_KEY")
        if self.provider == "zai":
            return os.environ.get("ZAI_API_KEY")
        return os.environ.get("OPENAI_API_KEY")

    @property
    def is_configured(self) -> bool:
        key = self.api_key
        if not key:
            return False
        # Simple placeholder check – key must be non‑empty and not a known placeholder
        invalid_keys = {
            "",
            "your_",
            "placeholder",
            "sk-placeholder",
            "your_openai_key_here",
            "your-anthropic-key",
        }
        return key.strip() not in invalid_keys


def _check_rate_limit(provider: str, rate_limit_calls: int) -> None:
    """Check and enforce rate limiting per provider.

    Args:
        provider: The LLM provider name
        rate_limit_calls: Maximum calls per minute (0 = disabled)

    Raises:
        RuntimeError: If rate limit is exceeded
    """
    if rate_limit_calls <= 0:
        return

    now = time.time()
    window_start = now - 60  # 1 minute window

    with _rate_limit_lock:
        # Initialize state for this provider if needed
        if provider not in _rate_limit_state:
            _rate_limit_state[provider] = deque()

        # Remove old entries outside the window
        calls = _rate_limit_state[provider]
        while calls and calls[0] < window_start:
            calls.popleft()

        # Check if limit exceeded
        if len(calls) >= rate_limit_calls:
            raise RuntimeError(
                f"Rate limit exceeded for {provider}: {rate_limit_calls} calls per minute"
            )

        # Record this call
        calls.append(now)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    config: Optional[LLMConfig] = None,
) -> str:
    """Call the configured LLM and return the response text.

    Args:
        system_prompt: System-level instructions for the model.
        user_prompt: The user message / task input.
        config: Optional LLM configuration. Uses env-based defaults when None.

    Returns:
        The assistant's response as plain text.

    Raises:
        RuntimeError: If the API call fails or rate limit exceeded.
    """
    cfg = config or LLMConfig.from_env()

    # Check rate limiting
    _check_rate_limit(cfg.provider, cfg.rate_limit_calls)

    if offline_mode_enabled() or not cfg.is_configured:
        return _placeholder_response(system_prompt, user_prompt)

    if cfg.provider == "anthropic":
        return _call_anthropic(system_prompt, user_prompt, cfg)
    if cfg.provider == "openrouter":
        return _call_openrouter(system_prompt, user_prompt, cfg)
    if cfg.provider == "zai":
        return _call_zai(system_prompt, user_prompt, cfg)
    return _call_openai(system_prompt, user_prompt, cfg)


def _call_openai(system_prompt: str, user_prompt: str, cfg: LLMConfig) -> str:
    import openai

    client = openai.OpenAI(api_key=cfg.api_key, timeout=cfg.timeout)
    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _call_zai(system_prompt: str, user_prompt: str, cfg: LLMConfig) -> str:
    """Call z.ai API (OpenAI-compatible with custom base URL).

    Uses the ZAI_API_KEY and ZAI_BASE_URL environment variables.
    Defaults to https://api.z.ai/v1 if ZAI_BASE_URL is not set.
    """
    import openai

    base_url = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/v1")
    client = openai.OpenAI(
        api_key=cfg.api_key,
        base_url=base_url,
        timeout=cfg.timeout,
    )
    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _call_anthropic(system_prompt: str, user_prompt: str, cfg: LLMConfig) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg.api_key, timeout=cfg.timeout)
    response = client.messages.create(
        model=cfg.model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )
    text = response.content[0].text
    return text.strip() if text else ""


def _call_openrouter(system_prompt: str, user_prompt: str, cfg: LLMConfig) -> str:
    import openai

    client = openai.OpenAI(
        api_key=cfg.api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=cfg.timeout,
    )
    response = client.chat.completions.create(
        model=cfg.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _placeholder_response(system_prompt: str, user_prompt: str) -> str:
    role = "assistant"
    if "reverse engineer" in system_prompt.lower() or "system design" in system_prompt.lower():
        role = "Reverse Engineering Agent"
    elif "data analysis" in system_prompt.lower() or "pandas" in system_prompt.lower():
        role = "Data Analysis Agent"
    elif "coding" in system_prompt.lower() or "implement" in system_prompt.lower():
        role = "Coding Agent"
    elif "documentation" in system_prompt.lower() or "summar" in system_prompt.lower():
        role = "Documentation Agent"
    elif "trading" in system_prompt.lower() or "market" in system_prompt.lower():
        role = "Trading Analysis Agent"
    elif "creative" in system_prompt.lower() or "storytelling" in system_prompt.lower():
        role = "Creative Writing Agent"
    return f"[{role}] Processed: {user_prompt}"
