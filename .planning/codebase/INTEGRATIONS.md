# External Integrations
_Last updated: 2026-03-28_

## Summary
MoneyPrinterV2 integrates with seven distinct external services spanning LLM inference, image generation, speech synthesis, transcription, video platform APIs, cross-posting, and email. Each integration is configured via `config.json` and accessed through purpose-built modules under `src/`. No integration uses a shared SDK client — each is wired independently.

---

## LLM Providers

Three providers are supported. The active provider is selected via `llm_provider` in `config.json`. All text generation goes through the unified `generate_text()` function in `src/llm_provider.py`.

**Ollama (local)**
- Purpose: Primary LLM for script, metadata, and tweet generation
- Client: `ollama` Python SDK (`ollama.Client`)
- Connection: `ollama_base_url` in `config.json` (default `http://127.0.0.1:11434`)
- Auth: None — local server, no API key
- Model: `ollama_model` in `config.json`; if empty, user picks from `ollama.Client.list()` at startup
- Implementation: `src/llm_provider.py` → `_generate_with_ollama()`

**OpenAI / OpenAI-compatible**
- Purpose: Optional cloud LLM alternative
- Client: Raw `requests.post` to `/chat/completions`
- Base URL: `openai_base_url` in `config.json` (default `https://api.openai.com/v1`)
- Auth: Bearer token — `openai_api_key` in `config.json` or `OPENAI_API_KEY` env var
- Model: `openai_model` in `config.json` (default `gpt-4o-mini`)
- Implementation: `src/llm_provider.py` → `_generate_with_openai()`
- Note: Base URL is configurable, making it compatible with local OpenAI-compatible servers

**Google Gemini**
- Purpose: Optional cloud LLM alternative; also reuses the same API key for image generation
- Client: `google-generativeai` SDK (`genai.GenerativeModel`)
- Auth: API key — `nanobanana2_api_key` in `config.json` (shared with image generation)
- Model: `gemini_model` in `config.json` (default `gemini-2.5-flash`)
- Implementation: `src/llm_provider.py` → `_generate_with_gemini()`

---

## Image Generation

**Nano Banana 2 / Gemini Image API**
- Purpose: Generates per-scene images for YouTube Shorts
- Endpoint: `nanobanana2_api_base_url` in `config.json` (default `https://generativelanguage.googleapis.com/v1beta`)
- Auth: API key — `nanobanana2_api_key` in `config.json`
- Model: `nanobanana2_model` in `config.json` (default `gemini-3.1-flash-image-preview`)
- Aspect ratio: `nanobanana2_aspect_ratio` in `config.json` (default `9:16`)
- Implementation: Called from `src/classes/YouTube.py` via direct HTTP requests

---

## Text-to-Speech Providers

Two TTS providers are supported. Selected via `tts_provider` in `config.json`. Dispatched by `src/tts_providers.py` and exposed through the `TTS` wrapper class in `src/classes/Tts.py`.

**Chatterbox (local)**
- Purpose: Voice-cloning TTS; default provider
- Client: `chatterbox-tts` Python package (`ChatterboxTTS.from_pretrained`)
- Auth: None — runs locally on CPU
- Config: `tts_ref_audio` — path to reference WAV file for voice cloning (default `.mp/my_voice_ref.wav`)
- Output: WAV via `soundfile`
- Implementation: `src/tts_providers.py` → `ChatterboxProvider`

**ElevenLabs (cloud)**
- Purpose: Cloud TTS alternative
- Endpoint: `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
- Auth: API key — `elevenlabs_api_key` in `config.json` or `ELEVENLABS_API_KEY` env var
- Config keys: `elevenlabs_voice_id`, `elevenlabs_model_id`, `elevenlabs_stability`, `elevenlabs_similarity_boost`, `elevenlabs_style`, `elevenlabs_use_speaker_boost`
- Output format: PCM 44100 Hz (primary); falls back to MPEG → WAV via `ffmpeg` subprocess if PCM rejected (HTTP 400/401/402/403)
- Implementation: `src/tts_providers.py` → `ElevenLabsProvider`

---

## Speech-to-Text (Transcription)

Used to generate subtitles from synthesized audio. Selected via `stt_provider` in `config.json`.

**Local Whisper**
- Purpose: On-device transcription
- Client: `faster-whisper` Python package
- Config: `whisper_model` (default `base`), `whisper_device` (default `auto`), `whisper_compute_type` (default `int8`)
- Auth: None

**AssemblyAI (cloud)**
- Purpose: Cloud transcription alternative
- Client: `assemblyai` Python SDK
- Auth: API key — `assembly_ai_api_key` in `config.json`
- Implementation: imported directly in `src/classes/YouTube.py`

---

## YouTube

**YouTube Data API v3 (OAuth 2.0)**
- Purpose: Video upload and research/signal collection
- Client: `google-api-python-client` (`build("youtube", "v3", credentials=creds)`)
- Auth: OAuth 2.0 — user grants scopes `youtube.upload` + `youtube.readonly` via browser flow on first run; token persisted to `youtube_oauth_token` path (default `.mp/youtube_token.json`)
- Client secrets: `youtube_client_secrets` in `config.json` (default `client_secrets.json`); must be downloaded from Google Cloud Console
- Scopes: `https://www.googleapis.com/auth/youtube.upload`, `https://www.googleapis.com/auth/youtube.readonly`
- Implementation: `src/youtube_auth.py` → `build_youtube_client()`; used in `src/classes/YouTube.py` (upload) and `src/research/collectors.py` (signal collection)

