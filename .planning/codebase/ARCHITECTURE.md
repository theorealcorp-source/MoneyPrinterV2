# Architecture
_Last updated: 2026-03-28_

## Summary

MoneyPrinterV2 is a Python 3.12 CLI automation tool organized around four independent workflow pipelines (YouTube Shorts, Twitter Bot, Affiliate Marketing, Outreach), plus newer supporting systems (Research Pipeline, Dashboard, Post Bridge cross-posting). All pipelines share a common config layer, a JSON file cache for accounts, and a SQLite database for pipeline run tracking. There is no web API layer; the only HTTP server is the optional Flask dashboard launched as a subprocess.

---

## Overall Pattern

**Workflow-per-class with a shared service layer.** Each automation workflow is encapsulated in a class under `src/classes/`. These classes consume shared services (LLM generation, TTS synthesis, config reads, JSON cache) but are otherwise independent. The main entry point (`src/main.py`) is a top-level interactive menu loop that instantiates the right class based on user input.

---

## Entry Points

**Interactive menu (`src/main.py`):**
- Launched directly: `python src/main.py`
- Adds `src/` to `sys.path` at startup, so all internal imports use bare module names (e.g., `from config import *`)
- Calls `init_db()`, `assert_folder_structure()`, `rem_temp_files()`, and `fetch_songs()` before entering the menu loop
- Prompts for Ollama model selection if no model is configured
- Dispatches to workflow classes based on integer menu selection

**Headless cron runner (`src/cron.py`):**
- Invoked as a subprocess by the scheduler: `python src/cron.py <platform> <account_uuid> <model> <provider>`
- Does not re-enter the menu; calls `execute_youtube_run()` or `Twitter.post()` directly
- Accepts LLM provider/model as CLI args (passed from the parent process at job registration time)

**Flask dashboard (`src/dashboard.py`):**
- Launched as a subprocess via `subprocess.Popen([sys.executable, "src/dashboard.py"])` from `main.py`
- Serves `src/templates/dashboard.html` via Flask's `render_template`
- Exposes REST-style form-POST routes for config edits, account CRUD, and async YouTube run triggering
- Calls `start_youtube_run_async()` which spawns a `threading.Thread` for each pipeline run

---

## Core Components

**`src/config.py` — Configuration layer**
- `ROOT_DIR` = `os.path.dirname(sys.path[0])` (always project root regardless of invocation path)
- `CONFIG_PATH` = `ROOT_DIR/config.json`
- Every getter function calls `_load_config()` on each invocation — no module-level caching
- `_load_config()` deep-merges `config.example.json` (defaults) over `config.json` (user values), so missing keys always fall back to example values
- `update_config(updates: dict)` performs a partial in-place update to `config.json`
- Key getters: `get_llm_provider()`, `get_llm_model()`, `get_tts_provider()`, `get_post_bridge_config()`, `get_imagemagick_path()`, `get_nanobanana2_api_key()`

**`src/cache.py` — JSON file persistence**
- Stores account lists and AFM products in `.mp/` as `youtube.json`, `twitter.json`, `afm.json`
- CRUD: `get_accounts(provider)`, `add_account(provider, data)`, `update_account(provider, id, updates)`, `remove_account(provider, id)`
- Products: `get_products()`, `add_product(product)`
- No locking; concurrent access from cron subprocesses is not safe

