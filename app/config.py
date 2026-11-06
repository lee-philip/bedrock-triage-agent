import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local")
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "local")
LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL")
LMSTUDIO_EMBED_MODEL = os.environ.get("LMSTUDIO_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
BEDROCK_EMBED_MODEL_ID = os.environ.get("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-2")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "bedrock-triage")
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "1")
GUARDRAIL_REGION = os.environ.get("GUARDRAIL_REGION", AWS_REGION)


def validate():
    if LLM_PROVIDER == "local" and not LMSTUDIO_MODEL:
        raise RuntimeError("LLM_PROVIDER=local requires LMSTUDIO_MODEL env var")
    if LLM_PROVIDER == "bedrock" and not BEDROCK_MODEL_ID:
        raise RuntimeError("LLM_PROVIDER=bedrock requires BEDROCK_MODEL_ID env var")
    if EMBED_PROVIDER == "local" and not LMSTUDIO_MODEL:
        raise RuntimeError("EMBED_PROVIDER=local requires LMSTUDIO_MODEL env var")


validate()
