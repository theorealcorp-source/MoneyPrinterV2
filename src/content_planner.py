import json
import re

from config import get_verbose
from llm_provider import generate_text
from status import info
from status import warning


CARDNEWS_SLIDE_TYPES = {"cover", "insight", "list", "stat", "quote", "cta"}
DEFAULT_EYEBROWS = {
    "cover": "SWIPE GUIDE",
    "insight": "WHY IT MATTERS",
    "list": "QUICK CHECK",
    "stat": "KEY POINT",
    "quote": "ONE LINE",
    "cta": "NEXT STEP",
}


def _strip_code_fences(raw_text: str) -> str:
    cleaned = str(raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _extract_json_blob(raw_text: str) -> str:
    cleaned = _strip_code_fences(raw_text)
    candidates = [("{", "}"), ("[", "]")]

    for opener, closer in candidates:
        start_index = cleaned.find(opener)
        end_index = cleaned.rfind(closer)
        if start_index != -1 and end_index != -1 and end_index > start_index:
            return cleaned[start_index : end_index + 1]

    return cleaned


def _default_slide_type(index: int, slide_count: int) -> str:
    if index == 0:
        return "cover"
    if index == slide_count - 1:
        return "cta"

    middle_types = ["insight", "list", "stat", "quote"]
    return middle_types[(index - 1) % len(middle_types)]


def _derive_bullets_from_text(text: str) -> list[str]:
    chunks = re.split(r"(?:\n|[.!?]|(?:\s*[-•]\s*))", str(text or ""))
    bullets = []

    for chunk in chunks:
        normalized = " ".join(chunk.strip().split())
        if normalized and normalized not in bullets:
            bullets.append(normalized)
        if len(bullets) == 3:
            break

    return bullets


def generate_json(prompt: str, model_name: str = None, max_attempts: int = 3):
    """
    Generate a JSON payload from the active LLM with a small retry loop.

    Args:
        prompt (str): Prompt instructing the model to return JSON
        model_name (str | None): Optional model override
        max_attempts (int): Parse retries

    Returns:
        payload (dict | list): Parsed JSON payload
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        completion = generate_text(prompt, model_name=model_name)
        payload_text = _extract_json_blob(completion)

        try:
            return json.loads(payload_text)
        except json.JSONDecodeError as exc:
            last_error = exc
            if get_verbose():
                warning(
                    f"Structured generation returned invalid JSON on attempt {attempt}: {exc}"
                )

    raise RuntimeError(f"Failed to parse JSON from model output: {last_error}")


def generate_topic_idea(niche: str, language: str, model_name: str = None) -> str:
    """
    Generate a single card-news topic idea.

    Args:
        niche (str): Editorial niche
        language (str): Output language
        model_name (str | None): Optional model override

    Returns:
        topic (str): Generated topic
    """
    completion = generate_text(
        (
            f"Generate one highly specific card-news topic about '{niche}'. "
            f"Write it in {language}. "
            "Keep it under 14 words. Only return the topic sentence."
        ),
        model_name=model_name,
    )

    return _strip_code_fences(completion).replace('"', "").strip()


def generate_cardnews_outline(
    topic: str,
    language: str,
    slide_count: int,
    model_name: str = None,
) -> dict:
    """
    Generate a structured card-news outline.

    Returns:
        outline (dict): Topic, caption and slides
    """
    if get_verbose():
        info(f"Generating card-news outline for topic: {topic}")

    prompt = f"""
You are creating a social-media card-news carousel.
Return only valid JSON with this exact shape:
{{
  "topic": "string",
  "caption": "string",
  "slides": [
    {{
      "type": "cover|insight|list|stat|quote|cta",
      "eyebrow": "string",
      "title": "string",
      "body": "string",
      "highlight": "string",
      "bullets": ["string"],
      "visual_prompt": "string"
    }}
  ]
}}

Rules:
- Output language: {language}
- Topic: {topic}
- Create exactly {slide_count} slides
- Slide 1 type must be "cover"
- Final slide type must be "cta"
- Use at least one "list" or "stat" slide in the middle
- Each title must be <= 55 characters
- Each body must be 1-2 short sentences, <= 220 characters
- Each eyebrow must be <= 18 characters
- Each highlight must be <= 28 characters
- bullets must be 0-3 short items and only included when useful
- Slide 1 should hook the reader
- Middle slides should explain or break down the topic
- Final slide should end with a practical takeaway
- Vary the slide rhythm so the carousel does not feel repetitive
- visual_prompt must describe a single striking illustration background for that slide
- Do not use markdown
- Do not include extra keys
""".strip()

    outline = generate_json(prompt, model_name=model_name)
    slides = outline.get("slides", []) if isinstance(outline, dict) else []

    normalized_slides = []
    for index, slide in enumerate(slides[:slide_count]):
        slide_type = str(slide.get("type", "")).strip().lower()
        if slide_type not in CARDNEWS_SLIDE_TYPES:
            slide_type = _default_slide_type(index, slide_count)

        title = str(slide.get("title", "")).strip()
        body = str(slide.get("body", "")).strip()
        highlight = str(slide.get("highlight", "")).strip()
        eyebrow = str(slide.get("eyebrow", "")).strip() or DEFAULT_EYEBROWS[slide_type]

        bullets = slide.get("bullets", [])
        if not isinstance(bullets, list):
            bullets = []

        normalized_bullets = []
        for bullet in bullets[:3]:
            normalized = " ".join(str(bullet).strip().split())
            if normalized:
                normalized_bullets.append(normalized)

        if slide_type in {"list", "cta"} and not normalized_bullets:
            normalized_bullets = _derive_bullets_from_text(body)

        if slide_type in {"stat", "quote"} and not highlight:
            highlight = title or body[:28]

        normalized_slides.append(
            {
                "type": slide_type,
                "eyebrow": eyebrow[:18],
                "title": title,
                "body": body,
                "highlight": highlight[:28],
                "bullets": normalized_bullets[:3],
                "visual_prompt": str(slide.get("visual_prompt", "")).strip(),
            }
        )

    while len(normalized_slides) < slide_count:
        fallback_index = len(normalized_slides)
        slide_type = _default_slide_type(fallback_index, slide_count)
        fallback_body = ""
        fallback_bullets = []
        if slide_type in {"list", "cta"}:
            fallback_body = "Keep the message short and easy to scan."
            fallback_bullets = [
                "Use one clear takeaway.",
                "Keep the layout airy.",
                "End with a practical next step.",
            ]

        normalized_slides.append(
            {
                "type": slide_type,
                "eyebrow": DEFAULT_EYEBROWS[slide_type],
                "title": f"{topic} {len(normalized_slides) + 1}",
                "body": fallback_body,
                "highlight": topic[:28],
                "bullets": fallback_bullets,
                "visual_prompt": f"Editorial illustration about {topic}",
            }
        )

    return {
        "topic": str(outline.get("topic", topic)).strip() or topic,
        "caption": str(outline.get("caption", topic)).strip() or topic,
        "slides": normalized_slides,
    }


def review_cardnews_draft(draft: dict, language: str, model_name: str = None) -> dict:
    """
    Ask the model to critique a generated draft.

    Returns:
        review (dict): Review payload
    """
    prompt = f"""
Review the following card-news draft and return only valid JSON:
{{
  "status": "pass|flag|block",
  "summary": "string",
  "issues": ["string"]
}}

Review criteria:
- clarity
- flow across slides
- clickbait risk
- unverifiable factual claims
- visual rhythm across slide types
- whether the ending gives a practical takeaway

Language: {language}
Draft:
{json.dumps(draft, ensure_ascii=False)}
""".strip()

    review = generate_json(prompt, model_name=model_name)
    issues = review.get("issues", []) if isinstance(review, dict) else []

    return {
        "status": str(review.get("status", "flag")).strip().lower() or "flag",
        "summary": str(review.get("summary", "")).strip(),
        "issues": [str(issue).strip() for issue in issues if str(issue).strip()],
    }