**`src/database.py` — SQLite persistence**
- DB path: `.mp/mpv2.db`
- Tables: `topic_candidate`, `approval_decision`, `published_asset`, `performance_outcome`, `pipeline_run`, `pipeline_step`
- `init_db()` is idempotent — safe to call on every startup; applies `_migrate()` for additive schema changes
- `get_connection()` returns a `sqlite3.Connection` with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`

**`src/llm_provider.py` — Unified LLM dispatch**
- Module-level state: `_selected_provider` and `_selected_model` (set once at startup via `select_provider_model()`)
- `generate_text(prompt)` dispatches to `_generate_with_ollama()`, `_generate_with_openai()`, or `_generate_with_gemini()` based on selected provider
- Supported providers: `ollama`, `openai`, `gemini`
- OpenAI calls use raw `requests.post` to the configured base URL (supports local proxies)

**`src/classes/YouTube.py` — Full video production pipeline**
- Most complex class (~1,000 lines)
- Constructor takes: `account_uuid`, `account_nickname`, `fp_profile_path`, `niche`, `language`
- `generate_video(tts, production_request=None, tracker=None)` orchestrates all steps:
  1. Topic generation (LLM)
  2. Script generation (LLM)
  3. Metadata generation: title, description, tags (LLM)
  4. Image prompt generation (LLM)
  5. Image generation via Nano Banana 2 (Gemini image API)
  6. TTS synthesis via `TTS.synthesize()` → WAV file in `.mp/`
  7. Subtitle generation via AssemblyAI or local Whisper → SRT file
  8. MoviePy composition: images + TTS audio + background music + subtitle overlay → MP4
- `upload_video(tracker=None)` uploads via Selenium to YouTube Studio
- Supports `ProductionRequest` injection to bypass internal topic/script generation
- Each step is wrapped in `_execute_tracked_step()` which calls `PipelineTracker` start/complete/fail

**`src/classes/Twitter.py` — Twitter Selenium automation**
- `post()` generates a tweet via LLM then posts via Selenium against x.com
- Uses pre-authenticated Firefox profiles; never handles login flow
- Selenium selectors live in `src/constants.py` (`TWITTER_TEXTAREA_CLASS`, `TWITTER_POST_BUTTON_XPATH`)

**`src/classes/AFM.py` — Affiliate Marketing**
- `generate_pitch()` scrapes Amazon product page via Selenium, extracts title and bullet points, generates pitch via LLM
- `share_pitch(platform)` posts the pitch to the specified platform

**`src/classes/Outreach.py` — Local business outreach**
- Invokes a Go binary to scrape Google Maps for business emails
- Sends cold outreach emails via yagmail (SMTP)

**`src/classes/Tts.py` — TTS facade**
- Thin wrapper over `src/tts_providers.py`; keeps call sites stable while provider is swappable
- `TTS(provider_name=None)` calls `build_tts_provider()` which reads `get_tts_provider()` from config
- `synthesize(text, output_file)` delegates to the active provider

**`src/tts_providers.py` — TTS provider implementations**
- `BaseTTSProvider` abstract base with `synthesize(text, output_file) -> str`
- `ChatterboxProvider` — local voice cloning using Chatterbox; model loaded once into `_CHATTERBOX_MODEL` global
- `ElevenLabsProvider` — cloud TTS via ElevenLabs HTTP API
- `build_tts_provider(name=None)` factory function; defaults to `get_tts_provider()` config value

**`src/classes/PostBridge.py` — Post Bridge API client**
- `PostBridge(api_key)` wraps the Post Bridge REST API
- `list_social_accounts(platforms, limit)` — paginated fetch
- `upload_media(file_path)` — signed-URL media upload
- `create_post(caption, social_account_ids, media_ids, platform_configurations)` — create cross-post
- Auto-retries on HTTP 429/5xx up to `max_retries` (default 3) with exponential backoff

**`src/post_bridge_integration.py` — Cross-posting orchestration**
- `maybe_crosspost_youtube_short(video_path, title, interactive)` — entry point called after successful YouTube upload
- Reads Post Bridge config, resolves social account IDs, uploads media, creates post
- In interactive mode: may prompt user; respects `auto_crosspost` flag
- In cron mode: only posts if `auto_crosspost = true`

**`src/managed_pipeline.py` — Pipeline execution facade**
- `execute_youtube_run(account, production_request, upload, crosspost, trigger_source, tracker)` — synchronous full pipeline run used by cron
- `start_youtube_run_async(account_id, ...)` — wraps `execute_youtube_run` in a `threading.Thread`; used by dashboard
- Thread registry `_RUN_THREADS: dict[int, Thread]` tracks active threads by run ID

**`src/pipeline_tracker.py` — Run persistence**
- `PipelineTracker` wraps a `pipeline_run` DB row by `run_id`
- States: `queued → running → completed | failed`
- Step tracking via `pipeline_step` table: `start_step()`, `complete_step()`, `fail_step()`
- `get_recent_runs()`, `get_run_details()`, `get_dashboard_snapshot()` — read queries for dashboard

**`src/research/` — Topic research pipeline**
- `research/collectors.py` — `collect_youtube_signals()` (YouTube Data API v3) and `collect_rss_signals()` (Philippine RSS feeds); both return `list[RawSignal]`
- `research/scoring.py` — 7-factor scoring model; grades topics A/B/C; `get_shortlist(scored, n=10)` returns top candidates
- `research/approval.py` — CLI approval queue; saves shortlist to `topic_candidate` table; returns approved/rejected/deferred splits
- `research/pipeline.py` — `run_research_pipeline(keywords, quota_budget)` orchestrates the full flow end-to-end

**`src/production_request.py` — Topic injection contract**
- `ProductionRequest` dataclass: fields for `subject`, `keyword`, `working_title`, `content_angle`, `niche_grade`, `language`, `script`, `title`, `description`, `image_prompts`, `metadata`
- `from_dict(payload)` and `from_file(file_path)` constructors
- `prompt_context()` builds a formatted string injected into LLM prompts

---

## Data Flow

**YouTube Shorts production (interactive):**
```
main.py (menu option 1)
  → YouTube.__init__(account)
  → YouTube.generate_video(TTS, tracker=PipelineTracker)
      → generate_text(topic_prompt)        [llm_provider.py]
      → generate_text(script_prompt)       [llm_provider.py]
      → generate_text(metadata_prompt)     [llm_provider.py]
      → generate_text(image_prompt)        [llm_provider.py]
      → requests.post(nanobanana2_api)     [image generation]
      → TTS.synthesize(script) → .mp/audio.wav
      → AssemblyAI/Whisper → .mp/audio.srt
      → MoviePy composite → .mp/<uuid>.mp4
  → YouTube.upload_video()                 [Selenium → YouTube Studio]
  → maybe_crosspost_youtube_short()        [post_bridge_integration.py]
      → PostBridge.upload_media()
      → PostBridge.create_post()
