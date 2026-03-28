# CONCERNS
_Last updated: 2026-03-28_

## Summary

MoneyPrinterV2 is a functional automation tool with several architectural and safety concerns that accumulate risk as the codebase grows. The most pressing issues are the widespread use of wildcard imports creating invisible namespace collisions, the JSON flat-file cache having no concurrency protection, and the dashboard having no authentication layer despite accepting config writes and triggering pipeline runs. Most concerns are Medium severity — individually manageable, but compounding under concurrent or unattended operation.

---

## High Severity

### No Authentication on the Web Dashboard

**Issue:** `src/dashboard.py` exposes a Flask app with routes that write `config.json`, add/delete YouTube accounts, trigger video pipeline runs, and serve generated audio previews. There is no session check, API key validation, or IP allowlist on any route.

**Files:** `src/dashboard.py` (lines 84–255), `src/config.py` `update_config()`

**Impact:** Anyone who can reach the dashboard port (default `8787`, configurable) can overwrite credentials, trigger expensive LLM/image-gen jobs, or exfiltrate the full config including API keys. The default host is `127.0.0.1`, which limits exposure on a single machine, but it is trivially changed via config or `--host`.

**Fix approach:** Add a simple shared-secret or bearer-token middleware to Flask before any route handler, or at minimum gate behind an OS-level firewall rule and document the risk clearly.

---

### Wildcard Star Imports Throughout All Modules

**Issue:** Every entry-point and class file uses `from module import *` for `cache`, `config`, `status`, `utils`, `constants`, and `selenium_firefox`. There are 24 occurrences across the codebase.

**Files:** `src/main.py` (lines 7–13), `src/classes/YouTube.py` (lines 9–18), `src/classes/Twitter.py` (lines 7–9), `src/classes/AFM.py` (lines 5–10), `src/classes/Outreach.py` (lines 14–16), `src/utils.py` (lines 7–8), `src/cron.py` (line 4)

**Impact:** Name collisions are silently possible — e.g., a function named `error` or `info` defined in any imported module overwrites another. The namespace of any class is polluted with 30+ config getter functions. Static analysis and auto-complete are degraded. Refactoring any exported name silently breaks callers.

**Fix approach:** Replace star imports with explicit named imports. `config` exports ~35 getter functions; most call sites only need 3–6 of them.

---

## Medium Severity

### JSON Cache Has No Concurrency Protection

**Issue:** `src/cache.py` uses a read-modify-write pattern with plain `open()` calls and no file locking. When the cron scheduler spawns multiple `subprocess.run()` calls, or when the dashboard triggers a run while an interactive run is in progress, two processes can simultaneously read the same `youtube.json` or `twitter.json`, each appending their record, and the slower writer will overwrite the faster one's data.

**Files:** `src/cache.py` (`add_account`, `update_account`, `remove_account`, `add_product` — all lines 94–217), `src/classes/YouTube.py` `add_video()` (lines 651–677), `src/classes/Twitter.py` `add_post()` (lines 172–196)

**Impact:** Silent data loss of uploaded video records or posted tweet records when two runs overlap.

