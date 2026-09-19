import httpx
import litellm

# Curated subset for the Providers dropdown -- litellm.provider_list carries
# ~149 raw provider ids (confirmed live), far too many for a legible picker.
# "other" takes a free-text LiteLLM provider prefix instead of exposing the rest.
CURATED_PROVIDERS = [
    ("gemini", "Google Gemini"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("ollama", "Ollama (local)"),
    ("azure", "Azure OpenAI"),
    ("openrouter", "OpenRouter"),
    ("groq", "Groq"),
    ("mistral", "Mistral"),
    ("cohere", "Cohere"),
    ("other", "Other / custom"),
]

# Providers where a base URL is required, not just an optional override.
PROVIDERS_REQUIRING_BASE_URL = {"ollama", "azure", "other"}

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


def list_models_for_provider(provider_id: str) -> list[str] | None:
    """Known model ids for `provider_id` from litellm's static catalog, or None
    (never []) when there's no reliable catalog -- callers should fall back to
    free-text entry in that case, not treat None the same as "zero models
    exist". Ollama's litellm entry is a static stub, not live data (confirmed:
    it returns just ['llama2'] regardless of what's actually installed), so
    it's excluded here on purpose -- use probe_ollama() for that provider.
    """
    if provider_id in ("ollama", "other"):
        return None
    models = litellm.models_by_provider.get(provider_id)
    if not models:
        return None
    return sorted(models)


def get_model_capabilities(model_id: str) -> dict | None:
    """Wraps litellm.model_cost -- capability flags (supports_audio_input,
    supports_audio_output, mode, max_input_tokens, ...) for a known model id,
    or None if litellm has no metadata for it."""
    return litellm.model_cost.get(model_id)


def probe_ollama(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> list[str]:
    """Live, read-only query of an Ollama daemon's installed models -- never a
    pull, matching this project's established Ollama philosophy. Raises on
    failure (unreachable daemon, bad response) so the caller can show a clear
    error instead of a silently empty list."""
    url = base_url.rstrip("/") + "/api/tags"
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    return [m["name"] for m in data.get("models", [])]
