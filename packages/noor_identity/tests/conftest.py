import sys
from pathlib import Path

for package in ("noor_identity", "noor_contracts"):
    root = Path(__file__).resolve().parents[2] / package
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
