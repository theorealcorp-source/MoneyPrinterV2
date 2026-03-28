import base64
import os
from uuid import uuid4

import requests

from config import get_nanobanana2_api_base_url
from config import get_nanobanana2_api_key
from config import get_nanobanana2_model
from config import get_verbose
from status import warning


def generate_nanobanana_image(
    prompt: str,
    output_dir: str,
    aspect_ratio: str = "4:5",
) -> str | None:
    """
    Generate a single image via the configured Gemini image endpoint.

    Args:
        prompt (str): Image prompt
        output_dir (str): Directory for the generated image
        aspect_ratio (str): Requested aspect ratio

    Returns:
        path (str | None): Absolute file path when generation succeeds
    """
    api_key = get_nanobanana2_api_key()
    if not api_key:
        return None

    os.makedirs(output_dir, exist_ok=True)

    endpoint = (
        f"{get_nanobanana2_api_base_url().rstrip('/')}/models/"
        f"{get_nanobanana2_model()}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio},
        },
    }

    try:
        response = requests.post(
            endpoint,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        if get_verbose():
            warning(f"Image generation failed: {exc}")
        return None

    for candidate in body.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue

            data = inline_data.get("data")
            mime_type = inline_data.get("mimeType") or inline_data.get("mime_type", "")
            if data and str(mime_type).startswith("image/"):
                image_path = os.path.join(output_dir, f"{uuid4()}.png")
                with open(image_path, "wb") as image_file:
                    image_file.write(base64.b64decode(data))
                return image_path

    if get_verbose():
        warning("Image generation returned no image payload.")
    return None
