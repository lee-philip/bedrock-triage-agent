import sys
from pathlib import Path

# Add repo root to Python path so `app` is importable
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
