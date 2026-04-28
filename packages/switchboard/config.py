# Copyright 2026 Human Systems. MIT License.
"""Configuration layer for Switchboard routing system.

Centralizes all configurable thresholds and parameters with validation.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SwitchboardConfig:
    """Configuration for Switchboard routing behavior.

    All thresholds are validated at construction time to ensure
    they are within valid ranges.

    Attributes:
        low_confidence_threshold: Minimum confidence before falling back to general agent (0.0-1.0)
        fallback_threshold: Confidence threshold for triggering fallback on failure (0.0-1.0)
        max_retries: Maximum retry attempts before giving up (>= 0)
        validate_plans: Whether to run sanity checks on plans before execution
        debug_logging: Whether to enable detailed debug logging
        dedupe_steps: Whether to merge consecutive steps with the same agent
        max_input_length: Maximum input text length (default: 10000 chars)
        enable_audit_logging: Whether to log execution history
        audit_log_path: Path to audit log file (default: switchboard_audit.log)
    """

    low_confidence_threshold: float = 0.4
    fallback_threshold: float = 0.45
    max_retries: int = 2
    validate_plans: bool = True
    debug_logging: bool = False
    dedupe_steps: bool = True
    use_mcts_routing: bool = False
    mcts_budget: int = 50
    max_input_length: int = 10000
    enable_audit_logging: bool = True
    audit_log_path: str = "switchboard_audit.log"
    # When True, the CLI and execute() helpers use EnhancedRouter (hierarchical+MCTS path).
    # Defaults to False to preserve existing behaviour; set to True via --hierarchical flag
    # or SWITCHBOARD_HIERARCHICAL=1 env var.
    use_hierarchical: bool = False

    def __post_init__(self):
        # Validate thresholds are within valid ranges
        if not 0.0 <= self.low_confidence_threshold <= 1.0:
            raise ValueError(
                f"low_confidence_threshold must be between 0.0 and 1.0, "
                f"got {self.low_confidence_threshold}"
            )
        if not 0.0 <= self.fallback_threshold <= 1.0:
            raise ValueError(
                f"fallback_threshold must be between 0.0 and 1.0, got {self.fallback_threshold}"
            )
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {self.max_retries}")
        if self.mcts_budget < 1:
            raise ValueError(f"mcts_budget must be at least 1, got {self.mcts_budget}")
        if self.max_input_length < 1:
            raise ValueError(f"max_input_length must be at least 1, got {self.max_input_length}")

    @classmethod
    def from_dict(cls, config_dict: dict) -> "SwitchboardConfig":
        """Create config from a dictionary, ignoring unknown keys.

        Args:
            config_dict: Dictionary containing configuration values

        Returns:
            SwitchboardConfig with validated values
        """
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in config_dict.items() if k in valid_keys}
        return cls(**filtered)

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "low_confidence_threshold": self.low_confidence_threshold,
            "fallback_threshold": self.fallback_threshold,
            "max_retries": self.max_retries,
            "validate_plans": self.validate_plans,
            "debug_logging": self.debug_logging,
            "dedupe_steps": self.dedupe_steps,
            "use_mcts_routing": self.use_mcts_routing,
            "mcts_budget": self.mcts_budget,
            "max_input_length": self.max_input_length,
            "enable_audit_logging": self.enable_audit_logging,
            "audit_log_path": self.audit_log_path,
            "use_hierarchical": self.use_hierarchical,
        }
