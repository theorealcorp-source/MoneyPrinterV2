import os
import subprocess
import threading
import time
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

from flask import Flask
from flask import abort
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for
import requests

from cache import add_account
from cache import add_cardnews_job
from cache import get_accounts
from cache import get_cardnews_draft
from cache import get_cardnews_drafts
from cache import get_cardnews_jobs
from cache import get_cardnews_job
from cache import remove_account
from cache import update_cardnews_job
from cache import update_account
from classes.CardNews import CardNews
from config import ROOT_DIR
from config import ensure_config_file
from config import get_cardnews_config
from config import get_dashboard_host
from config import get_dashboard_port
from config import get_full_config
from config import get_image_generation_config
from config import get_llm_provider
from config import update_config
from llm_provider import ensure_model_selected
from llm_provider import get_active_model
from llm_provider import get_active_provider
from llm_provider import select_provider
from llm_provider import select_provider_model


LOCAL_SERVICE_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
COMFYUI_START_SCRIPT = os.path.join(ROOT_DIR, "scripts", "start_comfyui_local.sh")
COMFYUI_RUNTIME_DIR = os.path.join(ROOT_DIR, ".mp", "runtime")
COMFYUI_PID_PATH = os.path.join(COMFYUI_RUNTIME_DIR, "comfyui.pid")
COMFYUI_LOG_PATH = os.path.join(COMFYUI_RUNTIME_DIR, "comfyui.log")
IMAGE_PRESETS = {
    "flux_fast": {
        "label": "FLUX Fast",
        "description": "Use FLUX for a single shared hero background when you want to test a stronger key visual.",
        "payload": {
            "image_generation": {
                "provider": "comfyui",
                "comfyui": {
                    "workflow_path": "",
                    "checkpoint": "flux1-schnell-fp8.safetensors",
                    "negative_prompt": "",
                    "steps": 4,
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "timeout_seconds": 360,
                },
            },
            "cardnews": {
                "background_strategy": "shared_single",
                "background_style": "editorial_abstract",
            },
        },
    },
    "sdxl_cardnews": {
        "label": "SDXL CardNews",
        "description": "Practical default for this app: generate two SDXL backgrounds per deck and reuse them across slides.",
        "payload": {
            "image_generation": {
                "provider": "comfyui",
                "comfyui": {
                    "workflow_path": "",
                    "checkpoint": "sd_xl_base_1.0_0.9vae.safetensors",
                    "negative_prompt": "low quality, blurry, distorted, watermark, logo, text",
                    "steps": 10,
                    "cfg": 4.5,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "timeout_seconds": 600,
                },
            },
            "cardnews": {
                "background_strategy": "deck_pair",
                "background_style": "editorial_abstract",
            },
        },
    },
    "gemini_quick": {
        "label": "Gemini Quick",
        "description": "Switch image generation back to Gemini for remote output.",
        "payload": {
            "image_generation": {
                "provider": "gemini",
            },
            "cardnews": {
                "background_strategy": "per_slide",
                "background_style": "editorial_abstract",
            },
        },
    },
}
ACTIVE_JOB_STATUSES = {"queued", "running"}


def _parse_bool(raw_value: str | None) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_channels(raw_value: str | None) -> list[str]:
    channels = []
    for chunk in str(raw_value or "").split(","):
        normalized = chunk.strip().lower()
        if normalized and normalized not in channels:
            channels.append(normalized)

    return channels or get_cardnews_config()["default_channels"]


def _find_cardnews_profile(profile_id: str) -> dict | None:
    for profile in get_accounts("cardnews"):
        if profile.get("id") == profile_id:
            return profile
    return None


def _draft_preview_files(draft: dict) -> list[str]:
    files = []
    for slide in draft.get("slides", []):
        asset_path = slide.get("asset_path", "")
        if asset_path and os.path.exists(asset_path):
            files.append(os.path.basename(asset_path))
    return files


def _draft_slide_urls(draft: dict) -> list[str]:
    return [
        f"/artifacts/{draft.get('id', '')}/{file_name}"
        for file_name in _draft_preview_files(draft)
    ]


