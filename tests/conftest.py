"""Shared test setup: keyless and offline by construction.

config/settings.py reads OPENAI_API_KEY when it is imported, and
load_dotenv() never overrides a variable that is already set. Forcing an
empty key here, before any project module is imported, keeps every test
in simulation mode even when a local .env holds a real key.
"""

import os
import sys
from pathlib import Path

os.environ["OPENAI_API_KEY"] = ""

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
