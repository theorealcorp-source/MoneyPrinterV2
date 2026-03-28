# Codebase Structure
_Last updated: 2026-03-28_

## Summary

All application code lives under `src/`. Workflow classes are grouped in `src/classes/`. New subsystems (research pipeline, dashboard) are either top-level modules in `src/` or in a subdirectory (`src/research/`). Static assets, background music, and fonts live in top-level directories. Persistent state is stored entirely in `.mp/` (JSON files and SQLite DB).

---

## Directory Layout

```
MoneyPrinterV2/
├── src/                        # All application source code
│   ├── classes/                # One class per automation workflow
│   │   ├── YouTube.py          # Full Shorts production + Selenium upload
│   │   ├── Twitter.py          # Twitter Selenium automation
│   │   ├── AFM.py              # Affiliate marketing scraper + pitch generation
│   │   ├── Outreach.py         # Google Maps scraper + email outreach
│   │   ├── Tts.py              # TTS facade (delegates to tts_providers.py)
│   │   └── PostBridge.py       # Post Bridge REST API client
│   ├── research/               # Topic research subsystem
│   │   ├── __init__.py
│   │   ├── collectors.py       # YouTube Data API + RSS signal collection
│   │   ├── scoring.py          # 7-factor topic scoring and grading
│   │   ├── approval.py         # CLI approval queue + DB persistence
│   │   └── pipeline.py         # Top-level orchestrator for research flow
│   ├── templates/
│   │   └── dashboard.html      # Single-file Flask dashboard template
│   ├── main.py                 # Interactive CLI menu entry point
│   ├── cron.py                 # Headless cron runner entry point
│   ├── dashboard.py            # Flask dashboard server (launched as subprocess)
│   ├── config.py               # All config getters; reads config.json on every call
│   ├── cache.py                # JSON-file CRUD for accounts and AFM products
│   ├── database.py             # SQLite schema, migrations, connection factory
│   ├── llm_provider.py         # Unified LLM dispatch (Ollama / OpenAI / Gemini)
│   ├── tts_providers.py        # TTS provider implementations (Chatterbox, ElevenLabs)
│   ├── managed_pipeline.py     # Synchronous + async YouTube pipeline execution
│   ├── pipeline_tracker.py     # Pipeline run + step persistence via SQLite
│   ├── post_bridge_integration.py  # Cross-post orchestration after YouTube upload
│   ├── production_request.py   # ProductionRequest dataclass (topic injection contract)
│   ├── constants.py            # Menu strings, Selenium selectors, research keywords
│   ├── status.py               # Colored terminal output helpers
│   ├── utils.py                # rem_temp_files, fetch_songs, Selenium teardown
│   ├── art.py                  # ASCII banner printer
│   ├── youtube_auth.py         # YouTube OAuth helper (standalone util)
│   └── produce_youtube.py      # Thin CLI shim for single-shot YouTube production
├── tests/                      # Test suite (Post Bridge integration only)
│   ├── test_post_bridge_client.py
│   ├── test_post_bridge_integration.py
│   ├── test_cron_post_bridge.py
│   └── test_config.py
├── scripts/                    # Setup and validation scripts
│   ├── setup_local.sh          # macOS first-time setup (Ollama, ImageMagick, Firefox)
│   ├── preflight_local.py      # Service reachability checks
│   └── upload_video.sh         # Standalone video upload shell script
├── assets/                     # Static assets (images, etc.)
├── fonts/                      # Font files used by MoviePy subtitle rendering
├── Songs/                      # Background music MP3s (downloaded at startup)
├── .mp/                        # Runtime state directory (gitignored)
│   ├── youtube.json            # YouTube account cache
│   ├── twitter.json            # Twitter account cache
│   ├── afm.json                # AFM products cache
│   ├── mpv2.db                 # SQLite database
│   ├── previews/               # Video preview files for dashboard
│   └── *.wav / *.png / *.srt / *.mp4  # Scratch files (wiped on each run start)
├── docs/                       # Documentation files
├── config.json                 # User-specific config (gitignored)
├── config.example.json         # Config template and default values (committed)
├── requirements.txt            # Python dependencies
├── .python-version             # Python version pin (3.12)
├── CLAUDE.md                   # Claude Code guidance
└── test_pipeline.py            # Ad-hoc pipeline smoke test (project root)
```

---

## Key Files and Their Roles

| File | Role |
|------|------|
| `src/main.py` | Primary entry point; interactive menu loop; initializes all shared services |
| `src/cron.py` | Headless entry point; receives platform + account ID + model as CLI args |
| `src/dashboard.py` | Flask HTTP server; manages accounts and triggers async runs via browser UI |
| `src/config.py` | Single source of truth for all configuration values; 30+ getter functions |
| `src/cache.py` | Read/write for account and product JSON files in `.mp/` |
| `src/database.py` | SQLite schema definition, `init_db()`, `get_connection()` |
| `src/llm_provider.py` | `generate_text(prompt)` — the only LLM call site used by all other modules |
| `src/tts_providers.py` | `build_tts_provider()` factory; Chatterbox and ElevenLabs implementations |
| `src/classes/YouTube.py` | Full video production pipeline + Selenium upload; ~1,000 lines |
| `src/managed_pipeline.py` | `execute_youtube_run()` (sync) and `start_youtube_run_async()` (threaded) |
| `src/pipeline_tracker.py` | `PipelineTracker` class + dashboard query functions |
| `src/production_request.py` | `ProductionRequest` dataclass — the contract for injecting approved topics |
| `src/post_bridge_integration.py` | `maybe_crosspost_youtube_short()` — called after every successful upload |
| `src/constants.py` | All hardcoded strings: menu options, Selenium XPaths/IDs, research keywords |
| `src/status.py` | `info()`, `warning()`, `error()`, `success()`, `question()` — all terminal output |
| `src/utils.py` | `rem_temp_files()`, `fetch_songs()`, `choose_random_song()`, Selenium teardown |
| `src/research/pipeline.py` | `run_research_pipeline()` — top-level entry for topic discovery |
| `config.example.json` | Default config values; deep-merged under user `config.json` at every read |