def _build_draft_cards(drafts: list[dict]) -> list[dict]:
    cards = []
    for draft in sorted(drafts, key=lambda item: str(item.get("created_at", "")), reverse=True):
        slide_urls = _draft_slide_urls(draft)
        review = draft.get("review", {}) if isinstance(draft.get("review"), dict) else {}
        slides = draft.get("slides", []) if isinstance(draft.get("slides"), list) else []
        format_mode = str(draft.get("format", "carousel")).strip().lower() or "carousel"
        cards.append(
            {
                **draft,
                "format": format_mode,
                "slide_urls": slide_urls,
                "slide_count": len(slide_urls),
                "slide_count_label": (
                    f"{len(slide_urls)} page" if format_mode == "poster" else f"{len(slide_urls)} slides"
                ),
                "issue_count": len(review.get("issues", []) or []),
                "slide_types": [str(slide.get("type", "slide")) for slide in slides],
                "primary_title": str(slides[0].get("title", "")) if slides else "",
            }
        )

    return cards


def _utc_timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _update_job_status(job_id: str, **updates) -> dict | None:
    payload = dict(updates)
    payload["updated_at"] = _utc_timestamp()
    return update_cardnews_job(job_id, payload)


def _build_job_cards(jobs: list[dict]) -> list[dict]:
    cards = []
    for job in sorted(jobs, key=lambda item: str(item.get("created_at", "")), reverse=True):
        status = str(job.get("status", "queued")).strip().lower() or "queued"
        draft = get_cardnews_draft(str(job.get("draft_id", "")).strip()) if job.get("draft_id") else None
        slide_urls = _draft_slide_urls(draft) if draft else []
        progress = int(job.get("progress", 0) or 0)
        cards.append(
            {
                **job,
                "status": status,
                "progress": max(0, min(progress, 100)),
                "is_active": status in ACTIVE_JOB_STATUSES,
                "slide_urls": slide_urls,
                "has_preview": bool(slide_urls),
            }
        )

    return cards


def _is_local_service_url(raw_url: str) -> bool:
    try:
        parsed = urlparse(str(raw_url).strip())
    except ValueError:
        return False

    return parsed.hostname in LOCAL_SERVICE_HOSTS


def _probe_service_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return None