**Fix approach:** Use `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) around the read-modify-write, or migrate all account/video history into the existing SQLite database (`src/database.py`).

---

### Config Re-read on Every Getter Call

**Issue:** Every `get_*()` function in `src/config.py` calls `_load_config()`, which opens and parses `config.json` from disk. A single pipeline run invokes dozens of getters at every step — generating topic, script, metadata, images, TTS, subtitles, and render — resulting in hundreds of redundant file reads per video.

**Files:** `src/config.py` (all `get_*` functions, lines 151–715)

**Impact:** Negligible latency individually, but it means any mid-run manual edit to `config.json` takes effect immediately mid-pipeline, which can produce incoherent behaviour (e.g., the LLM model switching mid-generation).

**Fix approach:** Cache the parsed config in a module-level dict and invalidate only when `save_config()` or `update_config()` is called.

---

### `generate_script` and `generate_metadata` Use Unbounded Recursion for Retry

**Issue:** Both `generate_script()` and `generate_metadata()` in `src/classes/YouTube.py` call themselves recursively with no depth limit when the LLM returns an oversized response.

**Files:** `src/classes/YouTube.py` `generate_script()` (line 389), `generate_metadata()` (line 416)

**Impact:** If the LLM consistently returns long outputs (common with some Ollama models on the default prompt), these methods will recurse until Python hits the stack limit (`RecursionError`) or the process hangs indefinitely.

**Fix approach:** Replace with an explicit `for attempt in range(MAX_RETRIES)` loop, logging a warning and raising after exhaustion.

---

### `generate_prompts` Retries via Recursion and Silently Truncates JSON

**Issue:** `generate_prompts()` in `src/classes/YouTube.py` (lines 479–515) attempts to parse LLM output as JSON, and on failure applies a regex `r"\[.*\]"` to extract any bracket-delimited substring. If that also fails, it recurses. This fragile chain means malformed LLM output can silently produce wrong image prompts, produce fewer images than intended, or recurse indefinitely.

**Files:** `src/classes/YouTube.py` lines 479–515

**Fix approach:** Enforce a maximum retry count; log the raw LLM response when parsing fails; consider using a structured-output mode if the LLM provider supports it.

---

### Selenium Browser Is Never Closed in `AFM` and `Twitter`

**Issue:** `src/classes/AFM.py` initialises `webdriver.Firefox` in `__init__` and exposes a `quit()` method, but `quit()` is never called in normal application flow — neither in `src/main.py` nor after `share_pitch()`. `src/classes/Twitter.py` also never calls `browser.quit()` after posting.

**Files:** `src/classes/AFM.py` (lines 66–176), `src/classes/Twitter.py` (lines 68–141)

**Impact:** Each interactive or cron run leaks a Firefox process. Over time this exhausts system memory. Visible in `.mp` scratch space as orphaned profiles.

**Fix approach:** Call `browser.quit()` in a `finally` block or implement `__del__` / context manager protocol.

---

### Hardcoded YouTube Category ID and Video Privacy

**Issue:** YouTube upload in `src/classes/YouTube.py` (line 1090) hardcodes `"categoryId": "22"` (People & Blogs) and `"privacyStatus": "public"` (line 1094). Neither is exposed in `config.json`.

**Files:** `src/classes/YouTube.py` lines 1089–1096

**Impact:** All videos are permanently public and always filed under one category, regardless of niche. There is no way to upload as `unlisted` or `private` for review without editing source code.

**Fix approach:** Add `youtube_category_id` and `youtube_privacy_status` to `config.json` with the current values as defaults.

---

### `Outreach.start()` Runs Scraper from `os.getcwd()`

**Issue:** `src/classes/Outreach.py` writes `niche.txt` to `os.getcwd()` (line 218), runs the scraper binary from `os.getcwd()` (line 133), and resolves the scraper directory relative to `os.getcwd()` (line 41). The app must be run from project root, but `cron.py` is invoked as a subprocess and inherits whichever cwd the calling process has.

**Files:** `src/classes/Outreach.py` lines 41, 97–98, 133, 218

**Impact:** Outreach feature silently fails if the cwd is not the project root; `niche.txt` and the binary end up in unpredictable locations.

**Fix approach:** Use `ROOT_DIR` (available from `config`) for all paths in `Outreach`, consistent with every other module.

---

### `src/config.json` Is Committed to the Repository

**Issue:** A live `src/config.json` exists at `src/config.json` (a second copy, separate from the root `config.json`). Both are committed in git. The root `config.json` is listed in `.gitignore` per convention, but `src/config.json` may not be. If either contains real API keys, they are exposed in git history.

**Files:** `/Users/theo/ai_playgroud/MoneyPrinterV2/src/config.json`

**Impact:** Potential credential leakage in repository history.

**Fix approach:** Verify `src/config.json` is in `.gitignore` and contains only example/empty values; remove it from tracked files if it has real credentials.

---

### Dashboard Passes Full Config (Including API Keys) to Template Context

**Issue:** `src/dashboard.py` (line 111) passes `config=get_full_config()` directly to the Jinja2 template. The full config includes `openai_api_key`, `elevenlabs_api_key`, `nanobanana2_api_key`, and SMTP credentials. These are rendered into the HTML form and may appear in browser developer tools, proxy logs, or server access logs.

**Files:** `src/dashboard.py` line 111

**Impact:** API keys visible in HTML source to anyone who can view the page.

**Fix approach:** Mask sensitive fields (replace value with `"•••"` in the template context) or pass only non-sensitive fields and handle sensitive fields server-side only.

---

### `add_video` Double-Appends in `YouTube` Cache

**Issue:** `YouTube.add_video()` in `src/classes/YouTube.py` (lines 651–677) first calls `self.get_videos()` to load the existing list, then opens the cache file again and independently appends the new video to the in-file account object. The `videos` list fetched at line 661 is never written back, making the first read a no-op. If multiple videos were written quickly, the logic would still be safe, but the dead read adds confusion and could mask future bugs.

**Files:** `src/classes/YouTube.py` lines 651–677

**Fix approach:** Simplify to a single read-modify-write using `cache.update_account()`.

---

## Low Severity

### Research Pipeline Keywords Are Philippines-Specific by Default

**Issue:** `src/constants.py` (lines 54–91) hardcodes `DEFAULT_RESEARCH_KEYWORDS` and `PHILIPPINE_RSS_FEEDS` with Filipino-language and Philippines-specific sources as the fallback when no config override is provided.

**Files:** `src/constants.py` lines 54–91

**Impact:** Any new user who does not configure `research_keywords` and `research_rss_feeds` in `config.json` will receive research results optimised for a Filipino audience, with no indication this is happening. The tool presents itself as generic in `README.md`.

**Fix approach:** Document the default audience in `docs/Configuration.md`; consider making the defaults empty with a clear "no defaults" error.

---

### `Outreach.set_email_for_website` Has No Timeout on HTTP Requests

**Issue:** `src/classes/Outreach.py` `set_email_for_website()` (line 178) calls `requests.get(website)` with no `timeout` argument. If any scraped business website hangs, the outreach loop stalls indefinitely on that request.

**Files:** `src/classes/Outreach.py` line 178

**Fix approach:** Add `timeout=10` to the `requests.get()` call.

---

### `main()` Calls Itself Recursively on Invalid Input

**Issue:** `src/main.py` calls `main()` recursively on invalid account selection (lines 150, 326, 452, 501). Deep invalid input sequences could overflow the call stack.

**Files:** `src/main.py` lines 150, 326, 452, 501

**Fix approach:** Replace recursive `main()` calls with `continue` inside the existing `while True` loop.

---

### Test Coverage Is Limited to Post Bridge Integration Only

**Issue:** The `tests/` directory contains four test files (`test_config.py`, `test_cron_post_bridge.py`, `test_post_bridge_client.py`, `test_post_bridge_integration.py`) covering only the Post Bridge client and integration path. There are zero tests for the YouTube pipeline, Twitter automation, AFM scraping, Outreach, LLM provider dispatch, TTS providers, or the cache layer.

**Files:** `tests/` directory; no tests for `src/classes/YouTube.py`, `src/classes/Twitter.py`, `src/cache.py`, `src/llm_provider.py`, `src/tts_providers.py`

**Impact:** Regressions in core video generation logic go undetected. The `generate_prompts` JSON parsing fallback chain and `generate_script` retry recursion are particularly risky without test coverage.

**Priority:** Medium — acceptable for a personal automation tool but must be addressed before the managed pipeline or dashboard are relied upon for unattended production.

---

### Chatterbox TTS Is Hardcoded to CPU

**Issue:** `src/tts_providers.py` `ChatterboxProvider._load_model()` (line 59) passes `device="cpu"` unconditionally with the comment "MPS is unstable on Apple Silicon." This means Apple Silicon users cannot use GPU acceleration even if they have a stable MPS environment.

**Files:** `src/tts_providers.py` line 59

**Fix approach:** Expose a `tts_device` config key (defaulting to `"cpu"`) consistent with the existing `whisper_device` pattern.

---

### `src/classes/Tts.py` Default Output Path Uses Module-Level `ROOT_DIR`

**Issue:** The default `output_file` parameter in `TTS.synthesize()` (`src/classes/Tts.py` line 26) is evaluated at class definition time using `os.path.join(ROOT_DIR, ".mp", "audio.wav")`. If `ROOT_DIR` is computed incorrectly (e.g., in test contexts where `sys.path[0]` differs), the default path silently points to the wrong directory.

**Files:** `src/classes/Tts.py` line 26

**Fix approach:** Use `None` as the default and resolve the path inside the function body.

---

*Concerns audit: 2026-03-28*
