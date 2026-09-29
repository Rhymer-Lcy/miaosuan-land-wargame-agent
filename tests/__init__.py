"""Test package. Makes ``src/`` importable so the suite runs from a plain checkout:

    python -m unittest discover -s tests -t .
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
