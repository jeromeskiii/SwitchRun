"""Environment loading helpers for Switchboard."""

from __future__ import annotations

import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
FUSION_ROOT = PACKAGE_DIR.parent.parent
ECOSYSTEM_ROOT = Path(os.environ.get("ECOSYSTEM_ROOT", str(FUSION_ROOT)))
DEFAULT_ENV_PATHS = (
    PACKAGE_DIR / ".env",
    FUSION_ROOT / ".env",
)


def load_environment(paths: tuple[Path, ...] = DEFAULT_ENV_PATHS) -> None:
    """Load known local .env files without overriding existing env vars."""
    for path in paths:
        if not path.exists():
            continue

        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and value and key not in os.environ:
                os.environ[key] = value


def offline_mode_enabled() -> bool:
    """Return true when Switchboard should avoid live provider calls."""
    return os.environ.get("SWITCHBOARD_OFFLINE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