```

**YouTube Shorts production (cron):**
```
schedule (in-process) → subprocess.run("python src/cron.py youtube <id> <model> <provider>")
  → cron.py → execute_youtube_run(account, upload=True, crosspost=True)
      → [same pipeline as interactive, skipping interactive prompts]
```

**Research → Production:**
```
main.py (menu option 5)
  → run_research_pipeline(keywords, quota_budget)
      → collect_youtube_signals() + collect_rss_signals()
      → score_signals() → get_shortlist()
      → save_candidates_to_db() → topic_candidate table
      → run_approval_queue()   [CLI prompts]
          → approved topics → topic_candidate.status = 'approved'

[Future / dashboard flow]
  → get_approved_topics_for_production() → list[ProductionRequest]
  → execute_youtube_run(account, production_request=req)
```

---

## Scheduling

Uses Python's `schedule` library run in-process inside the `main.py` event loop. The `schedule.run_pending()` loop is not shown in the menu dispatch code; scheduled jobs are registered but the loop is expected to be running in the background while the user interacts with menus. Each scheduled job calls `subprocess.run(["python", "src/cron.py", platform, account_id, model, provider])`.

---

## Error Handling

- No centralized exception handling; each workflow class catches and logs errors locally using `status.py` helpers (`error()`, `warning()`)
- `PipelineTracker.mark_failed(str(exc))` is called in `try/except` blocks in `execute_youtube_run()` and `managed_pipeline.py`
- Selenium failures propagate as uncaught exceptions, surfaced as terminal output
- `PostBridgeClientError` is caught in `post_bridge_integration.py` and logged as a warning (cross-post failure is non-fatal)

---

## Cross-Cutting Concerns

**Logging:** `src/status.py` provides colored terminal output helpers — `info()`, `warning()`, `error()`, `success()`, `question()`. No structured logging or log files.

**Config access:** All modules import `from config import *` or specific getters. Config is re-read from disk on every getter call.

**Import convention:** Bare module names (e.g., `from cache import *`) because `src/` is on `sys.path`. This means the project must always be launched from project root.

**Temp file cleanup:** `rem_temp_files()` deletes all non-`.json`/`.db` files from `.mp/` on each run start. WAV, PNG, SRT, MP4 scratch files accumulate during a run and are wiped on the next run.
