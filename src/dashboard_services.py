import os
import subprocess
import time
from urllib.parse import urlparse

import requests

from cache import get_cardnews_jobs
from classes.CardNews import CardNews
from config import ROOT_DIR
from config import get_llm_provider
from flask import url_for
from llm_provider import ensure_model_selected
from llm_provider import get_active_model

from dashboard_helpers import _build_job_cards
from dashboard_helpers import _update_job_status
from dashboard_helpers import _utc_timestamp


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


def start_comfyui_service(base_url: str) -> tuple[bool, str]:
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


def build_service_statuses(config_payload: dict, image_config: dict) -> list[dict]:
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


def build_overview(draft_cards: list[dict], profiles: list[dict], image_config: dict) -> list[dict]:
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


def run_cardnews_job(job_id: str, profile: dict, topic_override: str | None, format_mode: str) -> None:
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
