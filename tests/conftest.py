import sys
import os
from pathlib import Path

# Add repo root to Python path so `app` is importable
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Set env vars to satisfy config validation without needing real LLM credentials
os.environ.setdefault("LLM_PROVIDER", "bedrock")
os.environ.setdefault("EMBED_PROVIDER", "bedrock")
