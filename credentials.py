import keyring
import keyring.errors

# Every multimodal provider's API key is stored under this one keyring service
# name, keyed by the provider's id (e.g. "gemini", "openai"). On Windows this
# lands in Credential Manager -- never in config.json, never logged. The app
# reads it straight back to show in the Providers tab's plaintext field; that's
# a deliberate product choice (keys are visible inside the app, nowhere else),
# not an oversight.
_SERVICE_NAME = "infinisper"
_LEGACY_SERVICE_NAME = "freewisperr"


def set_api_key(provider_id: str, key: str) -> None:
    keyring.set_password(_SERVICE_NAME, provider_id, key)


def get_api_key(provider_id: str) -> str | None:
    try:
        val = keyring.get_password(_SERVICE_NAME, provider_id)
        if val is not None:
            return val
        # Check legacy service name and migrate if found
        legacy_val = keyring.get_password(_LEGACY_SERVICE_NAME, provider_id)
        if legacy_val is not None:
            set_api_key(provider_id, legacy_val)
            return legacy_val
        return None
    except keyring.errors.KeyringError:
        return None


def delete_api_key(provider_id: str) -> None:
    try:
        keyring.delete_password(_SERVICE_NAME, provider_id)
    except keyring.errors.PasswordDeleteError:
        pass
    try:
        keyring.delete_password(_LEGACY_SERVICE_NAME, provider_id)
    except keyring.errors.PasswordDeleteError:
        pass
