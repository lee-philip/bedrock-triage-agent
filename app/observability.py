"""Langfuse observability integration for the triage agent.

Provides callback handlers for LangChain/LangGraph tracing, manual span
instrumentation, and prompt management. Gracefully degrades when Langfuse
is disabled or unreachable.
"""
import os
import logging

from app.config import LLM_PROVIDER, LMSTUDIO_MODEL, BEDROCK_MODEL_ID

logger = logging.getLogger(__name__)

LANGFUSE_ENABLED = os.environ.get("LANGFUSE_ENABLED", "true").lower() == "true"
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")

_client = None
_handler = None


def get_model_name():
    """Return the configured model name for tagging."""
    if LLM_PROVIDER == "local":
        return LMSTUDIO_MODEL or "local-unknown"
    return BEDROCK_MODEL_ID or "bedrock-unknown"


def get_client():
    """Get the Langfuse client, initializing if needed."""
    global _client
    if _client is not None:
        return _client

    if not LANGFUSE_ENABLED:
        return None

    try:
        from langfuse import get_client as lf_get_client
        _client = lf_get_client(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            base_url=LANGFUSE_BASE_URL,
        )
        if not _client.auth_check():
            logger.warning("Langfuse authentication failed; tracing disabled")
            _client = None
    except Exception as e:
        logger.warning(f"Langfuse client initialization failed: {e}; tracing disabled")
        _client = None

    return _client


def get_callbacks(run_id, thread_id, eval_run_name=None):
    """Get Langfuse callback handler with proper session and metadata.

    Returns empty list if Langfuse is disabled or unavailable.
    """
    global _handler
    client = get_client()
    if client is None:
        return []

    tags = [LLM_PROVIDER, get_model_name()]
    if eval_run_name:
        tags.append(f"eval:{eval_run_name}")

    metadata = {
        "run_id": run_id,
        "thread_id": thread_id,
        "provider": LLM_PROVIDER,
        "model": get_model_name(),
    }
    if eval_run_name:
        metadata["eval_run"] = eval_run_name

    try:
        from langfuse.langchain import CallbackHandler
        _handler = CallbackHandler(
            session_id=run_id,
            tags=tags,
            metadata=metadata,
        )
        return [_handler]
    except Exception as e:
        logger.warning(f"Langfuse callback handler creation failed: {e}")
        return []


def flush():
    """Flush any pending Langfuse events."""
    client = get_client()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            logger.warning(f"Langfuse flush failed: {e}")


def add_score(trace_id, name, value, data_type="NUMERIC", observation_id=None):
    """Attach a score to a trace."""
    client = get_client()
    if client is None:
        return None
    try:
        kwargs = {
            "name": name,
            "value": value,
            "trace_id": trace_id,
            "data_type": data_type,
        }
        if observation_id:
            kwargs["observation_id"] = observation_id
        score = client.create_score(**kwargs)
        return score
    except Exception as e:
        logger.warning(f"Langfuse score creation failed: {e}")
        return None


def observe(name, as_type="span", **kwargs):
    """Return the Langfuse observe decorator, or a no-op decorator if unavailable."""
    client = get_client()
    if client is None:
        # Return a no-op decorator
        def noop_decorator(func):
            return func
        return noop_decorator

    try:
        from langfuse import observe as lf_observe
        return lf_observe(name=name, as_type=as_type, **kwargs)
    except Exception as e:
        logger.warning(f"Langfuse observe decorator failed: {e}")
        def noop_decorator(func):
            return func
        return noop_decorator


def start_span(name, **kwargs):
    """Start a manual span. Returns (span, langfuse) or (None, None) if unavailable.

    Caller must call span.end() when done.
    """
    client = get_client()
    if client is None:
        return None, None
    try:
        span = client.start_observation(name=name, **kwargs)
        return span, client
    except Exception as e:
        logger.warning(f"Langfuse span creation failed: {e}")
        return None, None


def get_prompt(name, label="production", fallback_path=None, **compile_vars):
    """Fetch a managed prompt from Langfuse.

    Falls back to local file if Langfuse is unavailable or prompt not found.
    Returns dict with 'prompt' (compiled string) and metadata fields.
    """
    client = get_client()
    metadata = {
        "prompt_name": name,
        "prompt_version": None,
        "prompt_source": "langfuse",
    }

    if client is not None:
        try:
            prompt = client.get_prompt(name, label=label)
            compiled = prompt.compile(**compile_vars)
            metadata["prompt_version"] = prompt.version
            metadata["prompt_id"] = prompt.id
            return {"prompt": compiled, **metadata}
        except Exception as e:
            logger.warning(f"Langfuse prompt fetch failed for {name}: {e}")

    # Fallback to local file
    metadata["prompt_source"] = "local"
    if fallback_path is None or not os.path.exists(fallback_path):
        raise FileNotFoundError(f"Prompt {name} not found in Langfuse or at {fallback_path}")

    with open(fallback_path) as f:
        template = f.read()

    # Simple variable substitution for local files
    import string
    try:
        template = template.format(**compile_vars)
    except (KeyError, IndexError, string.Template.SubstituteError) as e:
        # Fall back to plain string replacement
        for k, v in compile_vars.items():
            template = template.replace(f"{{{k}}}", str(v))

    metadata["prompt_version"] = "local"
    return {"prompt": template, **metadata}