---

## Module Organization

**Shared services (imported by everything):**
- `config.py` — via `from config import *` or named imports
- `status.py` — via `from status import *`
- `cache.py` — via `from cache import *`
- `utils.py` — via `from utils import *`
- `constants.py` — via `from constants import *`

**Workflow classes (`src/classes/`):**
- Each class imports shared services at the top of its file
- Classes do not import each other
- The `YouTube` class is the only one that also imports `pipeline_tracker`, `production_request`, and `post_bridge_integration`

**Research subsystem (`src/research/`):**
- Has its own `__init__.py`; imported lazily in `main.py` (`from research.pipeline import run_research_pipeline`)
- `collectors.py` → `scoring.py` → `approval.py` → `pipeline.py` (linear dependency chain)
- All modules import from `database.py`, `constants.py`, and `config.py`

**Dashboard:**
- `dashboard.py` imports from `managed_pipeline`, `pipeline_tracker`, `cache`, `config`, `tts_providers`, `production_request`
- Template lives in `src/templates/dashboard.html`; referenced as `render_template("dashboard.html")` — Flask looks in `src/templates/` relative to `dashboard.py`

---

## Naming Conventions

**Files:**
- Workflow classes: `PascalCase.py` — `YouTube.py`, `Twitter.py`, `PostBridge.py`
- Shared service modules: `snake_case.py` — `config.py`, `cache.py`, `llm_provider.py`, `pipeline_tracker.py`
- Entry points: `snake_case.py` — `main.py`, `cron.py`, `dashboard.py`
- Research submodules: `snake_case.py` — `collectors.py`, `scoring.py`, `approval.py`

**Classes:**
- `PascalCase` — `YouTube`, `Twitter`, `PostBridge`, `PipelineTracker`, `ProductionRequest`
- Provider implementations: `<Name>Provider` — `ChatterboxProvider`, `ElevenLabsProvider`

**Functions:**
- Public: `snake_case` — `generate_text()`, `get_accounts()`, `execute_youtube_run()`
- Private helpers: `_snake_case` — `_load_config()`, `_generate_with_ollama()`, `_build_subtitle_generator()`
- Config getters: `get_<field_name>()` — `get_llm_provider()`, `get_tts_ref_audio()`

**Test files:**
- `test_<module_name>.py` in `tests/` — `test_post_bridge_client.py`, `test_config.py`

---

## Where to Add New Code

**New automation workflow:**
- Implementation class: `src/classes/<WorkflowName>.py`
- Menu option string: add to `OPTIONS` list in `src/constants.py`
- Menu dispatch: add `elif user_input == N:` block in `src/main.py`
- Cron support: add `elif purpose == "<workflow>":` block in `src/cron.py`

**New config option:**
- Add key with default value to `config.example.json`
- Add getter function to `src/config.py` following the `def get_<key>()` pattern

**New LLM provider:**
- Add provider name to `SUPPORTED_PROVIDERS` set in `src/llm_provider.py`
- Add `_generate_with_<provider>()` private function
- Add `elif resolved_provider == "<provider>":` dispatch in `generate_text()`

**New TTS provider:**
- Add a class extending `BaseTTSProvider` in `src/tts_providers.py`
- Add to `SUPPORTED_TTS_PROVIDERS` tuple
- Add `elif name == "<provider>":` branch in `build_tts_provider()`

**New database table:**
- Add `CREATE TABLE IF NOT EXISTS` statement to `_SCHEMA` in `src/database.py`
- Add any index creation to `_migrate()` in `src/database.py`

**New pipeline step tracking:**
- Call `tracker.start_step(step_key, label, order)` before the operation
- Call `tracker.complete_step(step_key)` on success
- Call `tracker.fail_step(step_key, message)` on exception (tracker is optional — always null-check first)

**Tests:**
- Place in `tests/test_<module>.py`
- Run with `python -m pytest tests/`

---

## Special Directories

**`.mp/` (runtime state):**
- Purpose: all persistent and scratch state; JSON caches, SQLite DB, temp media files
- Generated: yes, created by `assert_folder_structure()` on first run
- Committed: no (gitignored); `.mp/previews/` subdirectory also created at runtime

**`Songs/` (background music):**
- Purpose: MP3 files used as background audio in generated videos
- Generated: downloaded at startup by `fetch_songs()` from a configured ZIP URL or Jamendo API
- Committed: no (gitignored); directory is created if missing

**`src/templates/` (Flask templates):**
- Purpose: HTML templates for the dashboard Flask app
- Contains: `dashboard.html` (single file, ~35K lines, self-contained dashboard UI)
- Committed: yes
