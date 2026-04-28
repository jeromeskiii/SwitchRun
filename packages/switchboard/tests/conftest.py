import sys
import os
from pathlib import Path

# Tests must not require live provider keys or network access.
os.environ.setdefault("SWITCHBOARD_OFFLINE", "1")

# Add project root to path for imports during testing
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
