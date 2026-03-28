import os
import threading
from uuid import uuid4

from flask import Flask
from flask import abort
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for

from cache import add_account
from cache import add_cardnews_job
from cache import get_accounts
from cache import get_cardnews_draft
from cache import get_cardnews_drafts
from cache import get_cardnews_jobs
from cache import remove_account
from cache import update_account
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

from classes.CardNews import CardNews
from dashboard_helpers import _build_draft_cards
from dashboard_helpers import _build_job_cards
from dashboard_helpers import _find_cardnews_profile
from dashboard_helpers import _parse_bool
from dashboard_helpers import _parse_channels
from dashboard_helpers import _utc_timestamp
from dashboard_services import IMAGE_PRESETS
from dashboard_services import build_overview
from dashboard_services import build_service_statuses
from dashboard_services import run_cardnews_job
from dashboard_services import start_comfyui_service as _start_comfyui_service


def create_app() -> Flask:
    ensure_config_file()
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
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
            "overview": build_overview(draft_cards, get_accounts("cardnews"), image_config),
            "service_statuses": build_service_statuses(config_payload, image_config),
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

        update_config(
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
                target=run_cardnews_job,
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
