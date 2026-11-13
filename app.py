"""Run Flask from the project root while retaining the existing layout."""

import sys
from pathlib import Path

# Existing backend scripts use sibling imports such as `from config import ...`.
backend_directory = str(Path(__file__).resolve().parent / "code")
if backend_directory not in sys.path:
    sys.path.insert(0, backend_directory)

from frontend.app import create_app