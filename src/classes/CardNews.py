import os
from datetime import datetime
from uuid import uuid4

from cache import add_cardnews_draft
from cache import get_cardnews_draft
from cache import get_cardnews_drafts_for_profile
from cache import update_cardnews_draft
from cardnews_renderer import render_cardnews_slides
from config import ROOT_DIR
from config import assert_folder_structure
from config import get_cardnews_config
from config import get_image_generation_config
from config import get_image_provider
from content_planner import CARDNEWS_SLIDE_TYPES
from content_planner import generate_cardnews_outline
from content_planner import generate_topic_idea
from content_planner import review_cardnews_draft
from image_generator import generate_image_asset
from post_bridge_integration import publish_cardnews_images
from status import info
from status import success
from status import warning


class CardNews:
    """
    Card-news pipeline for topic generation, review, rendering and publishing.
    """

    def __init__(self, profile: dict) -> None:
        self.profile = profile
        self.config = get_cardnews_config()

    @property
    def profile_id(self) -> str:
        return str(self.profile.get("id", ""))

    @property
    def nickname(self) -> str:
        return str(self.profile.get("nickname", ""))

    @property
    def niche(self) -> str:
        return str(self.profile.get("niche", ""))

    @property
    def language(self) -> str:
        return str(self.profile.get("language", "English"))

    @property
    def channels(self) -> list[str]:
        channels = self.profile.get("channels", self.config["default_channels"])
        if isinstance(channels, list):
            normalized = [str(channel).strip().lower() for channel in channels if str(channel).strip()]
            if normalized:
                return normalized
        return self.config["default_channels"]

    def list_drafts(self) -> list[dict]:
        return get_cardnews_drafts_for_profile(self.profile_id)

    def _draft_root(self, draft_id: str) -> str:
        return os.path.join(ROOT_DIR, ".mp", "cardnews", draft_id)

    def _run_rule_review(self, draft: dict) -> dict:
        issues = []
        slides = draft.get("slides", [])

        if len(slides) != self.config["slides_per_post"]:
            issues.append(
                f"Expected {self.config['slides_per_post']} slides but found {len(slides)}."
            )

        for index, slide in enumerate(slides, start=1):
            slide_type = str(slide.get("type", "")).strip().lower()
            eyebrow = str(slide.get("eyebrow", "")).strip()
            title = str(slide.get("title", "")).strip()
            body = str(slide.get("body", "")).strip()
            highlight = str(slide.get("highlight", "")).strip()
            bullets = slide.get("bullets", [])

            if slide_type not in CARDNEWS_SLIDE_TYPES:
                issues.append(f"Slide {index}: unknown slide type '{slide_type}'.")
            if not eyebrow:
                issues.append(f"Slide {index}: eyebrow is empty.")

            if not title:
                issues.append(f"Slide {index}: title is empty.")
            if not body:
                issues.append(f"Slide {index}: body is empty.")
            if len(eyebrow) > 18:
                issues.append(f"Slide {index}: eyebrow exceeds 18 characters.")
            if len(title) > 55:
                issues.append(f"Slide {index}: title exceeds 55 characters.")
            if len(body) > 220:
                issues.append(f"Slide {index}: body exceeds 220 characters.")
            if len(highlight) > 28:
                issues.append(f"Slide {index}: highlight exceeds 28 characters.")
            if isinstance(bullets, list) and len(bullets) > 3:
                issues.append(f"Slide {index}: has more than 3 bullets.")
            if any(char in body for char in ["#", "*", "_", "`"]):
                issues.append(f"Slide {index}: body contains markdown-like formatting.")
            claim_blob = " ".join(
                [
                    title,
                    body,
                    highlight,
                    " ".join(str(bullet) for bullet in bullets if str(bullet).strip()),
                ]
            )
            if any(char.isdigit() for char in claim_blob):
                issues.append(f"Slide {index}: contains numeric claim, verify facts manually.")

        if issues:
            return {
                "status": "flag",
                "summary": "Rule-based review found issues that should be checked.",
                "issues": issues,
            }

        return {"status": "pass", "summary": "Rule-based review passed.", "issues": []}

    def create_draft(self, topic_override: str | None = None) -> dict:
        """
        Create a new draft and persist it.
        """
        assert_folder_structure()

        topic = str(topic_override or "").strip()
        if not topic:
            topic = generate_topic_idea(self.niche, self.language)

        outline = generate_cardnews_outline(
            topic=topic,
            language=self.language,
            slide_count=self.config["slides_per_post"],
        )

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        slides = []
        for index, slide in enumerate(outline["slides"], start=1):
            slide_payload = dict(slide)
            slide_payload["index"] = index
            slide_payload["topic"] = outline["topic"]
            slide_payload["background_path"] = ""
            slide_payload["asset_path"] = ""
            slides.append(slide_payload)

        draft = {
            "id": str(uuid4()),
            "profile_id": self.profile_id,
            "profile_nickname": self.nickname,
            "topic": outline["topic"],
            "caption": outline["caption"],
            "language": self.language,
            "channels": self.channels,
            "slides": slides,
            "status": "draft",
            "review": {"status": "pending", "summary": "", "issues": []},
            "created_at": timestamp,
            "updated_at": timestamp,
            "published_at": "",
        }
        add_cardnews_draft(draft)
        success(f"Created CardNews draft: {draft['topic']}")
        return draft

    def review_draft(self, draft_id: str) -> dict:
        """
        Run LLM and rule-based review on a draft.
        """
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            raise ValueError(f"CardNews draft '{draft_id}' was not found.")

        llm_review = review_cardnews_draft(draft, self.language)
        rule_review = self._run_rule_review(draft)
        issues = llm_review.get("issues", []) + [
            issue for issue in rule_review.get("issues", []) if issue not in llm_review.get("issues", [])
        ]

        status = llm_review.get("status", "flag")
        if rule_review["status"] == "flag" and status == "pass":
            status = "flag"

        if any("empty" in issue.lower() for issue in issues):
            status = "block"

        summary = llm_review.get("summary", "") or rule_review.get("summary", "")
        updated = update_cardnews_draft(
            draft_id,
            {
                "review": {"status": status, "summary": summary, "issues": issues},
                "status": "reviewed",
                "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        return updated

    def render_draft(self, draft_id: str) -> dict:
        """
        Render a reviewed draft into PNG assets.
        """
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            raise ValueError(f"CardNews draft '{draft_id}' was not found.")

        draft_root = self._draft_root(draft_id)
        generated_dir = os.path.join(draft_root, "generated")
        slides_dir = os.path.join(draft_root, "slides")
        os.makedirs(generated_dir, exist_ok=True)
        os.makedirs(slides_dir, exist_ok=True)

        rendered_slides = []
        for slide in draft.get("slides", []):
            background_path = generate_image_asset(
                slide.get("visual_prompt", ""),
                generated_dir,
                aspect_ratio="4:5",
            )
            slide_copy = dict(slide)
            slide_copy["background_path"] = background_path or ""
            rendered_slides.append(slide_copy)

        if not any(slide.get("background_path", "") for slide in rendered_slides):
            provider = get_image_provider()
            if provider == "comfyui":
                comfyui_config = get_image_generation_config()["comfyui"]
                raise RuntimeError(
                    "ComfyUI did not return any images. "
                    f"Check the server at {comfyui_config['base_url']} and verify the workflow/checkpoint settings."
                )
            if provider != "none":
                warning(
                    "Configured image provider returned no background assets. "
                    "Slides were rendered with the visual fallback only."
                )

        asset_paths = render_cardnews_slides(
            rendered_slides,
            slides_dir,
            self.config["render_width"],
            self.config["render_height"],
            deck_topic=str(draft.get("topic", "")),
        )

        for slide, asset_path in zip(rendered_slides, asset_paths):
            slide["asset_path"] = asset_path

        updated = update_cardnews_draft(
            draft_id,
            {
                "slides": rendered_slides,
                "asset_paths": asset_paths,
                "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        info(f"Rendered {len(asset_paths)} slides for draft {draft_id}.")
        return updated

    def prepare_draft(self, topic_override: str | None = None) -> dict:
        """
        Create, review and render a draft in sequence.
        """
        draft = self.create_draft(topic_override=topic_override)
        draft = self.review_draft(draft["id"])
        draft = self.render_draft(draft["id"])
        return draft

    def approve_draft(self, draft_id: str) -> dict:
        """
        Mark a reviewed draft as approved.
        """
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            raise ValueError(f"CardNews draft '{draft_id}' was not found.")

        review = draft.get("review", {})
        if self.config["review_required"] and review.get("status") == "block":
            raise RuntimeError("Blocked draft cannot be approved until issues are fixed.")

        updated = update_cardnews_draft(
            draft_id,
            {
                "status": "approved",
                "approved_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        success(f"Approved CardNews draft {draft_id}.")
        return updated

    def publish_draft(
        self,
        draft_id: str,
        interactive: bool = True,
        force_publish: bool = False,
    ) -> bool | None:
        """
        Publish an approved draft through Post Bridge.
        """
        draft = get_cardnews_draft(draft_id)
        if draft is None:
            raise ValueError(f"CardNews draft '{draft_id}' was not found.")

        if self.config["review_required"] and draft.get("status") != "approved":
            raise RuntimeError("Draft must be approved before publishing.")

        image_paths = [
            slide.get("asset_path", "")
            for slide in draft.get("slides", [])
            if slide.get("asset_path")
        ]

        if not image_paths:
            warning("Draft has no rendered assets. Render it before publishing.")
            return None

        result = publish_cardnews_images(
            image_paths=image_paths,
            caption=str(draft.get("caption", draft.get("topic", ""))).strip(),
            interactive=interactive,
            platforms=draft.get("channels", self.channels),
            force_publish=force_publish,
        )
        if result:
            update_cardnews_draft(
                draft_id,
                {
                    "status": "published",
                    "published_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        return result
