import os

from flask import Flask
from flask import abort
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for

from cache import add_account
from cache import get_accounts
from cache import get_cardnews_draft
from cache import get_cardnews_drafts
from cache import remove_account
from cache import update_account
from classes.CardNews import CardNews
from config import ROOT_DIR
from config import ensure_config_file
from config import get_cardnews_config
from config import get_dashboard_host
from config import get_dashboard_port
from config import get_full_config
from config import get_llm_provider
from config import update_config
from llm_provider import ensure_model_selected
from llm_provider import get_active_model
from llm_provider import get_active_provider
from llm_provider import select_provider
from llm_provider import select_provider_model


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


def create_app() -> Flask:
    ensure_config_file()
    template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    app = Flask(__name__, template_folder=template_dir)

    @app.get("/")
    def dashboard_index():
        notice = request.args.get("notice", "")
        error = request.args.get("error", "")
        state = {
            "config": get_full_config(),
            "youtube_accounts": get_accounts("youtube"),
            "cardnews_profiles": get_accounts("cardnews"),
            "cardnews_drafts": get_cardnews_drafts(),
            "cardnews_defaults": get_cardnews_config(),
            "llm": {
                "provider": get_llm_provider(),
                "active_provider": get_active_provider(),
                "active_model": get_active_model(),
                "provider_options": ["lmstudio", "ollama", "openai", "gemini"],
            },
        }

        preview_map = {}
        for draft in state["cardnews_drafts"]:
            preview_map[draft["id"]] = _draft_preview_files(draft)

        return render_template(
            "dashboard.html",
            state=state,
            notice=notice,
            error=error,
            preview_map=preview_map,
        )

    @app.get("/api/state")
    def api_state():
        return jsonify(
            {
                "youtube_accounts": get_accounts("youtube"),
                "cardnews_profiles": get_accounts("cardnews"),
                "cardnews_drafts": get_cardnews_drafts(),
            }
        )

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
                "post_bridge": {
                    "enabled": _parse_bool(request.form.get("post_bridge_enabled")),
                    "auto_crosspost": _parse_bool(request.form.get("post_bridge_auto_crosspost")),
                },
                "cardnews": {
                    "slides_per_post": int(request.form.get("slides_per_post", "6") or 6),
                    "review_required": _parse_bool(request.form.get("review_required")),
                    "default_channels": _parse_channels(request.form.get("default_channels", "")),
                },
            }
        )

        if llm_model:
            select_provider_model(provider, llm_model)
        else:
            select_provider(provider)

        return redirect(url_for("dashboard_index", notice="Settings saved."))

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
        profile = _find_cardnews_profile(profile_id)

        if profile is None:
            return redirect(url_for("dashboard_index", error="Select a valid CardNews profile."))

        try:
            ensure_model_selected()
            studio = CardNews(profile)
            draft = studio.prepare_draft(topic_override or None)
            return redirect(
                url_for(
                    "dashboard_index",
                    notice=f"Generated CardNews draft '{draft.get('topic', '')}'.",
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
