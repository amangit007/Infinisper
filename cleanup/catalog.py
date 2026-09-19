from dataclasses import dataclass
from urllib.parse import urlparse

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

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


def normalize_local_url(base_url: str | None) -> str | None:
    """On Windows "localhost" resolves to the IPv6 address ::1 first, and Ollama only listens
    on IPv4, so every new connection to "localhost" waits ~2 s for IPv6 to fail. Measured:
    2,048 ms vs 1.2 ms. Always dial the IPv4 loopback address directly."""
    if not base_url:
        return base_url
    return str(base_url).replace("localhost", "127.0.0.1")


def is_local_endpoint(model: str, base_url: str | None) -> bool:
    """Does this model run on the user's own machine (so nothing leaves it)?

    True for any endpoint on a loopback address, and for an Ollama model with no base URL
    (Ollama's own default is loopback). A hosted provider (Gemini, Groq, ...) is neither."""
    if base_url:
        host = urlparse(normalize_local_url(base_url)).hostname or ""
        return host in ("127.0.0.1", "::1", "0.0.0.0")
    return model.startswith("ollama/")


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
    url = normalize_local_url(base_url).rstrip("/") + "/api/tags"
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    return [m["name"] for m in data.get("models", [])]


@dataclass
class OllamaStatus:
    models: list[str]
    problem: str | None = None  # None when reachable and at least one model is installed
    show_install_link: bool = False


def ollama_status(base_url: str = DEFAULT_OLLAMA_BASE_URL) -> OllamaStatus:
    """What the user should be told about their Ollama, in words. Read-only: this app never
    installs Ollama or pulls a model for the user -- it only says what's missing."""
    try:
        models = probe_ollama(base_url)
    except Exception:
        return OllamaStatus(
            [],
            f"Ollama isn't running at {normalize_local_url(base_url)}. Start it, or install it first.",
            show_install_link=True,
        )
    if not models:
        return OllamaStatus(
            [],
            "Ollama is running but has no models yet. Pull a small one in a terminal, "
            "for example: ollama pull gemma4:e4b",
        )
    return OllamaStatus(models)