def _read_pid_file(pid_path: str) -> int | None:
    if not os.path.exists(pid_path):
        return None

    try:
        with open(pid_path, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _comfyui_online(base_url: str) -> bool:
    return _probe_service_json(f"{base_url.rstrip('/')}/system_stats") is not None


def _start_comfyui_service(base_url: str) -> tuple[bool, str]:
    if _comfyui_online(base_url):
        return True, "ComfyUI is already online."

    if not os.path.exists(COMFYUI_START_SCRIPT):
        return False, f"ComfyUI start script was not found: {COMFYUI_START_SCRIPT}"

    os.makedirs(COMFYUI_RUNTIME_DIR, exist_ok=True)
    existing_pid = _read_pid_file(COMFYUI_PID_PATH)
    if _pid_is_running(existing_pid):
        return False, "ComfyUI start was requested, but the service is still not responding."

    with open(COMFYUI_LOG_PATH, "a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            ["bash", COMFYUI_START_SCRIPT],
            cwd=ROOT_DIR,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    with open(COMFYUI_PID_PATH, "w", encoding="utf-8") as handle:
        handle.write(str(process.pid))

    deadline = time.time() + 20
    while time.time() < deadline:
        if _comfyui_online(base_url):
            return True, "ComfyUI is online."
        if process.poll() is not None:
            break
        time.sleep(1.0)

    return False, f"ComfyUI did not come online within 20 seconds. Check {COMFYUI_LOG_PATH}."


def _build_service_statuses(config_payload: dict, image_config: dict) -> list[dict]:
    llm_provider = get_llm_provider()
    llm_model = get_active_model() or config_payload.get("llm_model", "")
    statuses = []

    if llm_provider == "ollama":
        ollama_url = str(config_payload.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        tags = _probe_service_json(f"{ollama_url}/api/tags") if _is_local_service_url(ollama_url) else None
        statuses.append(
            {
                "name": "LLM",
                "kind": "ok" if tags is not None else "warn",
                "summary": "Ollama online" if tags is not None else "Ollama unreachable",
                "detail": llm_model or ollama_url,
            }
        )
    elif llm_provider == "lmstudio":
        base_url = str(config_payload.get("openai_base_url", "http://127.0.0.1:1234/v1")).rstrip("/")
        models = _probe_service_json(f"{base_url}/models") if _is_local_service_url(base_url) else None
        statuses.append(
            {
                "name": "LLM",
                "kind": "ok" if models is not None else "warn",
                "summary": "LM Studio online" if models is not None else "LM Studio unreachable",
                "detail": llm_model or base_url,
            }
        )
    elif llm_provider == "openai":
        has_key = bool(str(config_payload.get("openai_api_key", "")).strip())
        statuses.append(
            {
                "name": "LLM",
                "kind": "ok" if has_key else "warn",
                "summary": "OpenAI configured" if has_key else "OpenAI key missing",
                "detail": llm_model or str(config_payload.get("openai_base_url", "https://api.openai.com/v1")),
            }
        )
    else:
        has_key = bool(str(config_payload.get("gemini_api_key", "")).strip())
        statuses.append(
            {
                "name": "LLM",
                "kind": "ok" if has_key else "warn",
                "summary": "Gemini configured" if has_key else "Gemini key missing",
                "detail": llm_model or str(config_payload.get("gemini_model", "gemini-2.5-flash")),
            }
        )

    image_provider = str(image_config.get("provider", "gemini")).strip().lower()
    if image_provider == "comfyui":
        comfyui_config = image_config["comfyui"]
        comfyui_base_url = str(comfyui_config.get("base_url", "http://127.0.0.1:8188")).rstrip("/")
        stats = _probe_service_json(f"{comfyui_base_url}/system_stats")
        device_name = ""
        if stats:
            devices = stats.get("devices", [])
            if isinstance(devices, list) and devices:
                device_name = str(devices[0].get("name", "")).strip()
        statuses.append(
            {
                "name": "Image",
                "kind": "ok" if stats is not None else "warn",
                "summary": "ComfyUI online" if stats is not None else "ComfyUI offline",
                "detail": str(comfyui_config.get("checkpoint", "")).strip() or device_name or "No checkpoint selected",
                "action_url": url_for("start_comfyui_service") if stats is None else "",
                "action_label": "Start ComfyUI" if stats is None else "",
            }
        )
    elif image_provider == "gemini":
        has_key = bool(
            str(config_payload.get("nanobanana2_api_key", "")).strip()
            or str(config_payload.get("gemini_api_key", "")).strip()
        )
        statuses.append(
            {
                "name": "Image",
                "kind": "ok" if has_key else "warn",
                "summary": "Gemini image configured" if has_key else "Gemini image key missing",
                "detail": str(config_payload.get("nanobanana2_model", "gemini-3.1-flash-image-preview")),
            }
        )
    else:
        statuses.append(
            {
                "name": "Image",
                "kind": "muted",
                "summary": "Image generation disabled",
                "detail": "Fallback gradients only",
            }
        )

    post_bridge_config = config_payload.get("post_bridge", {})
    post_bridge_enabled = bool(post_bridge_config.get("enabled"))
    statuses.append(
        {
            "name": "Publish",
            "kind": "ok" if post_bridge_enabled else "muted",
            "summary": "Post Bridge enabled" if post_bridge_enabled else "Publish bridge off",
            "detail": ", ".join(post_bridge_config.get("platforms", [])) or "No channels",
        }
    )

    return statuses


def _build_overview(draft_cards: list[dict], profiles: list[dict], image_config: dict) -> list[dict]:
    job_cards = _build_job_cards(get_cardnews_jobs())
    running_jobs = sum(1 for job in job_cards if job.get("is_active"))
    flagged_count = sum(
        1 for draft in draft_cards if str(draft.get("review", {}).get("status", "")).lower() == "flag"
    )
    active_checkpoint = image_config["comfyui"].get("checkpoint", "") if image_config.get("provider") == "comfyui" else image_config.get("provider", "none")

    return [
        {"label": "Profiles", "value": str(len(profiles)), "hint": "Reusable content profiles"},
        {"label": "Drafts", "value": str(len(draft_cards)), "hint": "Stored card decks"},
        {"label": "Running", "value": str(running_jobs), "hint": "Background generation jobs"},
        {"label": "Flags", "value": str(flagged_count), "hint": "Drafts that need a check"},
        {"label": "Image Stack", "value": str(image_config.get("provider", "none")).upper(), "hint": str(active_checkpoint or "No model selected")},
    ]


def _run_cardnews_job(job_id: str, profile: dict, topic_override: str | None, format_mode: str) -> None:
    try:
        ensure_model_selected()
        studio = CardNews(profile)
        _update_job_status(
            job_id,
            status="running",
            stage="planning",
            progress=8,
            message="Generating topic and outline",
        )
        draft = studio.create_draft(topic_override=topic_override, format_override=format_mode)
        _update_job_status(
            job_id,
            status="running",
            stage="review",
            progress=20,
            message="Reviewing generated draft",
            draft_id=draft["id"],
            topic=draft.get("topic", ""),
        )
        draft = studio.review_draft(draft["id"])

        def on_progress(payload: dict) -> None:
            stage = str(payload.get("stage", "render")).strip() or "render"
            progress = int(payload.get("progress", 0) or 0)
            _update_job_status(
                job_id,
                status="running",
                stage=stage,
                progress=progress,
                message=str(payload.get("message", "")).strip(),
                step_current=payload.get("current"),
                step_total=payload.get("total"),
                draft_id=draft["id"],
                topic=draft.get("topic", ""),
            )

        _update_job_status(
            job_id,
            status="running",
            stage="render",
            progress=28,
            message="Preparing final assets",
            draft_id=draft["id"],
            topic=draft.get("topic", ""),
        )
        draft = studio.render_draft(draft["id"], progress_callback=on_progress)
        _update_job_status(
            job_id,
            status="completed",
            stage="done",
            progress=100,
            message="Draft ready for review",
            draft_id=draft["id"],
            topic=draft.get("topic", ""),
            finished_at=_utc_timestamp(),
        )
    except Exception as exc:
        _update_job_status(
            job_id,
            status="failed",
            stage="error",
            progress=100,
            message=str(exc),
            error=str(exc),
            finished_at=_utc_timestamp(),
        )


def create_app() -> Flask:
    ensure_config_file()
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    app = Flask(__name__, template_folder=template_dir)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    @app.get("/")
    def dashboard_index():
        notice = request.args.get("notice", "")
        error = request.args.get("error", "")
        config_payload = get_full_config()
        draft_cards = _build_draft_cards(get_cardnews_drafts())
        job_cards = _build_job_cards(get_cardnews_jobs())
        image_config = get_image_generation_config()
        recent_draft = draft_cards[0] if draft_cards else None
        state = {
            "config": config_payload,
            "youtube_accounts": get_accounts("youtube"),
            "cardnews_profiles": get_accounts("cardnews"),
            "cardnews_drafts": draft_cards,
            "cardnews_jobs": job_cards,
            "cardnews_defaults": get_cardnews_config(),
            "overview": _build_overview(draft_cards, get_accounts("cardnews"), image_config),
            "service_statuses": _build_service_statuses(config_payload, image_config),
            "recent_draft": recent_draft,
            "image_presets": [
                {
                    "id": preset_id,
                    "label": preset["label"],
                    "description": preset["description"],
                }
                for preset_id, preset in IMAGE_PRESETS.items()
            ],
            "llm": {
                "provider": get_llm_provider(),
                "active_provider": get_active_provider(),
                "active_model": get_active_model(),
                "provider_options": ["lmstudio", "ollama", "openai", "gemini"],
            },
            "image": {
                "config": image_config,
                "provider_options": ["none", "comfyui", "gemini"],
            },
        }

        return render_template(
            "dashboard.html",
            state=state,
            notice=notice,
            error=error,
        )

    @app.get("/api/state")
    def api_state():
        return jsonify(
            {
                "youtube_accounts": get_accounts("youtube"),
                "cardnews_profiles": get_accounts("cardnews"),
                "cardnews_drafts": get_cardnews_drafts(),
                "cardnews_jobs": get_cardnews_jobs(),
            }
        )

    @app.get("/api/jobs")
    def api_jobs():
        return jsonify({"jobs": _build_job_cards(get_cardnews_jobs())})

    @app.post("/settings/save")
    def save_settings():
        current = get_full_config()

        provider = str(request.form.get("llm_provider", "ollama")).strip().lower() or "ollama"
        llm_model = str(request.form.get("llm_model", "")).strip()
        ollama_base_url = str(
            request.form.get("ollama_base_url", current.get("ollama_base_url", ""))
        ).strip()
        openai_base_url = str(
            request.form.get("openai_base_url", current.get("openai_base_url", ""))
        ).strip()
        openai_api_key = str(request.form.get("openai_api_key", "")).strip() or str(
            current.get("openai_api_key", "")
        ).strip()
        gemini_api_key = str(request.form.get("gemini_api_key", "")).strip() or str(
            current.get("gemini_api_key", "")
        ).strip()
        gemini_model = str(
            request.form.get("gemini_model", current.get("gemini_model", "gemini-2.5-flash"))
        ).strip()
        image_config = get_image_generation_config()
        comfyui_current = image_config["comfyui"]
        gemini_image_current = image_config["gemini"]
        image_provider = str(
            request.form.get("image_provider", image_config.get("provider", "gemini"))
        ).strip().lower() or image_config.get("provider", "gemini")
        comfyui_base_url = str(
            request.form.get("comfyui_base_url", comfyui_current.get("base_url", ""))
        ).strip()
        comfyui_workflow_path = str(
            request.form.get("comfyui_workflow_path", comfyui_current.get("workflow_path", ""))
        ).strip()
        comfyui_checkpoint = str(
            request.form.get("comfyui_checkpoint", comfyui_current.get("checkpoint", ""))
        ).strip()
        comfyui_negative_prompt = str(
            request.form.get(
                "comfyui_negative_prompt",
                comfyui_current.get("negative_prompt", ""),
            )
        ).strip()
        gemini_image_api_base_url = str(
            request.form.get(
                "nanobanana2_api_base_url",
                gemini_image_current.get("api_base_url", ""),
            )
        ).strip()
        gemini_image_api_key = str(request.form.get("nanobanana2_api_key", "")).strip() or str(
            current.get("nanobanana2_api_key", "")
        ).strip()
        gemini_image_model = str(
            request.form.get("nanobanana2_model", gemini_image_current.get("model", ""))
        ).strip()
        gemini_image_aspect_ratio = str(
            request.form.get(
                "nanobanana2_aspect_ratio",
                gemini_image_current.get("aspect_ratio", "9:16"),
            )
        ).strip()

        try:
            comfyui_steps = int(
                request.form.get("comfyui_steps", str(comfyui_current.get("steps", 8))) or 8
            )
        except ValueError:
            comfyui_steps = int(comfyui_current.get("steps", 8))

        try:
            comfyui_cfg = float(
                request.form.get("comfyui_cfg", str(comfyui_current.get("cfg", 4.0))) or 4.0
            )
        except ValueError:
            comfyui_cfg = float(comfyui_current.get("cfg", 4.0))

        try:
            poster_item_count = int(
                request.form.get(
                    "poster_item_count",
                    str(current.get("cardnews", {}).get("poster_item_count", 6)),
                )
                or 6
            )
        except ValueError:
            poster_item_count = int(current.get("cardnews", {}).get("poster_item_count", 6) or 6)

        comfyui_sampler_name = str(
            request.form.get(
                "comfyui_sampler_name",
                comfyui_current.get("sampler_name", "euler"),
            )
        ).strip()
        comfyui_scheduler = str(
            request.form.get(
                "comfyui_scheduler",
                comfyui_current.get("scheduler", "normal"),
            )
        ).strip()

        updated = update_config(
            {
                "llm_provider": provider,
                "llm_model": llm_model,
                "ollama_base_url": ollama_base_url,
                "ollama_model": llm_model if provider == "ollama" else str(current.get("ollama_model", "")).strip(),
                "openai_base_url": openai_base_url,
                "openai_api_key": openai_api_key,
                "openai_model": llm_model if provider in {"lmstudio", "openai"} else str(current.get("openai_model", "")).strip(),
                "gemini_api_key": gemini_api_key,
                "gemini_model": gemini_model,
                "nanobanana2_api_base_url": gemini_image_api_base_url,
                "nanobanana2_api_key": gemini_image_api_key,
                "nanobanana2_model": gemini_image_model,
                "nanobanana2_aspect_ratio": gemini_image_aspect_ratio,
                "post_bridge": {
                    "enabled": _parse_bool(request.form.get("post_bridge_enabled")),
                    "auto_crosspost": _parse_bool(request.form.get("post_bridge_auto_crosspost")),
                },
                "image_generation": {
                    "provider": image_provider,
                    "comfyui": {
                        "base_url": comfyui_base_url,
                        "workflow_path": comfyui_workflow_path,
                        "checkpoint": comfyui_checkpoint,
                        "negative_prompt": comfyui_negative_prompt,
                        "steps": comfyui_steps,
                        "cfg": comfyui_cfg,
                        "sampler_name": comfyui_sampler_name,
                        "scheduler": comfyui_scheduler,
                    },
                },
                "cardnews": {
                    "format": str(
                        request.form.get(
                            "cardnews_format",
                            current.get("cardnews", {}).get("format", "carousel"),
                        )
                    ).strip().lower(),
                    "slides_per_post": int(request.form.get("slides_per_post", "6") or 6),
                    "poster_item_count": poster_item_count,
                    "review_required": _parse_bool(request.form.get("review_required")),
                    "default_channels": _parse_channels(request.form.get("default_channels", "")),
                    "background_strategy": str(
                        request.form.get(
                            "background_strategy",
                            current.get("cardnews", {}).get("background_strategy", "deck_pair"),
                        )
                    ).strip().lower(),
                    "background_style": str(
                        request.form.get(
                            "background_style",
                            current.get("cardnews", {}).get("background_style", "editorial_abstract"),
                        )
                    ).strip().lower(),
                },
            }
        )

        if llm_model:
            select_provider_model(provider, llm_model)
        else:
            select_provider(provider)

        return redirect(url_for("dashboard_index", notice="Settings saved."))

    @app.post("/services/comfyui/start")
    def start_comfyui_service():
        comfyui_base_url = str(
            get_image_generation_config()["comfyui"].get("base_url", "http://127.0.0.1:8188")
        ).rstrip("/")
        ok, message = _start_comfyui_service(comfyui_base_url)
        if ok:
            return redirect(url_for("dashboard_index", notice=message))
        return redirect(url_for("dashboard_index", error=message))

    @app.post("/settings/image-preset")
    def apply_image_preset():
        preset_name = str(request.form.get("preset", "")).strip()
        preset = IMAGE_PRESETS.get(preset_name)
        if preset is None:
            return redirect(url_for("dashboard_index", error="Unknown image preset."))

        current_image_config = get_image_generation_config()
        payload = {
            "image_generation": {
                **preset["payload"]["image_generation"],
                "comfyui": {
                    **current_image_config["comfyui"],
                    **preset["payload"]["image_generation"].get("comfyui", {}),
                },
            },
            "cardnews": {
                **get_cardnews_config(),
                **preset["payload"].get("cardnews", {}),
            },
        }
        update_config(payload)
        return redirect(
            url_for(
                "dashboard_index",
                notice=f"Applied image preset: {preset['label']}.",
            )
        )

    @app.post("/accounts/cardnews/save")
    def save_cardnews_account():
        profile_id = str(request.form.get("profile_id", "")).strip()
        payload = {
            "nickname": str(request.form.get("nickname", "")).strip(),
            "niche": str(request.form.get("niche", "")).strip(),
            "language": str(request.form.get("language", "")).strip(),
            "channels": _parse_channels(request.form.get("channels", "")),
        }

        if not payload["nickname"] or not payload["niche"] or not payload["language"]:
            return redirect(
                url_for("dashboard_index", error="Nickname, niche and language are required.")
            )

        if profile_id:
            update_account("cardnews", profile_id, payload)
            notice = "CardNews profile updated."
        else:
            payload["id"] = os.urandom(8).hex()
            add_account("cardnews", payload)
            notice = "CardNews profile added."

        return redirect(url_for("dashboard_index", notice=notice))

    @app.post("/accounts/cardnews/delete")
    def delete_cardnews_account():
        profile_id = str(request.form.get("profile_id", "")).strip()
        if not profile_id:
            return redirect(url_for("dashboard_index", error="Profile id is required."))

        remove_account("cardnews", profile_id)
        return redirect(url_for("dashboard_index", notice="CardNews profile deleted."))

    @app.post("/cardnews/generate")
    def generate_cardnews():
        profile_id = str(request.form.get("profile_id", "")).strip()
        topic_override = str(request.form.get("topic_override", "")).strip()
        format_mode = str(
            request.form.get("format_mode", get_cardnews_config().get("format", "carousel"))
        ).strip().lower()
        profile = _find_cardnews_profile(profile_id)

        if profile is None:
            return redirect(url_for("dashboard_index", error="Select a valid CardNews profile."))

        try:
            ensure_model_selected()
            job = {
                "id": str(uuid4()),
                "profile_id": profile_id,
                "profile_nickname": str(profile.get("nickname", "")).strip(),
                "topic": topic_override,
                "format": format_mode,
                "status": "queued",
                "stage": "queued",
                "progress": 2,
                "message": "Queued for generation",
                "draft_id": "",
                "error": "",
                "step_current": None,
                "step_total": None,
                "created_at": _utc_timestamp(),
                "updated_at": _utc_timestamp(),
                "finished_at": "",
            }
            add_cardnews_job(job)
            worker = threading.Thread(
                target=_run_cardnews_job,
                args=(job["id"], profile, topic_override or None, format_mode),
                daemon=True,
            )
            worker.start()
            return redirect(
                url_for(
                    "dashboard_index",
                    notice="CardNews generation started. Progress is shown in the queue.",
                )
            )
        except Exception as exc:
            return redirect(url_for("dashboard_index", error=str(exc)))

    @app.post("/cardnews/approve")
    def approve_cardnews():
        draft_id = str(request.form.get("draft_id", "")).strip()
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            return redirect(url_for("dashboard_index", error="Draft not found."))

        profile = _find_cardnews_profile(str(draft.get("profile_id", "")))
        if profile is None:
            return redirect(url_for("dashboard_index", error="Draft profile was not found."))

        CardNews(profile).approve_draft(draft_id)
        return redirect(url_for("dashboard_index", notice="Draft approved."))

    @app.post("/cardnews/publish")
    def publish_cardnews():
        draft_id = str(request.form.get("draft_id", "")).strip()
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            return redirect(url_for("dashboard_index", error="Draft not found."))

        profile = _find_cardnews_profile(str(draft.get("profile_id", "")))
        if profile is None:
            return redirect(url_for("dashboard_index", error="Draft profile was not found."))

        result = CardNews(profile).publish_draft(
            draft_id,
            interactive=False,
            force_publish=True,
        )
        if result:
            return redirect(url_for("dashboard_index", notice="Draft published via Post Bridge."))

        return redirect(url_for("dashboard_index", error="Draft publish was skipped or failed."))

    @app.get("/artifacts/<draft_id>/<file_name>")
    def serve_artifact(draft_id: str, file_name: str):
        asset_path = os.path.join(ROOT_DIR, ".mp", "cardnews", draft_id, "slides", file_name)
        if not os.path.exists(asset_path):
            abort(404)

        return send_file(asset_path, mimetype="image/png")

    return app


def main() -> None:
    app = create_app()
    app.run(host=get_dashboard_host(), port=get_dashboard_port(), debug=False)


if __name__ == "__main__":
    main()
