from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Optional

try:
    from config import EcosystemConfig
except ImportError:
    try:
        import importlib.util as _ilu
        import os
        from pathlib import Path
        from switchboard.env import FUSION_ROOT
        _config_path = Path(os.environ.get("ECOSYSTEM_CONFIG_PATH", str(FUSION_ROOT / "config.py")))
        if _config_path.exists():
            _spec = _ilu.spec_from_file_location("_root_config", _config_path)
            _root_config = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_root_config)
            EcosystemConfig = _root_config.EcosystemConfig
        else:
            EcosystemConfig = None
    except Exception:
        EcosystemConfig = None


class RuntimeEnforcement:
    def __init__(self, config: Optional[EcosystemConfig] = None):
        self._config = config
        self._fail_counts: dict[str, int] = {}
        self._circuit_open: dict[str, bool] = {}
        self._circuit_opened_at: dict[str, float] = {}
        self._rate_timestamps: list[float] = []
        self._rate_hour_timestamps: list[float] = []
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._cb_threshold = getattr(getattr(config, "circuit_breaker", None), "threshold", 3) if config else 3
        self._cb_cooldown = getattr(getattr(config, "circuit_breaker", None), "cooldown_seconds", 60) if config else 60
        self._rpm = getattr(getattr(config, "rate_limit", None), "requests_per_minute", 60) if config else 60
        self._rph = getattr(getattr(config, "rate_limit", None), "requests_per_hour", 1000) if config else 1000
        self._cache_enabled = getattr(getattr(config, "cache", None), "enabled", True) if config else True
        self._cache_ttl = getattr(getattr(config, "cache", None), "ttl_seconds", 300) if config else 300
        self._cache_max = getattr(getattr(config, "cache", None), "max_size", 10000) if config else 10000

    def check_circuit_breaker(self, agent_id: str) -> bool:
        with self._lock:
            if not self._circuit_open.get(agent_id, False):
                return True
            opened_at = self._circuit_opened_at.get(agent_id, 0)
            if time.time() - opened_at > self._cb_cooldown:
                self._circuit_open[agent_id] = False
                self._fail_counts[agent_id] = 0
                return True
            return False

    def record_failure(self, agent_id: str) -> None:
        with self._lock:
            count = self._fail_counts.get(agent_id, 0) + 1
            self._fail_counts[agent_id] = count
            if count >= self._cb_threshold:
                self._circuit_open[agent_id] = True
                self._circuit_opened_at[agent_id] = time.time()

    def record_success(self, agent_id: str) -> None:
        with self._lock:
            self._fail_counts[agent_id] = 0
            self._circuit_open[agent_id] = False

    def check_rate_limit(self) -> bool:
        now = time.time()
        with self._lock:
            self._rate_timestamps = [t for t in self._rate_timestamps if now - t < 60]
            self._rate_hour_timestamps = [t for t in self._rate_hour_timestamps if now - t < 3600]
            if len(self._rate_timestamps) >= self._rpm:
                return False
            if len(self._rate_hour_timestamps) >= self._rph:
                return False
            self._rate_timestamps.append(now)
            self._rate_hour_timestamps.append(now)
            return True

    def get_cached(self, key: str) -> Optional[str]:
        if not self._cache_enabled:
            return None
        with self._lock:
            if key not in self._cache:
                return None
            value, ts = self._cache[key]
            if time.time() - ts > self._cache_ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return value

    def set_cached(self, key: str, value: str) -> None:
        if not self._cache_enabled:
            return
        with self._lock:
            self._cache[key] = (value, time.time())
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max:
                self._cache.popitem(last=False)

    @staticmethod
    def cache_key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]
