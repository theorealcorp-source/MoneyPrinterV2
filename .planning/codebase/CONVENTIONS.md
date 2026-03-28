# Coding Conventions

_Last updated: 2026-03-28_

## Summary

MoneyPrinterV2 is a Python 3.12 CLI codebase with no enforced linter or formatter — no `.eslintrc`, `pyproject.toml`, `setup.cfg`, or `pytest.ini` is present. Conventions are applied inconsistently: newer modules (e.g., `src/classes/PostBridge.py`, `src/post_bridge_integration.py`) follow modern Python style with explicit imports and type hints, while older modules (e.g., `src/main.py`, `src/classes/YouTube.py`) use wildcard imports and bare `except Exception` broadly. All terminal output is funnelled through `src/status.py`, and all config access goes through getter functions in `src/config.py`.

---

## Naming Patterns

**Files:**
- Modules: `snake_case.py` — e.g., `src/cache.py`, `src/llm_provider.py`, `src/post_bridge_integration.py`
- Classes: `PascalCase.py` inside `src/classes/` — e.g., `YouTube.py`, `PostBridge.py`, `Twitter.py`
- `src/research/` subpackage uses `snake_case.py` (e.g., `collectors.py`, `scoring.py`)

**Functions:**
- `snake_case` throughout — e.g., `get_verbose()`, `generate_text()`, `rem_temp_files()`
- Private helpers prefixed with `_` — e.g., `_load_config()`, `_deep_merge()`, `_request_json()`, `_build_http_error()`

**Classes:**
- `PascalCase` — e.g., `YouTube`, `PostBridge`, `PostBridgeClientError`, `PipelineTracker`

**Variables:**
- `snake_case` — e.g., `account_id`, `video_path`, `llm_provider`
- Module-level constants: `UPPER_SNAKE_CASE` — e.g., `ROOT_DIR`, `CONFIG_PATH`, `RETRYABLE_STATUS_CODES`, `SUPPORTED_PROVIDERS`

**Config getter naming:**
- All getters in `src/config.py` follow the pattern `get_<thing>()` — e.g., `get_verbose()`, `get_llm_model()`, `get_post_bridge_config()`

---

## Import Style

**Two distinct patterns exist in the codebase — old modules use wildcard imports, newer modules use explicit imports.**

**Older pattern (wildcard) — found in `src/main.py`, `src/classes/YouTube.py`, `src/utils.py`, `src/classes/Twitter.py`, `src/classes/AFM.py`, `src/cron.py`:**
```python
from status import *
from config import *
from cache import *
from utils import *
from constants import *
```

**Newer pattern (explicit) — found in `src/post_bridge_integration.py`, `src/llm_provider.py`, `src/managed_pipeline.py`, `src/research/pipeline.py`:**
```python
from config import get_post_bridge_config
from status import info, question, success, warning
from classes.PostBridge import PostBridge, PostBridgeClientError
```

**Use the explicit import pattern for all new code.** Wildcard imports are a legacy holdover.

**sys.path manipulation:**
- `src/` is added to `sys.path` at entry points (`src/main.py`, `src/cron.py`) and in test files so that all imports use bare module names (e.g., `from config import` not `from src.config import`).
- Test files each manually prepend `SRC_DIR` to `sys.path` before importing:
```python
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
```

---

## Output / Logging

**All terminal output must go through `src/status.py`.** Never use `print()` directly in new code (existing legacy code has scattered `print()` calls inside `src/main.py`).

The five functions in `src/status.py`:
```python
from status import info, success, warning, error, question

info("Collecting signals...")        # magenta, ℹ️
success("Upload complete.")          # green, ✅
warning("No accounts found.")        # yellow, ⚠️
error("Upload failed: ...")          # red, ❌
user_input = question("Continue?")   # magenta, ❓ — wraps input()
```

All accept `show_emoji: bool = True` as a second argument. Pass `show_emoji=False` when formatting numeric or list output where the emoji would be confusing:
```python
info(f' "account_ids": {resolved_account_ids}', False)
```

**There is no structured logging framework** (no `logging` module, no log levels, no log files). All output is ephemeral to the terminal.

---

## Configuration Access Pattern

**Every config value is accessed through a dedicated getter in `src/config.py`.** Never read `config.json` directly outside that module.

Each getter calls the private `_load_config()` on every invocation — there is no in-process caching:
```python
def get_verbose() -> bool:
    return _load_config()["verbose"]

def get_llm_model() -> str:
    config_json = _load_config()
    configured_model = str(config_json.get("llm_model", "")).strip()
    ...
```

**Config + env var fallback pattern** — used for secrets and API keys. Check config first, fall back to environment variable:
```python
def get_openai_api_key() -> str:
    configured = str(_load_config().get("openai_api_key", "")).strip()
    return configured or os.environ.get("OPENAI_API_KEY", "")
```
This pattern is used for: `get_openai_api_key()`, `get_nanobanana2_api_key()`, `get_elevenlabs_api_key()`, and `get_post_bridge_config()` (via `POST_BRIDGE_API_KEY`).