**Selenium / YouTube Studio**
- Purpose: Legacy/fallback video upload and management via browser automation
- Auth: Pre-authenticated Firefox profile (user logs in manually once; profile path stored per-account in `.mp/youtube.json` and as default in `config.json`)
- Implementation: `src/classes/YouTube.py`

---

## Post Bridge (Cross-posting)

- Purpose: After a YouTube Short is produced, optionally cross-posts the video to TikTok and/or Instagram
- API base: `https://api.post-bridge.com/v1`
- Auth: Bearer token — `post_bridge.api_key` in `config.json` or `POST_BRIDGE_API_KEY` env var
- Config: `post_bridge.enabled` (bool), `post_bridge.platforms` (list), `post_bridge.account_ids` (list), `post_bridge.auto_crosspost` (bool)
- Media upload: signed URL flow — POST to `/media/create-upload-url` returns `upload_url`; PUT file to signed URL
- Retry policy: 3 retries on HTTP 429, 500, 502, 503, 504 with 0.5s × attempt backoff
- Pagination: `list_social_accounts()` follows `meta.next` cursor
- Implementation: `src/classes/PostBridge.py` (API client), `src/post_bridge_integration.py` (orchestration)

---

## Email / SMTP (Outreach)

- Purpose: Send cold outreach emails to businesses discovered via Google Maps scraper
- Client: `yagmail` Python package (wraps SMTP)
- Config: `email.smtp_server`, `email.smtp_port`, `email.username`, `email.password` in `config.json`
- Default server: `smtp.gmail.com:587`
- Email body: HTML file referenced by `outreach_message_body_file` in `config.json` (default `outreach_message.html`)
- Subject: `outreach_message_subject` in `config.json`
- Implementation: `src/classes/Outreach.py`

---

## Google Maps Scraper (Outreach)

- Purpose: Scrapes Google Maps to find local business email addresses for outreach
- Client: External Go binary — `gosom/google-maps-scraper` v0.9.7 downloaded from GitHub ZIP at runtime (`google_maps_scraper` URL in `config.json`)
- Auth: None (scrapes public Google Maps results)
- Prerequisites: Go must be installed (`go version` checked at class init); binary compiled via `subprocess`
- Config: `google_maps_scraper_niche`, `scraper_timeout` in `config.json`
- Implementation: `src/classes/Outreach.py`

---

## Jamendo (Background Music)

- Purpose: Fetches royalty-free background music for YouTube videos
- Auth: Client ID — `jamendo_client_id` in `config.json`
- Config: `jamendo_music_tags` in `config.json` (default `ambient`)
- Implementation: referenced in `config.example.json`; called from `src/classes/YouTube.py` via `requests`

---

## RSS Feeds (Research Pipeline)

- Purpose: Collects trending topic signals for content planning
- Client: `feedparser` Python package
- Auth: None
- Config: `research_rss_feeds` list in `config.json`; Philippine-specific feeds also hardcoded in `src/constants.py` as `PHILIPPINE_RSS_FEEDS`
- Implementation: `src/research/collectors.py`

---

## Twitter / X.com (Selenium)

- Purpose: Posts tweets and affiliate pitches
- Auth: Pre-authenticated Firefox profile (no API token used)
- Implementation: `src/classes/Twitter.py`; Selenium selectors maintained in `src/constants.py`

---

## Amazon (Selenium)

- Purpose: Scrapes product info for affiliate marketing
- Auth: Pre-authenticated Firefox profile
- Implementation: `src/classes/AFM.py`; Selenium selectors maintained in `src/constants.py`

---

## Environment Variable Overrides

The following env vars override `config.json` values (checked in their respective modules):

| Env var | Overrides |
|---|---|
| `POST_BRIDGE_API_KEY` | `post_bridge.api_key` |
| `OPENAI_API_KEY` | `openai_api_key` |
| `ELEVENLABS_API_KEY` | `elevenlabs_api_key` |
| `GEMINI_API_KEY` | `nanobanana2_api_key` (Gemini LLM path) |
