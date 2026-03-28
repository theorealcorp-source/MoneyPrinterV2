from typing import Any

import requests

try:
    import ollama
except ModuleNotFoundError:  # pragma: no cover - optional in tests
    ollama = None

from config import get_gemini_api_base_url
from config import get_gemini_api_key
from config import get_gemini_model
from config import get_llm_model
from config import get_llm_provider
from config import get_ollama_base_url
from config import get_openai_api_key
from config import get_openai_base_url

SUPPORTED_PROVIDERS = {"ollama", "lmstudio", "openai", "gemini"}

_selected_provider: str | None = None
_selected_model: str | None = None


def _normalize_provider(provider_name: str | None) -> str:
    provider = str(provider_name or _selected_provider or get_llm_provider()).strip().lower()
    return provider if provider in SUPPORTED_PROVIDERS else "ollama"


def _ollama_client() -> Any:
    if ollama is None:
        raise RuntimeError("ollama is not installed in this environment.")
    return ollama.Client(host=get_ollama_base_url())


def _openai_compatible_headers(provider_name: str) -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = get_openai_api_key()

    if api_key or provider_name == "lmstudio":
        headers["Authorization"] = f"Bearer {api_key or 'lm-studio'}"

    return headers


def _extract_openai_message(body: dict) -> str:
    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("LLM response did not contain any choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        content = "\n".join(part for part in text_parts if part)

    if not content:
        content = choices[0].get("text", "")

    return str(content).strip()


def _generate_ollama_text(prompt: str, model: str) -> str:
    response = _ollama_client().chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def _generate_openai_compatible_text(prompt: str, model: str, provider_name: str) -> str:
    response = requests.post(
        f"{get_openai_base_url().rstrip('/')}/chat/completions",
        headers=_openai_compatible_headers(provider_name),
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        },
        timeout=180,
    )
    response.raise_for_status()
    return _extract_openai_message(response.json())


def _generate_gemini_text(prompt: str, model: str) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")

    endpoint = f"{get_gemini_api_base_url().rstrip('/')}/models/{model}:generateContent"
    response = requests.post(
        endpoint,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        },
        timeout=180,
    )
    response.raise_for_status()
    body = response.json()

    texts = []
    for candidate in body.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                texts.append(str(text))

    if not texts:
        raise RuntimeError("Gemini response did not contain text output.")

    return "\n".join(texts).strip()


def list_models(provider_name: str = None) -> list[str]:
    """
    Lists models available for the selected provider.

    Args:
        provider_name (str | None): Optional provider override

    Returns:
        models (list[str]): Sorted model identifiers
    """
    provider = _normalize_provider(provider_name)

    if provider == "ollama":
        response = _ollama_client().list()
        return sorted(m.model for m in response.models)

    if provider in {"lmstudio", "openai"}:
        response = requests.get(
            f"{get_openai_base_url().rstrip('/')}/models",
            headers=_openai_compatible_headers(provider),
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        models = [
            str(model.get("id", "")).strip()
            for model in body.get("data", [])
            if str(model.get("id", "")).strip()
        ]
        return sorted(models)

    if provider == "gemini":
        return [get_gemini_model()]

    return []


def select_provider(provider_name: str) -> None:
    """
    Sets the provider for subsequent generate_text calls.

    Args:
        provider_name (str): Provider identifier
    """
    global _selected_provider
    global _selected_model

    normalized_provider = _normalize_provider(provider_name)
    if _selected_provider != normalized_provider:
        _selected_model = None

    _selected_provider = normalized_provider


def select_model(model: str) -> None:
    """
    Sets the model to use for all subsequent generate_text calls.

    Args:
        model (str): Model identifier
    """
    global _selected_model
    _selected_model = str(model).strip()


def select_provider_model(provider_name: str, model: str) -> None:
    """
    Sets both provider and model for future calls.

    Args:
        provider_name (str): Provider identifier
        model (str): Model identifier
    """
    select_provider(provider_name)
    select_model(model)


def get_active_provider() -> str:
    """
    Returns the currently selected provider.
    """
    return _normalize_provider(None)


def get_active_model() -> str | None:
    """
    Returns the currently selected model, or a configured fallback.
    """
    return _selected_model or get_llm_model() or None


def ensure_model_selected(provider_name: str = None) -> str:
    """
    Resolve the active model for non-interactive flows.

    Args:
        provider_name (str | None): Optional provider override

    Returns:
        model (str): Selected or configured model name
    """
    global _selected_provider
    global _selected_model

    provider = _normalize_provider(provider_name)
    _selected_provider = provider

    if _selected_model:
        return _selected_model

    configured_model = get_llm_model()
    if configured_model:
        _selected_model = configured_model
        return _selected_model

    try:
        models = list_models(provider)
    except Exception as exc:
        if provider == "ollama":
            raise RuntimeError(
                "Ollama is not reachable. Start Ollama and set ollama_model in config.json."
            ) from exc
        if provider == "lmstudio":
            raise RuntimeError(
                "LM Studio local server is not reachable. Start the local server and set llm_model in config.json."
            ) from exc
        if provider == "openai":
            raise RuntimeError(
                "OpenAI-compatible API is not reachable. Check openai_base_url, openai_api_key and llm_model."
            ) from exc
        raise RuntimeError(
            "Gemini is not reachable. Check gemini_api_key and gemini_model."
        ) from exc

    if len(models) == 0:
        if provider == "ollama":
            raise RuntimeError(
                "No Ollama models are available. Pull a model and set ollama_model in config.json."
            )
        raise RuntimeError(
            f"No models were returned for provider '{provider}'. Set llm_model in config.json."
        )

    if len(models) == 1:
        _selected_model = models[0]
        return _selected_model

    raise RuntimeError(
        f"No model selected for provider '{provider}'. Set llm_model in config.json."
    )


def generate_text(prompt: str, model_name: str = None, provider_name: str = None) -> str:
    """
    Generates text using the configured provider.

    Args:
        prompt (str): User prompt
        model_name (str | None): Optional model override
        provider_name (str | None): Optional provider override

    Returns:
        response (str): Generated text
    """
    provider = _normalize_provider(provider_name)
    model = str(model_name or ensure_model_selected(provider)).strip()

    if provider == "ollama":
        return _generate_ollama_text(prompt, model)
    if provider in {"lmstudio", "openai"}:
        return _generate_openai_compatible_text(prompt, model, provider)
    if provider == "gemini":
        return _generate_gemini_text(prompt, model)

    raise RuntimeError(f"Unsupported LLM provider '{provider}'.")
