# Copyright 2026 Human Systems. MIT License.
"""Persistent routing memory for feedback-driven routing improvement.

Tracks which agent/strategy succeeded for which task type and uses
historical performance to bias future routing decisions.
"""

from __future__ import annotations

import atexit
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from photonic import EXECUTION_COMPLETED, PhotonicBus, PhotonicEvent
    _PHOTONIC_AVAILABLE = True
except ImportError:
    _PHOTONIC_AVAILABLE = False

# Records older than this get 0.5x weight
DECAY_THRESHOLD_SECONDS = 7 * 24 * 3600  # 7 days
DECAY_FACTOR = 0.5
# Minimum records before historical bias kicks in
MIN_RECORDS_FOR_BIAS = 5
# How much historical performance biases agent fit scores
BIAS_STRENGTH = 0.3


@dataclass
class RoutingRecord:
    """A single routing outcome record."""

    agent_id: str
    task_type: str
    success: bool
    reward: float
    latency_ms: float
    timestamp: float = field(default_factory=time.time)

    def weight(self, now: Optional[float] = None) -> float:
        """Return time-decay weight for this record."""
        now = now or time.time()
        age = now - self.timestamp
        return DECAY_FACTOR if age > DECAY_THRESHOLD_SECONDS else 1.0


class RoutingMemory:
    """Persistent routing memory that saves/loads routing history.

    Schema on disk (routing_memory.json):
    {
        "records": [
            {"agent_id": str, "task_type": str, "success": bool,
             "reward": float, "latency_ms": float, "timestamp": float},
            ...
        ]
    }

    Aggregated view (computed on load):
    {task_type -> {agent_id -> {wins, losses, total_reward, count,
                                avg_latency_ms, weighted_avg_reward}}}

    Writes are non-blocking: records are buffered in memory and flushed
    to disk by a background daemon thread every ``flush_interval`` seconds
    (default 5 s).  The write is atomic — a temporary file is written
    then renamed to the target path so a crash never corrupts the JSON.
    """

    _FLUSH_INTERVAL = 5.0  # seconds between background flushes

    def __init__(self, path: Optional[Path] = None, max_records: int = 5000):
        self.path = path or Path(__file__).resolve().parent / "routing_memory.json"
        self.max_records = max_records
        self._records: list[RoutingRecord] = []
        self._dirty = False          # True when unflushed records exist
        self._lock = threading.Lock()
        self._load()
        self._start_flush_thread()
        self._subscribe_photonic()
        atexit.register(self._atexit_shutdown)

    def _atexit_shutdown(self) -> None:
        """Called on process exit to flush unflushed records."""
        self.flush()

    def _subscribe_photonic(self) -> None:
        """Subscribe to Photonic EXECUTION_COMPLETED events for auto-recording."""
        if not _PHOTONIC_AVAILABLE:
            return
        try:
            PhotonicBus.instance().on(EXECUTION_COMPLETED, self._on_execution_completed)
            logger.debug("routing memory subscribed to photonic execution events")
        except Exception as exc:
            logger.debug("photonic subscription failed: %s", exc)

    def _on_execution_completed(self, event: "PhotonicEvent") -> None:
        """Handle Photonic execution completed events."""
        try:
            p = event.payload
            self.record(
                agent_id=str(p.get("agent", "unknown")),
                task_type=str(p.get("task_type", "unknown")),
                success=bool(p.get("success", False)),
                reward=1.0 if p.get("success") else 0.0,
                latency_ms=float(p.get("latency_ms", 0)),
            )
        except Exception as exc:
            logger.debug("photonic event handling failed: %s", exc)

    # ── background flush thread ───────────────────────────────────

    def _start_flush_thread(self) -> None:
        t = threading.Thread(target=self._flush_loop, daemon=True, name="routing-memory-flush")
        t.start()

    def _flush_loop(self) -> None:
        """Background thread: flush dirty records every FLUSH_INTERVAL seconds."""
        while True:
            time.sleep(self._FLUSH_INTERVAL)
            with self._lock:
                if self._dirty:
                    self._save_locked()

    # ── persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        if not self.path.exists():
            self._records = []
            return
        try:
            data = json.loads(self.path.read_text())
            self._records = [
                RoutingRecord(**r) for r in data.get("records", [])
            ]
        except Exception as e:
            logger.warning("Failed to load routing memory: %s", e)
            self._records = []

    def _save_locked(self) -> None:
        """Atomic write: serialize to a tmp file then rename. Must be called with _lock held."""
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(
                {"records": [vars(r) for r in self._records]},
                indent=2,
            ))
            tmp.replace(self.path)
            self._dirty = False
        except Exception as e:
            logger.warning("Failed to save routing memory: %s", e)

    def flush(self) -> None:
        """Force an immediate synchronous flush (useful for tests / shutdown)."""
        with self._lock:
            self._save_locked()

    # ── recording ────────────────────────────────────────────────

    def record(
        self,
        agent_id: str,
        task_type: str,
        success: bool,
        reward: float = 1.0,
        latency_ms: float = 0.0,
    ) -> None:
        """Record a routing outcome. The write is deferred to the background flush thread."""
        with self._lock:
            self._records.append(RoutingRecord(
                agent_id=agent_id,
                task_type=task_type,
                success=success,
                reward=reward,
                latency_ms=latency_ms,
            ))
            self._dirty = True

    # ── querying ─────────────────────────────────────────────────

    def agent_bias(self, agent_id: str, task_type: str) -> float:
        """Return a bias term for the given agent on the given task type.

        Returns 0.0 if fewer than MIN_RECORDS_FOR_BIAS records exist.
        Otherwise returns (weighted_avg_reward - 0.5) * BIAS_STRENGTH,
        clamped to [-BIAS_STRENGTH, +BIAS_STRENGTH].
        """
        now = time.time()
        with self._lock:
            relevant = [
                r for r in self._records
                if r.agent_id == agent_id and r.task_type == task_type
            ]
        if len(relevant) < MIN_RECORDS_FOR_BIAS:
            return 0.0

        total_weight = sum(r.weight(now) for r in relevant)
        if total_weight == 0:
            return 0.0

        weighted_avg = sum(r.reward * r.weight(now) for r in relevant) / total_weight
        bias = (weighted_avg - 0.5) * BIAS_STRENGTH
        return max(-BIAS_STRENGTH, min(BIAS_STRENGTH, bias))

    def summary(self) -> dict:
        """Return aggregated stats: {task_type -> {agent_id -> stats}}."""
        now = time.time()
        agg: dict[str, dict[str, dict]] = {}
        for r in self._records:
            by_agent = agg.setdefault(r.task_type, {})
            stats = by_agent.setdefault(r.agent_id, {
                "wins": 0, "losses": 0, "total_reward": 0.0,
                "count": 0, "total_latency_ms": 0.0,
                "weighted_reward_sum": 0.0, "weight_sum": 0.0,
            })
            stats["count"] += 1
            if r.success:
                stats["wins"] += 1
            else:
                stats["losses"] += 1
            w = r.weight(now)
            stats["total_reward"] += r.reward
            stats["total_latency_ms"] += r.latency_ms
            stats["weighted_reward_sum"] += r.reward * w
            stats["weight_sum"] += w

        # Compute derived fields
        for task_agents in agg.values():
            for stats in task_agents.values():
                stats["avg_latency_ms"] = (
                    stats["total_latency_ms"] / stats["count"]
                    if stats["count"] > 0 else 0.0
                )
                stats["weighted_avg_reward"] = (
                    stats["weighted_reward_sum"] / stats["weight_sum"]
                    if stats["weight_sum"] > 0 else 0.0
                )
                # Clean up internal fields
                del stats["weighted_reward_sum"]
                del stats["weight_sum"]
                del stats["total_latency_ms"]

        return agg
