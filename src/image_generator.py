import base64
import copy
import json
import os
import time
from uuid import uuid4

import requests

from config import get_image_generation_config
from config import get_image_provider
from config import get_verbose
from status import warning


ASPECT_RATIO_DIMENSIONS = {
    "1:1": (1024, 1024),
    "4:5": (1024, 1280),
    "5:4": (1280, 1024),
    "3:4": (960, 1280),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "3:2": (1216, 832),
    "2:3": (832, 1216),
}


def _persist_image_bytes(image_bytes: bytes, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    image_path = os.path.join(output_dir, f"{uuid4()}.png")
    with open(image_path, "wb") as image_file:
        image_file.write(image_bytes)
    return image_path


def _render_workflow_placeholders(node: object, variables: dict) -> object:
    if isinstance(node, dict):
        return {key: _render_workflow_placeholders(value, variables) for key, value in node.items()}

    if isinstance(node, list):
        return [_render_workflow_placeholders(item, variables) for item in node]

    if isinstance(node, str):
        stripped = node.strip()
        if stripped.startswith("{{") and stripped.endswith("}}") and stripped.count("{{") == 1:
            key = stripped[2:-2].strip()
            if key in variables:
                return variables[key]

        rendered = node
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    return node


def _load_comfyui_workflow(variables: dict, comfyui_config: dict) -> dict:
    workflow_path = comfyui_config.get("workflow_path", "")
    if workflow_path:
        expanded_path = os.path.expanduser(workflow_path)
        if not os.path.exists(expanded_path):
            raise RuntimeError(f"ComfyUI workflow file was not found: {expanded_path}")

        with open(expanded_path, "r", encoding="utf-8") as handle:
            workflow = json.load(handle)
        return _render_workflow_placeholders(workflow, variables)

    checkpoint = comfyui_config.get("checkpoint", "")
    if not checkpoint:
        raise RuntimeError(
            "ComfyUI image generation requires either comfyui.workflow_path or comfyui.checkpoint."
        )

    return {
        "1": {
            "inputs": {
                "ckpt_name": checkpoint,
            },
            "class_type": "CheckpointLoaderSimple",
        },
        "2": {
            "inputs": {
                "text": variables["prompt"],
                "clip": ["1", 1],
            },
            "class_type": "CLIPTextEncode",
        },
        "3": {
            "inputs": {
                "text": variables["negative_prompt"],
                "clip": ["1", 1],
            },
            "class_type": "CLIPTextEncode",
        },
        "4": {
            "inputs": {
                "width": variables["width"],
                "height": variables["height"],
                "batch_size": 1,
            },
            "class_type": "EmptyLatentImage",
        },
        "5": {
            "inputs": {
                "seed": variables["seed"],
                "steps": variables["steps"],
                "cfg": variables["cfg"],
                "sampler_name": variables["sampler_name"],
                "scheduler": variables["scheduler"],
                "denoise": 1,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
            "class_type": "KSampler",
        },
        "6": {
            "inputs": {
                "samples": ["5", 0],
                "vae": ["1", 2],
            },
            "class_type": "VAEDecode",
        },
        "7": {
            "inputs": {
                "filename_prefix": variables["filename_prefix"],
                "images": ["6", 0],
            },
            "class_type": "SaveImage",
        },
    }


def _generate_with_gemini(prompt: str, output_dir: str, aspect_ratio: str, image_config: dict) -> str | None:
    api_key = image_config["gemini"].get("api_key", "")
    if not api_key:
        return None

    endpoint = (
        f"{image_config['gemini']['api_base_url'].rstrip('/')}/models/"
        f"{image_config['gemini']['model']}:generateContent"
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
            warning(f"Gemini image generation failed: {exc}")
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
                return _persist_image_bytes(base64.b64decode(data), output_dir)

    if get_verbose():
        warning("Gemini image generation returned no image payload.")
    return None


def _poll_comfyui_history(base_url: str, prompt_id: str, timeout_seconds: int) -> dict | None:
    deadline = time.time() + timeout_seconds
    history_url = f"{base_url.rstrip('/')}/history/{prompt_id}"

    while time.time() < deadline:
        response = requests.get(history_url, timeout=30)
        response.raise_for_status()
        history = response.json()
        prompt_history = history.get(prompt_id, {})
        outputs = prompt_history.get("outputs", {})
        if outputs:
            return prompt_history
        time.sleep(1.2)

    return None


def _generate_with_comfyui(prompt: str, output_dir: str, aspect_ratio: str, image_config: dict) -> str | None:
    comfyui_config = copy.deepcopy(image_config["comfyui"])
    width, height = ASPECT_RATIO_DIMENSIONS.get(aspect_ratio, (1024, 1024))
    seed = int(uuid4().int % 2_147_483_647)
    filename_prefix = "MoneyPrinter/cardnews"

    variables = {
        "prompt": prompt,
        "negative_prompt": comfyui_config["negative_prompt"],
        "width": width,
        "height": height,
        "steps": comfyui_config["steps"],
        "cfg": comfyui_config["cfg"],
        "seed": seed,
        "sampler_name": comfyui_config["sampler_name"],
        "scheduler": comfyui_config["scheduler"],
        "checkpoint": comfyui_config["checkpoint"],
        "filename_prefix": filename_prefix,
    }

    try:
        workflow = _load_comfyui_workflow(variables, comfyui_config)
        response = requests.post(
            f"{comfyui_config['base_url'].rstrip('/')}/prompt",
            json={"prompt": workflow, "client_id": str(uuid4())},
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        prompt_id = str(body.get("prompt_id", "")).strip()
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt_id. Response: {body}")

        history = _poll_comfyui_history(
            comfyui_config["base_url"],
            prompt_id,
            comfyui_config["timeout_seconds"],
        )
        if history is None:
            raise RuntimeError(
                f"ComfyUI timed out after {comfyui_config['timeout_seconds']} seconds."
            )

        for output in history.get("outputs", {}).values():
            for image in output.get("images", []):
                view_response = requests.get(
                    f"{comfyui_config['base_url'].rstrip('/')}/view",
                    params={
                        "filename": image.get("filename", ""),
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                    timeout=60,
                )
                view_response.raise_for_status()
                return _persist_image_bytes(view_response.content, output_dir)
    except Exception as exc:
        if get_verbose():
            warning(f"ComfyUI image generation failed: {exc}")
        return None

    if get_verbose():
        warning("ComfyUI image generation returned no images.")
    return None


def generate_image_asset(
    prompt: str,
    output_dir: str,
    aspect_ratio: str = "4:5",
    provider: str | None = None,
) -> str | None:
    """
    Generate an image using the configured provider.

    Args:
        prompt (str): Image prompt
        output_dir (str): Directory for the generated image
        aspect_ratio (str): Requested aspect ratio
        provider (str | None): Optional provider override

    Returns:
        path (str | None): Absolute file path when generation succeeds
    """
    image_config = get_image_generation_config()
    selected_provider = str(provider or get_image_provider()).strip().lower()

    if selected_provider == "none":
        return None

    if selected_provider == "gemini":
        return _generate_with_gemini(prompt, output_dir, aspect_ratio, image_config)

    if selected_provider == "comfyui":
        return _generate_with_comfyui(prompt, output_dir, aspect_ratio, image_config)

    if get_verbose():
        warning(f"Unknown image generation provider: {selected_provider}")
    return None


def generate_nanobanana_image(
    prompt: str,
    output_dir: str,
    aspect_ratio: str = "4:5",
) -> str | None:
    """
    Backwards-compatible wrapper for legacy Gemini image generation.
    """
    return _generate_with_gemini(prompt, output_dir, aspect_ratio, get_image_generation_config())
