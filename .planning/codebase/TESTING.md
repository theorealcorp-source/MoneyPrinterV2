# Testing Patterns

_Last updated: 2026-03-28_

## Summary

Testing coverage is narrow and focused entirely on the Post Bridge cross-posting feature added in the most recent PR. The four test files in `tests/` cover `PostBridge` client behaviour, the `post_bridge_integration` orchestration layer, `config.get_post_bridge_config()` parsing, and the cron entry point's gating logic. The rest of the codebase — YouTube pipeline, Twitter automation, TTS, AFM, Outreach, research pipeline, cache, dashboard — has zero automated test coverage. `test_pipeline.py` in the project root is a manual integration smoke-test script, not a pytest suite.

---

## Test Framework

**Runner:** `pytest` (installed via `requirements.txt`, no version pinned)

**Assertion library:** `unittest.TestCase` assertion methods (`assertEqual`, `assertTrue`, `assertIsNone`, `assert_called_once`, etc.)

**Test class base:** `unittest.TestCase` — all test classes inherit from it and are discovered by pytest.

**Run commands:**
```bash
python -m pytest tests/                                        # Run all tests
python -m pytest tests/test_post_bridge_client.py             # Single file
python -m pytest tests/ -v                                     # Verbose output
```
No `pytest.ini`, `pyproject.toml [tool.pytest]`, or `setup.cfg` exists — pytest runs with all defaults.

---

## Test File Organization

**Location:** All automated tests live in `tests/` at the project root (not co-located with source).

**Naming convention:** `test_<subject>.py`

| File | Subject |
|------|---------|
| `tests/test_post_bridge_client.py` | `src/classes/PostBridge.py` HTTP client behaviour |
| `tests/test_post_bridge_integration.py` | `src/post_bridge_integration.py` orchestration logic |
| `tests/test_config.py` | `src/config.get_post_bridge_config()` parsing edge cases |
| `tests/test_cron_post_bridge.py` | `src/cron.main()` gating — cross-post only runs after successful upload |

**Manual smoke-test (not pytest):**
- `test_pipeline.py` at the project root is a runnable script that executes the full YouTube generation pipeline against a live account. It is NOT collected by pytest and requires configured accounts and external services.

---

## sys.path Setup

Every test file manually bootstraps the import path before importing `src/` modules. This is required because `src/` is not a package on `sys.path` by default:

```python
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
```

This block appears identically in all four test files.

---

## Test Structure

All test classes use `unittest.TestCase` with pytest as the runner:

```python
class PostBridgeClientTests(unittest.TestCase):
    @patch("classes.PostBridge.time.sleep")
    def test_create_post_retries_after_rate_limit(self, sleep_mock) -> None:
        session = Mock()
        session.request.side_effect = [
            MockResponse(429, {"message": "Too many requests"}),
            MockResponse(200, {"id": "post-123", "status": "processing"}),
        ]
        client = PostBridge("token", session=session)
        response = client.create_post(...)
        self.assertEqual(response["id"], "post-123")
        sleep_mock.assert_called_once()

if __name__ == "__main__":
    unittest.main()
```

No `setUp` / `tearDown` methods are used. Each test method is self-contained.

---

## Mocking

**Framework:** `unittest.mock` — `Mock`, `patch`, `mock_open` from the standard library.

**Dependency injection for HTTP:** `PostBridge.__init__` accepts an optional `session: requests.Session` parameter, enabling tests to inject a `Mock()` session directly:
```python
session = Mock()
session.request.side_effect = [MockResponse(200, {...}), MockResponse(200, {...})]
client = PostBridge("token", session=session)
```

**Custom `MockResponse` class** (defined in `tests/test_post_bridge_client.py`) simulates `requests.Response`:
```python
class MockResponse:
    def __init__(self, status_code: int, json_data=None, text: str = "") -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data
```

**`@patch` decorator** is used for module-level dependencies:
```python
@patch("post_bridge_integration.PostBridge")
@patch("post_bridge_integration.get_post_bridge_config")
def test_cron_mode_skips_when_auto_crosspost_is_disabled(self, get_config_mock, post_bridge_cls_mock):
    get_config_mock.return_value = {"enabled": True, "api_key": "token", ...}
    ...
```

**Stub modules** for heavy dependencies: `tests/test_cron_post_bridge.py` manually injects fake modules into `sys.modules` before importing `cron`, to avoid importing Selenium, Ollama, and KittenTTS:
```python
fake_kittentts = types.ModuleType("kittentts")
fake_kittentts.KittenTTS = object
sys.modules.setdefault("kittentts", fake_kittentts)
```
This pattern is required because `src/cron.py` imports class modules at the top level.

