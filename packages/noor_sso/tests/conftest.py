import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'python'
sys.path.insert(0, str(root))
