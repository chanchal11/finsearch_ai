from __future__ import annotations

from strands.models.model import Model

from src.config import Settings

_BEDROCK = "bedrock"
_OLLAMA = "ollama"
_GROQ = "groq"
_SUPPORTED = "bedrock, ollama, or groq"


def build_model(settings: Settings) -> Model | str:
    """Return the Strands model selected by STRANDS_PROVIDER.

    ``bedrock`` keeps the historical path: a model id string, which Strands
    sends to Amazon Bedrock. ``ollama`` builds an OllamaModel against OLLAMA_HOST.
    ``groq`` builds an OpenAI-compatible client pointed at the Groq API.
    """
    provider = settings.strands_provider.strip().lower()
    model_id = settings.strands_model.strip()
    if provider == _BEDROCK:
        return model_id
    if provider == _OLLAMA:
        _require_model_id(provider, model_id)
        host = settings.ollama_host.strip() or "http://127.0.0.1:11434"
        from strands.models.ollama import OllamaModel

        return OllamaModel(host=host, model_id=model_id)
    if provider == _GROQ:
        _require_model_id(provider, model_id)
        api_key = settings.groq_api_key.strip()
        if not api_key:
            raise ValueError("GROQ_API_KEY is required when STRANDS_PROVIDER=groq.")
        base_url = settings.groq_base_url.strip() or "https://api.groq.com/openai/v1"
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={"api_key": api_key, "base_url": base_url},
            model_id=model_id,
        )
    raise ValueError(
        f"Unsupported STRANDS_PROVIDER={settings.strands_provider!r}. Use {_SUPPORTED}."
    )


def _require_model_id(provider: str, model_id: str) -> None:
    if not model_id:
        raise ValueError(f"STRANDS_MODEL must be set when STRANDS_PROVIDER={provider}.")