**`patch.object(config, "ROOT_DIR", temp_dir)`** is used in `tests/test_config.py` to redirect config file reads to a `tempfile.TemporaryDirectory`:
```python
with tempfile.TemporaryDirectory() as temp_dir:
    self.write_config(temp_dir, {"post_bridge": {"enabled": True}})
    with patch.object(config, "ROOT_DIR", temp_dir):
        result = config.get_post_bridge_config()
```

---

## Test Patterns Used

**Behaviour-oriented test names:** Test method names read as sentences describing a specific behaviour:
- `test_list_social_accounts_follows_pagination`
- `test_create_post_retries_after_rate_limit`
- `test_upload_media_does_not_forward_api_bearer_token_to_signed_upload_url`
- `test_cron_mode_skips_when_auto_crosspost_is_disabled`
- `test_non_list_platforms_fail_closed`

**Security-sensitive assertion** — verifying that auth headers are NOT leaked to signed upload URLs:
```python
upload_call = session.request.call_args_list[1]
self.assertEqual(upload_call.args[0], "PUT")
self.assertEqual(upload_call.kwargs["headers"], {"Content-Type": "video/mp4"})
# Implicitly: no Authorization header on the signed upload call
```

**Prompt injection via `prompt_fn` parameter** — `resolve_social_account_ids` and `maybe_crosspost_youtube_short` accept an optional `prompt_fn` callback, allowing tests to inject a `Mock(side_effect=["2"])` to simulate user input without patching `builtins.input`:
```python
prompt = Mock(side_effect=["2"])
account_ids = resolve_social_account_ids(
    client=client, ..., interactive=True, prompt_fn=prompt
)
prompt.assert_called_once()
```

**`tempfile.NamedTemporaryFile`** for real file paths in integration tests:
```python
with tempfile.NamedTemporaryFile(suffix=".mp4") as media_file:
    result = maybe_crosspost_youtube_short(video_path=media_file.name, ...)
```

---

## What Is Tested

| Area | Tested | File |
|------|--------|------|
| `PostBridge` pagination | Yes | `test_post_bridge_client.py` |
| `PostBridge` retry on 429/5xx | Yes | `test_post_bridge_client.py` |
| `PostBridge` signed-URL upload (no auth header leak) | Yes | `test_post_bridge_client.py` |
| `PostBridge` stream rewind on retry | Yes | `test_post_bridge_client.py` |
| `post_bridge_integration` account resolution (interactive) | Yes | `test_post_bridge_integration.py` |
| `post_bridge_integration` non-interactive skip on ambiguous accounts | Yes | `test_post_bridge_integration.py` |
| `post_bridge_integration` cron skip when `auto_crosspost=False` | Yes | `test_post_bridge_integration.py` |
| `post_bridge_integration` full upload+post flow | Yes | `test_post_bridge_integration.py` |
| `config.get_post_bridge_config()` edge cases | Yes | `test_config.py` |
| `cron.main()` cross-post gate on upload failure | Yes | `test_cron_post_bridge.py` |

---

## Coverage Gaps

The following areas have no automated test coverage at all:

**`src/classes/YouTube.py`:**
- Video generation pipeline (topic → script → images → TTS → MoviePy composite)
- `upload_video()` via Selenium
- SRT parsing and subtitle rendering
- MoviePy v1/v2 compatibility shims

**`src/classes/Twitter.py`** — no tests for tweet generation or Selenium posting

**`src/classes/AFM.py`** — no tests for Amazon scraping or LLM pitch generation

**`src/classes/Outreach.py`** — no tests for Google Maps scraping or SMTP email sending

**`src/classes/Tts.py` / `src/tts_providers.py`** — no tests for TTS generation (chatterbox, elevenlabs)

**`src/cache.py`** — no tests for account CRUD operations on JSON cache files

**`src/llm_provider.py`** — no tests for provider dispatch logic (`generate_text`, `select_provider_model`, `list_models`)

**`src/research/` subpackage** — no tests for signal collection, scoring, deduplication, or approval queue

**`src/managed_pipeline.py`** — `execute_youtube_run` and `start_youtube_run_async` are untested

**`src/pipeline_tracker.py`** — SQLite persistence layer is untested

**`src/database.py`** — schema creation is untested

**`src/dashboard.py`** — Flask routes are untested

**`src/config.py`** — only `get_post_bridge_config()` is tested; the 30+ other getters are untested

**`src/main.py`** — interactive menu loop is untested

---

## Running Tests

```bash
# All tests
python -m pytest tests/

# Single file
python -m pytest tests/test_post_bridge_client.py

# Verbose with test names
python -m pytest tests/ -v

# Manual pipeline smoke-test (requires live accounts + services)
python test_pipeline.py
```

No coverage reporting tool is configured. To get a coverage report manually:
```bash
python -m pytest tests/ --cov=src --cov-report=term-missing
```
(requires `pytest-cov` which is not in `requirements.txt`)
