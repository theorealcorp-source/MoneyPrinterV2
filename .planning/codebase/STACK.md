# Technology Stack
_Last updated: 2026-03-28_

## Summary
MoneyPrinterV2 is a Python 3.12+ CLI tool (no web framework for end-users; Flask is used only for an internal dashboard). It has no build step, no linter config, and no CI pipeline. All dependencies are declared in `requirements.txt` and installed into a local `venv/`.

## Language & Runtime

**Primary:**
- Python 3.12+ — all application code under `src/`
- The codebase uses type annotations (`str | None`, `list[str]`) requiring Python 3.10+ union syntax; Python 3.14.3 confirmed in the dev environment

**Secondary:**
- Go — external binary dependency only, required for the Google Maps scraper (`src/classes/Outreach.py` downloads and compiles `google-maps-scraper` at runtime via `subprocess`)

**Package Manager:**
- `pip` with `venv`
- Lockfile: not present (plain `requirements.txt`, no `pip freeze` / `poetry.lock`)

## Frameworks

**Web/Dashboard:**
- Flask — serves the internal pipeline dashboard at `http://127.0.0.1:8787` by default (`src/dashboard.py`)

**Browser Automation:**
- Selenium — drives pre-authenticated Firefox profiles for YouTube Studio, X.com, and Amazon scraping
- `selenium_firefox` — Firefox-specific Selenium helper
- `webdriver_manager` — manages geckodriver installation
- `undetected_chromedriver` — imported but secondary to Firefox

**Video Production:**
- MoviePy — composites images, audio, and subtitles into MP4 (`src/classes/YouTube.py`). Supports both MoviePy v1 (`.editor` import) and v2 API — detected at import time via a `try/except`
- ImageMagick — called by MoviePy for subtitle/text rendering; path configured via `imagemagick_path` in `config.json`
- Pillow >= 10.0.0 — image handling

**Scheduling:**
- `schedule` — in-process cron scheduler (`src/main.py`, `src/cron.py`)

**Data:**
- SQLite (stdlib `sqlite3`) — pipeline tracking DB at `.mp/mpv2.db` (`src/database.py`)
- JSON flat files — account and video cache in `.mp/*.json` (`src/cache.py`)

## Key Dependencies

| Package | Purpose |
|---|---|
| `moviepy` | Video composition pipeline |
| `Pillow>=10.0.0` | Image processing |
| `selenium`, `selenium_firefox`, `webdriver_manager` | Browser automation |
| `undetected_chromedriver` | Anti-bot Chrome automation (secondary) |
| `ollama` | LLM text generation via local Ollama server |
| `google-generativeai` | Gemini API for LLM and image generation |
| `google-api-python-client` | YouTube Data API v3 client |
| `google-auth-oauthlib`, `google-auth-httplib2` | OAuth 2.0 flow for YouTube |
| `requests` | HTTP client used throughout (OpenAI, ElevenLabs, PostBridge) |
| `chatterbox-tts` | Local voice-cloning TTS (`ChatterboxTTS.from_pretrained`) |
| `soundfile` | WAV file writing for Chatterbox output |
| `assemblyai` | Cloud STT transcription |
| `faster-whisper` | Local Whisper STT |
| `srt_equalizer` | SRT subtitle timing normalization |
| `yagmail` | SMTP email sending for Outreach |
| `feedparser` | RSS feed parsing for research pipeline |
| `schedule` | In-process job scheduling |
| `termcolor` | Colored terminal output |
| `prettytable` | Table formatting in CLI menus |
| `Flask` | Internal dashboard web server |
| `platformdirs` | Cross-platform directory resolution |
| `wheel` | Build utility |

## Configuration

**Runtime Config:**
- `config.json` at project root — loaded fresh on every call by `src/config.py` (no caching)
- Template: `config.example.json`; auto-materialized on first run if `config.json` is absent
- Config merges `config.example.json` defaults with user overrides via `_deep_merge()`
- Key external values: `imagemagick_path`, `firefox_profile`, `ollama_base_url`, `nanobanana2_api_key`, `assembly_ai_api_key`, `elevenlabs_api_key`, `openai_api_key`

**Assets:**
- `fonts/` — font files (e.g., `bold_font.ttf`) referenced by MoviePy subtitle rendering
- `Songs/` — local background music files
- `.mp/` — runtime scratch directory: WAV, PNG, SRT, MP4 temp files + `mpv2.db` + JSON cache files

## Dev Tooling

- No linter (no `.eslintrc`, no `pyproject.toml`, no `ruff.toml`, no `mypy.ini`)
- No formatter config
- No CI pipeline
- Test runner: `pytest` — tests in `tests/` cover Post Bridge integration only (`tests/test_post_bridge_client.py`)
- Setup script: `scripts/setup_local.sh` — macOS helper to configure Ollama, ImageMagick, Firefox profile
- Preflight script: `scripts/preflight_local.py` — validates services are reachable before running

## Platform Requirements

**Development:**
- macOS or Linux recommended (`scripts/setup_local.sh` targets macOS)
- Firefox with pre-authenticated profiles for each platform
- Go installed if using Outreach feature
- ffmpeg installed if using ElevenLabs TTS (for MPEG → WAV conversion)
- Ollama server running locally (default `http://127.0.0.1:11434`) for LLM generation
- ImageMagick binary available at configured path

**Production:**
- No containerization, no deployment pipeline — designed to run directly on a developer's machine or a persistent VPS
- Must be launched from project root: `python src/main.py`
