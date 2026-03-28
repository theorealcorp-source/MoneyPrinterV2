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
from content_planner import generate_poster_outline
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

    @property
    def format_mode(self) -> str:
        return str(self.config.get("format", "carousel")).strip().lower() or "carousel"

    def list_drafts(self) -> list[dict]:
        return get_cardnews_drafts_for_profile(self.profile_id)

    def _draft_root(self, draft_id: str) -> str:
        return os.path.join(ROOT_DIR, ".mp", "cardnews", draft_id)

    def _emit_progress(
        self,
        progress_callback,
        *,
        stage: str,
        message: str,
        current: int | None = None,
        total: int | None = None,
        progress: int | None = None,
    ) -> None:
        if progress_callback is None:
            return

        computed_progress = progress
        if computed_progress is None and current is not None and total:
            computed_progress = int((current / max(total, 1)) * 100)

        progress_callback(
            {
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
                "progress": max(0, min(int(computed_progress or 0), 100)),
            }
        )

    def _run_rule_review(self, draft: dict) -> dict:
        issues = []
        slides = draft.get("slides", [])
        format_mode = str(draft.get("format", self.format_mode)).strip().lower() or "carousel"

        if format_mode == "poster":
            if len(slides) != 1:
                issues.append(f"Expected 1 poster slide but found {len(slides)}.")

            if slides:
                slide = slides[0]
                if str(slide.get("type", "")).strip().lower() != "poster":
                    issues.append("Poster draft must use slide type 'poster'.")

                title = str(slide.get("title", "")).strip()
                body = str(slide.get("body", "")).strip()
                poster_items = slide.get("poster_items", [])

                if not title:
                    issues.append("Poster headline is empty.")
                if not body:
                    issues.append("Poster subheadline is empty.")
                if len(title) > 64:
                    issues.append("Poster headline exceeds 64 characters.")
                if len(body) > 180:
                    issues.append("Poster subheadline exceeds 180 characters.")
                if not isinstance(poster_items, list) or not poster_items:
                    issues.append("Poster items are missing.")
                else:
                    expected_count = int(self.config.get("poster_item_count", 6))
                    if len(poster_items) != expected_count:
                        issues.append(
                            f"Expected {expected_count} poster items but found {len(poster_items)}."
                        )
                    for item_index, item in enumerate(poster_items, start=1):
                        label = str(item.get("label", "")).strip()
                        sublabel = str(item.get("sublabel", "")).strip()
                        visual_prompt = str(item.get("visual_prompt", "")).strip()
                        if not label:
                            issues.append(f"Poster item {item_index}: label is empty.")
                        if len(label) > 28:
                            issues.append(
                                f"Poster item {item_index}: label exceeds 28 characters."
                            )
                        if len(sublabel) > 44:
                            issues.append(
                                f"Poster item {item_index}: sublabel exceeds 44 characters."
                            )
                        if not visual_prompt:
                            issues.append(
                                f"Poster item {item_index}: visual prompt is empty."
                            )
                        if any(char in f"{label} {sublabel}" for char in ["#", "*", "_", "`"]):
                            issues.append(
                                f"Poster item {item_index}: contains markdown-like formatting."
                            )
                        if any(char.isdigit() for char in f"{label} {sublabel}"):
                            issues.append(
                                f"Poster item {item_index}: contains numeric claim, verify facts manually."
                            )

            if issues:
                return {
                    "status": "flag",
                    "summary": "Poster review found issues that should be checked.",
                    "issues": issues,
                }

            return {"status": "pass", "summary": "Poster rule-based review passed.", "issues": []}

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

    def _background_style_prompt(self) -> str:
        style = str(self.config.get("background_style", "editorial_abstract")).strip().lower()
        if style == "paper_layers":
            return (
                "Paper-cut editorial background, layered soft shadows, tactile material depth, "
                "calm premium magazine look, large clean negative space for overlay text."
            )
        if style == "minimal_gradient":
            return (
                "Minimal gradient editorial background, restrained shapes, smooth tonal transitions, "
                "high readability, clean premium composition with strong empty space."
            )

        return (
            "Editorial abstract background, geometric forms, subtle paper texture, balanced contrast, "
            "premium magazine composition, clear negative space for overlay text."
        )

    def _build_shared_background_prompt(self, draft: dict, variant: str) -> str:
        slides = draft.get("slides", [])
        style_prompt = self._background_style_prompt()
        topic = str(draft.get("topic", "")).strip()
        topic_context = " ".join(
            str(slide.get("title", "")).strip()
            for slide in slides[:3]
            if str(slide.get("title", "")).strip()
        )

        if variant == "primary":
            mood_prompt = (
                "Hero background for the opening and closing slides. Strong focal shape, more dramatic depth, "
                "confident visual rhythm."
            )
        else:
            mood_prompt = (
                "Support background for explanation slides. Quieter structure, cleaner reading field, "
                "less visual tension."
            )

        return (
            f"{style_prompt} {mood_prompt} "
            f"Card-news topic: {topic}. Context: {topic_context}. "
            f"Niche: {self.niche}. Language: {self.language}. "
            "No text, no letters, no numerals, no logos, no watermark, no UI, no collage."
        )

    def _build_poster_background_prompt(self, draft: dict) -> str:
        return (
            "Single-page infographic background, warm paper texture, light editorial illustration mood, "
            "soft abstract shapes, calm premium print feel, large clean negative space. "
            f"Topic: {str(draft.get('topic', '')).strip()}. "
            f"Niche: {self.niche}. Language: {self.language}. "
            "No text, no letters, no numerals, no logos, no watermark, no UI."
        )

    def _build_poster_item_prompt(self, item: dict, topic: str) -> str:
        label = str(item.get("label", "")).strip()
        sublabel = str(item.get("sublabel", "")).strip()
        user_prompt = str(item.get("visual_prompt", "")).strip()
        base_prompt = (
            "Single isolated editorial illustration, centered subject, plain light backdrop, "
            "warm travel-poster palette, clean silhouette, simple readable forms, no text, no letters, "
            "no numerals, no watermark."
        )
        return " ".join(
            part
            for part in [
                user_prompt,
                f"Topic: {topic}." if topic else "",
                f"Label: {label}." if label else "",
                f"Context: {sublabel}." if sublabel else "",
                base_prompt,
            ]
            if part
        )

    def _render_poster_assets(
        self,
        draft: dict,
        generated_dir: str,
        progress_callback=None,
    ) -> list[dict]:
        slides = draft.get("slides", [])
        if not slides:
            return []

        slide_copy = dict(slides[0])
        poster_items = []
        total_steps = len(slide_copy.get("poster_items", [])) + 2
        step = 1
        self._emit_progress(
            progress_callback,
            stage="backgrounds",
            message="Generating poster background",
            current=step,
            total=total_steps,
            progress=34,
        )
        slide_copy["background_path"] = (
            generate_image_asset(
                self._build_poster_background_prompt(draft),
                generated_dir,
                aspect_ratio="4:5",
                progress_callback=lambda event, step_index=step: self._emit_progress(
                    progress_callback,
                    stage="backgrounds",
                    message=f"Waiting for poster background ({event.get('elapsed_seconds', 0)}s)",
                    current=step_index,
                    total=total_steps,
                    progress=34,
                ),
            )
            or ""
        )
        step += 1

        for item_index, item in enumerate(slide_copy.get("poster_items", []), start=1):
            self._emit_progress(
                progress_callback,
                stage="illustrations",
                message=f"Generating poster illustration {item_index}/{len(slide_copy.get('poster_items', []))}",
                current=step,
                total=total_steps,
                progress=min(34 + step * 10, 82),
            )
            item_copy = dict(item)
            item_copy["illustration_path"] = (
                generate_image_asset(
                    self._build_poster_item_prompt(
                        item_copy,
                        str(draft.get("topic", "")).strip(),
                    ),
                    generated_dir,
                    aspect_ratio="1:1",
                    progress_callback=lambda event, step_index=step, current_index=item_index: self._emit_progress(
                        progress_callback,
                        stage="illustrations",
                        message=(
                            f"Waiting for illustration {current_index}/{len(slide_copy.get('poster_items', []))} "
                            f"({event.get('elapsed_seconds', 0)}s)"
                        ),
                        current=step_index,
                        total=total_steps,
                        progress=min(34 + step_index * 10, 82),
                    ),
                )
                or ""
            )
            poster_items.append(item_copy)
            step += 1

        slide_copy["poster_items"] = poster_items
        return [slide_copy]

    def _render_background_assets(
        self,
        draft: dict,
        generated_dir: str,
        progress_callback=None,
    ) -> list[dict]:
        if str(draft.get("format", self.format_mode)).strip().lower() == "poster":
            return self._render_poster_assets(draft, generated_dir, progress_callback=progress_callback)

        rendered_slides = []
        strategy = str(self.config.get("background_strategy", "deck_pair")).strip().lower()
        shared_backgrounds = {}

        if strategy == "shared_single":
            self._emit_progress(
                progress_callback,
                stage="backgrounds",
                message="Generating shared deck background",
                current=1,
                total=2,
                progress=36,
            )
            shared_backgrounds["shared"] = generate_image_asset(
                self._build_shared_background_prompt(draft, "primary"),
                generated_dir,
                aspect_ratio="4:5",
                progress_callback=lambda event: self._emit_progress(
                    progress_callback,
                    stage="backgrounds",
                    message=f"Waiting for shared background ({event.get('elapsed_seconds', 0)}s)",
                    current=1,
                    total=2,
                    progress=36,
                ),
            )
        elif strategy == "deck_pair":
            self._emit_progress(
                progress_callback,
                stage="backgrounds",
                message="Generating primary deck background",
                current=1,
                total=3,
                progress=32,
            )
            shared_backgrounds["primary"] = generate_image_asset(
                self._build_shared_background_prompt(draft, "primary"),
                generated_dir,
                aspect_ratio="4:5",
                progress_callback=lambda event: self._emit_progress(
                    progress_callback,
                    stage="backgrounds",
                    message=f"Waiting for primary background ({event.get('elapsed_seconds', 0)}s)",
                    current=1,
                    total=3,
                    progress=32,
                ),
            )
            self._emit_progress(
                progress_callback,
                stage="backgrounds",
                message="Generating support deck background",
                current=2,
                total=3,
                progress=48,
            )
            shared_backgrounds["support"] = generate_image_asset(
                self._build_shared_background_prompt(draft, "support"),
                generated_dir,
                aspect_ratio="4:5",
                progress_callback=lambda event: self._emit_progress(
                    progress_callback,
                    stage="backgrounds",
                    message=f"Waiting for support background ({event.get('elapsed_seconds', 0)}s)",
                    current=2,
                    total=3,
                    progress=48,
                ),
            )

        for slide in draft.get("slides", []):
            slide_copy = dict(slide)
            slide_type = str(slide.get("type", "")).strip().lower()

            if strategy == "shared_single":
                background_path = shared_backgrounds.get("shared")
            elif strategy == "deck_pair":
                bucket = "primary" if slide_type in {"cover", "quote", "cta"} else "support"
                background_path = shared_backgrounds.get(bucket)
            else:
                self._emit_progress(
                    progress_callback,
                    stage="backgrounds",
                    message=f"Generating slide background {slide_copy.get('index', len(rendered_slides) + 1)}/{len(draft.get('slides', []))}",
                    current=len(rendered_slides) + 1,
                    total=len(draft.get("slides", [])),
                    progress=min(30 + ((len(rendered_slides) + 1) * 8), 78),
                )
                background_path = generate_image_asset(
                    slide.get("visual_prompt", ""),
                    generated_dir,
                    aspect_ratio="4:5",
                    progress_callback=lambda event, slide_index=len(rendered_slides) + 1: self._emit_progress(
                        progress_callback,
                        stage="backgrounds",
                        message=f"Waiting for slide background {slide_index}/{len(draft.get('slides', []))} ({event.get('elapsed_seconds', 0)}s)",
                        current=slide_index,
                        total=len(draft.get("slides", [])),
                        progress=min(30 + (slide_index * 8), 78),
                    ),
                )

            slide_copy["background_path"] = background_path or ""
            rendered_slides.append(slide_copy)

        return rendered_slides

    def create_draft(
        self,
        topic_override: str | None = None,
        format_override: str | None = None,
    ) -> dict:
        """
        Create a new draft and persist it.
        """
        assert_folder_structure()

        topic = str(topic_override or "").strip()
        if not topic:
            topic = generate_topic_idea(self.niche, self.language)

        format_mode = str(format_override or self.format_mode).strip().lower() or self.format_mode
        if format_mode not in {"carousel", "poster"}:
            format_mode = self.format_mode

        if format_mode == "poster":
            outline = generate_poster_outline(
                topic=topic,
                language=self.language,
                item_count=int(self.config.get("poster_item_count", 6)),
            )
        else:
            outline = generate_cardnews_outline(
                topic=topic,
                language=self.language,
                slide_count=self.config["slides_per_post"],
            )

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        slides = []
        if format_mode == "poster":
            slides.append(
                {
                    "index": 1,
                    "type": "poster",
                    "eyebrow": "VISUAL GUIDE",
                    "title": str(outline.get("headline", outline["topic"])).strip(),
                    "body": str(outline.get("subheadline", outline["caption"])).strip(),
                    "highlight": "",
                    "bullets": [],
                    "visual_prompt": "",
                    "topic": outline["topic"],
                    "poster_items": [
                        {
                            **dict(item),
                            "index": item_index,
                            "illustration_path": "",
                        }
                        for item_index, item in enumerate(outline.get("items", []), start=1)
                    ],
                    "background_path": "",
                    "asset_path": "",
                }
            )
        else:
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
            "format": format_mode,
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

    def render_draft(self, draft_id: str, progress_callback=None) -> dict:
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

        self._emit_progress(
            progress_callback,
            stage="prepare-assets",
            message="Preparing image generation",
            progress=28,
        )
        rendered_slides = self._render_background_assets(
            draft,
            generated_dir,
            progress_callback=progress_callback,
        )

        has_visual_assets = any(slide.get("background_path", "") for slide in rendered_slides)
        if not has_visual_assets:
            has_visual_assets = any(
                item.get("illustration_path", "")
                for slide in rendered_slides
                for item in slide.get("poster_items", [])
            )

        if not has_visual_assets:
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

        self._emit_progress(
            progress_callback,
            stage="render",
            message="Rendering final PNG assets",
            progress=88,
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
        self._emit_progress(
            progress_callback,
            stage="done",
            message="Draft render completed",
            progress=100,
        )
        info(f"Rendered {len(asset_paths)} slides for draft {draft_id}.")
        return updated

    def prepare_draft(
        self,
        topic_override: str | None = None,
        format_override: str | None = None,
    ) -> dict:
        """
        Create, review and render a draft in sequence.
        """
        draft = self.create_draft(topic_override=topic_override, format_override=format_override)
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
