import json
import re

from config import get_verbose
from llm_provider import generate_text
from status import info
from status import warning


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
      "title": "string",
      "body": "string",
      "visual_prompt": "string"
    }}
  ]
}}

Rules:
- Output language: {language}
- Topic: {topic}
- Create exactly {slide_count} slides
- Each title must be <= 55 characters
- Each body must be 1-2 short sentences, <= 220 characters
- Slide 1 should hook the reader
- Middle slides should explain or break down the topic
- Final slide should end with a practical takeaway
- visual_prompt must describe a single striking illustration background for that slide
- Do not use markdown
- Do not include extra keys
""".strip()

    outline = generate_json(prompt, model_name=model_name)
    slides = outline.get("slides", []) if isinstance(outline, dict) else []

    normalized_slides = []
    for slide in slides[:slide_count]:
        normalized_slides.append(
            {
                "title": str(slide.get("title", "")).strip(),
                "body": str(slide.get("body", "")).strip(),
                "visual_prompt": str(slide.get("visual_prompt", "")).strip(),
            }
        )

    while len(normalized_slides) < slide_count:
        normalized_slides.append(
            {
                "title": f"{topic} {len(normalized_slides) + 1}",
                "body": "",
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
