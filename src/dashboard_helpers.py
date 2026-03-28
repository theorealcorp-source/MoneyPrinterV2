import os
from datetime import datetime

from cache import get_cardnews_draft
from config import get_cardnews_config
from cache import update_cardnews_job


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
    from cache import get_accounts
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
