from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings
from app.config import (
    LLM_PROVIDER, EMBED_PROVIDER,
    LMSTUDIO_BASE_URL, LMSTUDIO_MODEL, LMSTUDIO_EMBED_MODEL,
    BEDROCK_MODEL_ID, BEDROCK_EMBED_MODEL_ID, AWS_REGION
)


def get_chat_model():
    """Factory: returns the configured chat model for the current provider."""
    if LLM_PROVIDER == "local":
        return ChatOpenAI(
            base_url=LMSTUDIO_BASE_URL,
            api_key="lm-studio",
            model=LMSTUDIO_MODEL,
            temperature=0,
        )
    elif LLM_PROVIDER == "bedrock":
        return ChatBedrockConverse(
            model=BEDROCK_MODEL_ID,
            region_name=AWS_REGION,
            temperature=0,
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")


def get_embeddings():
    """Factory: returns the configured embeddings model for the current provider."""
    if EMBED_PROVIDER == "local":
        return OpenAIEmbeddings(
            openai_api_base=LMSTUDIO_BASE_URL,
            openai_api_key="lm-studio",
            model=LMSTUDIO_EMBED_MODEL,
            check_embedding_ctx_length=False,
        )
    elif EMBED_PROVIDER == "bedrock":
        return BedrockEmbeddings(
            model_id=BEDROCK_EMBED_MODEL_ID,
            region_name=AWS_REGION,
        )
    else:
        raise ValueError(f"Unknown EMBED_PROVIDER: {EMBED_PROVIDER}")