**`ROOT_DIR` is computed once at module load:**
```python
ROOT_DIR = os.path.dirname(sys.path[0])
```
It is imported directly from `config` by other modules: `from config import ROOT_DIR`.

---

## Error Handling

**Two distinct approaches coexist:**

**1. Bare `except Exception as e` with status output (old pattern)** — found throughout `src/utils.py`, `src/classes/YouTube.py`, `src/classes/Outreach.py`:
```python
try:
    info(" => Fetching songs...")
    ...
    success(" => Downloaded Songs.")
except Exception as e:
    error(f"Error occurred while fetching songs: {str(e)}")
```
These swallow exceptions silently in some cases (only printing). `choose_random_song()` in `src/utils.py` is an exception — it re-raises after logging.

**2. Custom exception class + let it propagate (newer pattern)** — used in `src/classes/PostBridge.py` and `src/post_bridge_integration.py`:
```python
class PostBridgeClientError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code

# Caller catches specifically:
try:
    ...
except PostBridgeClientError as exc:
    warning(f"Post Bridge cross-post failed: {exc}")
    return False
```

**For new code, use the newer pattern:** raise specific exceptions, catch specifically, and let unexpected errors propagate to the top-level handler.

**`managed_pipeline.py` wraps the entire pipeline run:**
```python
try:
    ...
    resolved_tracker.mark_completed(output_path=youtube.video_path)
    return resolved_tracker
except Exception as exc:
    resolved_tracker.mark_failed(str(exc))
    raise
```
This is the correct approach — record failure state but re-raise so the caller can observe the error.

---

## Type Hints

**Newer modules are fully typed; older modules have none.**

- Fully typed: `src/classes/PostBridge.py`, `src/post_bridge_integration.py`, `src/config.py`, `src/llm_provider.py`, `src/cache.py`, `src/pipeline_tracker.py`, `src/managed_pipeline.py`
- Untyped: `src/classes/YouTube.py` (partially), `src/classes/Twitter.py`, `src/classes/AFM.py`, `src/classes/Outreach.py`

**Return type annotation style:**
```python
def get_verbose() -> bool:
def list_social_accounts(self, platforms: Optional[Sequence[str]] = None, limit: int = 100) -> list[dict]:
def maybe_crosspost_youtube_short(...) -> Optional[bool]:
```
Uses built-in generics (`list[dict]`, `dict[str, Any]`) not `typing.List`/`typing.Dict` — Python 3.9+ style.

**Docstring style:** Google-style docstrings with explicit `Args:` and `Returns:` sections are used on most functions in the newer modules:
```python
def upload_media(self, file_path: str) -> str:
    """
    Upload a local media file to Post Bridge and return its media ID.

    Args:
        file_path (str): Absolute path to a local media file.

    Returns:
        media_id (str): Uploaded media ID.
    """
```

---

## Data Storage Idioms

**Cache reads/writes always go through `src/cache.py`.** The pattern is: read full list → mutate → write full list back (no partial updates):
```python
accounts = get_accounts(provider)
accounts.append(account)
with open(cache_path, 'w') as file:
    json.dump({"accounts": accounts}, file, indent=4)
```

**File opens use explicit `encoding="utf-8"` in newer code** (`src/config.py`). Older `src/cache.py` omits encoding on file opens — a minor inconsistency.

---

## Module-Level State

**`src/llm_provider.py` holds mutable module-level state** for the selected provider/model:
```python
_selected_provider: str | None = None
_selected_model: str | None = None
```
Set via `select_provider_model(provider, model)` before any `generate_text()` call. This is a process-wide singleton; there is no per-request override except via function arguments.

---

## Common Idioms

**Retry loop with back-off (PostBridge client):**
```python
for attempt in range(1, self._max_retries + 1):
    try:
        response = self._session.request(...)
    except requests.RequestException as exc:
        last_exception = exc
        if attempt == self._max_retries:
            break
        time.sleep(0.5 * attempt)
        continue
    if response.status_code in self.RETRYABLE_STATUS_CODES and attempt < self._max_retries:
        time.sleep(0.5 * attempt)
        continue
    raise PostBridgeClientError(...)
```

**MoviePy v1/v2 compatibility shims** — `src/classes/YouTube.py` detects the installed version at import time and defines wrapper functions:
```python
try:
    from moviepy.editor import ...
    MOVIEPY_V2 = False
except ModuleNotFoundError:
    from moviepy import ...
    MOVIEPY_V2 = True
```
Then all clip method calls go through private helpers like `_clip_with_fps()`, `_clip_resize()`, `_clip_with_audio()`.

**`setdefault` for grouping:** Used in `src/post_bridge_integration.py` to build platform-keyed dicts:
```python
accounts_by_platform.setdefault(platform, []).append(account)
```
