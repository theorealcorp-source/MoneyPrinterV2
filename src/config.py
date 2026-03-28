import os
import sys
import json
import shutil

try:
    import srt_equalizer
except ModuleNotFoundError:  # pragma: no cover - optional dependency in tests
    srt_equalizer = None

try:
    from termcolor import colored
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs
    def colored(message: str, *_args, **_kwargs) -> str:
        return str(message)

ROOT_DIR = os.path.dirname(sys.path[0])
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(ROOT_DIR, "config.example.json")


def ensure_config_file() -> None:
    """
    Ensure a root-level config.json exists.

    Returns:
        None
    """
    if os.path.exists(CONFIG_PATH):
        return

    if os.path.exists(CONFIG_EXAMPLE_PATH):
        shutil.copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        return

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump({}, file, indent=2)


def _read_config() -> dict:
    """
    Read config.json with a safe empty fallback.

    Returns:
        config (dict): Parsed configuration
    """
    ensure_config_file()

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        parsed = json.load(file)

    return parsed if isinstance(parsed, dict) else {}


def _merge_dict(base: dict, updates: dict) -> dict:
    merged = dict(base)

    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value

    return merged


def get_full_config() -> dict:
    """
    Return the full parsed config payload.

    Returns:
        config (dict): Parsed configuration
    """
    return _read_config()


def update_config(updates: dict) -> dict:
    """
    Deep-merge updates into config.json and persist them.

    Args:
        updates (dict): Partial config update

    Returns:
        config (dict): Persisted configuration
    """
    current = _read_config()
    merged = _merge_dict(current, updates or {})

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(merged, file, indent=2)

    return merged

def assert_folder_structure() -> None:
    """
    Make sure that the nessecary folder structure is present.

    Returns:
        None
    """
    # Create the .mp folder
    if not os.path.exists(os.path.join(ROOT_DIR, ".mp")):
        if get_verbose():
            print(colored(f"=> Creating .mp folder at {os.path.join(ROOT_DIR, '.mp')}", "green"))
        os.makedirs(os.path.join(ROOT_DIR, ".mp"))

def get_first_time_running() -> bool:
    """
    Checks if the program is running for the first time by checking if .mp folder exists.

    Returns:
        exists (bool): True if the program is running for the first time, False otherwise
    """
    return not os.path.exists(os.path.join(ROOT_DIR, ".mp"))

def get_email_credentials() -> dict:
    """
    Gets the email credentials from the config file.

    Returns:
        credentials (dict): The email credentials
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["email"]

def get_verbose() -> bool:
    """
    Gets the verbose flag from the config file.

    Returns:
        verbose (bool): The verbose flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["verbose"]

def get_firefox_profile_path() -> str:
    """
    Gets the path to the Firefox profile.

    Returns:
        path (str): The path to the Firefox profile
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["firefox_profile"]

def get_headless() -> bool:
    """
    Gets the headless flag from the config file.

    Returns:
        headless (bool): The headless flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["headless"]

def get_ollama_base_url() -> str:
    """
    Gets the Ollama base URL.

    Returns:
        url (str): The Ollama base URL
    """
    return str(_read_config().get("ollama_base_url", "http://127.0.0.1:11434")).strip() or "http://127.0.0.1:11434"

def get_ollama_model() -> str:
    """
    Gets the Ollama model name from the config file.

    Returns:
        model (str): The Ollama model name, or empty string if not set.
    """
    return str(_read_config().get("ollama_model", "")).strip()


def get_llm_provider() -> str:
    """
    Gets the active LLM provider.

    Returns:
        provider (str): Provider identifier
    """
    supported_providers = {"ollama", "lmstudio", "openai", "gemini"}
    provider = str(_read_config().get("llm_provider", "ollama")).strip().lower()
    return provider if provider in supported_providers else "ollama"


def get_llm_model() -> str:
    """
    Gets the active model name for the selected provider.

    Returns:
        model (str): Model identifier
    """
    config_json = _read_config()
    generic_model = str(config_json.get("llm_model", "")).strip()
    if generic_model:
        return generic_model

    provider = get_llm_provider()
    if provider == "ollama":
        return get_ollama_model()
    if provider in {"lmstudio", "openai"}:
        return get_openai_model()
    if provider == "gemini":
        return get_gemini_model()

    return ""


def get_openai_base_url() -> str:
    """
    Gets the OpenAI-compatible base URL.

    Returns:
        base_url (str): Base URL
    """
    config_json = _read_config()
    configured = str(
        config_json.get("openai_base_url", os.environ.get("OPENAI_BASE_URL", ""))
    ).strip()

    if configured:
        return configured

    if get_llm_provider() == "lmstudio":
        return "http://127.0.0.1:1234/v1"

    return "https://api.openai.com/v1"


def get_openai_api_key() -> str:
    """
    Gets the OpenAI-compatible API key.

    Returns:
        api_key (str): API key or local placeholder for LM Studio
    """
    config_json = _read_config()
    configured = str(
        config_json.get("openai_api_key", os.environ.get("OPENAI_API_KEY", ""))
    ).strip()

    if configured:
        return configured

    if get_llm_provider() == "lmstudio":
        return "lm-studio"

    return ""


def get_openai_model() -> str:
    """
    Gets the OpenAI-compatible model name.

    Returns:
        model (str): Model name
    """
    config_json = _read_config()
    return str(config_json.get("openai_model", "")).strip()


def get_gemini_api_base_url() -> str:
    """
    Gets the Gemini text API base URL.

    Returns:
        base_url (str): Base URL
    """
    config_json = _read_config()
    return str(
        config_json.get(
            "gemini_api_base_url",
            "https://generativelanguage.googleapis.com/v1beta",
        )
    ).strip()


def get_gemini_api_key() -> str:
    """
    Gets the Gemini API key.

    Returns:
        api_key (str): Gemini API key
    """
    config_json = _read_config()
    configured = str(config_json.get("gemini_api_key", "")).strip()
    return configured or os.environ.get("GEMINI_API_KEY", "").strip()


def get_gemini_model() -> str:
    """
    Gets the Gemini model name.

    Returns:
        model (str): Gemini model
    """
    config_json = _read_config()
    return str(config_json.get("gemini_model", "gemini-2.5-flash")).strip() or "gemini-2.5-flash"

def get_twitter_language() -> str:
    """
    Gets the Twitter language from the config file.

    Returns:
        language (str): The Twitter language
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["twitter_language"]

def get_nanobanana2_api_base_url() -> str:
    """
    Gets the Nano Banana 2 (Gemini image) API base URL.

    Returns:
        url (str): API base URL
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get(
            "nanobanana2_api_base_url",
            "https://generativelanguage.googleapis.com/v1beta",
        )

def get_nanobanana2_api_key() -> str:
    """
    Gets the Nano Banana 2 API key.

    Returns:
        key (str): API key
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        configured = json.load(file).get("nanobanana2_api_key", "")
        return configured or os.environ.get("GEMINI_API_KEY", "")

def get_nanobanana2_model() -> str:
    """
    Gets the Nano Banana 2 model name.

    Returns:
        model (str): Model name
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("nanobanana2_model", "gemini-3.1-flash-image-preview")

def get_nanobanana2_aspect_ratio() -> str:
    """
    Gets the aspect ratio for Nano Banana 2 image generation.

    Returns:
        ratio (str): Aspect ratio
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("nanobanana2_aspect_ratio", "9:16")


def get_image_provider() -> str:
    """
    Gets the configured image generation provider.

    Returns:
        provider (str): Supported provider identifier
    """
    image_config = _read_config().get("image_generation", {})
    if not isinstance(image_config, dict):
        image_config = {}

    provider = str(image_config.get("provider", "gemini")).strip().lower()
    supported = {"none", "gemini", "comfyui"}
    return provider if provider in supported else "gemini"


def get_image_generation_config() -> dict:
    """
    Gets the image generation configuration with safe defaults.

    Returns:
        config (dict): Sanitized image generation settings
    """
    defaults = {
        "provider": "gemini",
        "gemini": {
            "api_base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": "",
            "model": "gemini-3.1-flash-image-preview",
            "aspect_ratio": "9:16",
        },
        "comfyui": {
            "base_url": "http://127.0.0.1:8188",
            "workflow_path": "",
            "checkpoint": "",
            "negative_prompt": "low quality, blurry, distorted, watermark, logo, text",
            "steps": 8,
            "cfg": 4.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "timeout_seconds": 180,
        },
    }

    raw_root = _read_config()
    raw_image_config = raw_root.get("image_generation", {})
    if not isinstance(raw_image_config, dict):
        raw_image_config = {}

    raw_comfyui = raw_image_config.get("comfyui", {})
    if not isinstance(raw_comfyui, dict):
        raw_comfyui = {}

    try:
        comfyui_steps = int(raw_comfyui.get("steps", defaults["comfyui"]["steps"]))
    except (TypeError, ValueError):
        comfyui_steps = defaults["comfyui"]["steps"]

    try:
        comfyui_cfg = float(raw_comfyui.get("cfg", defaults["comfyui"]["cfg"]))
    except (TypeError, ValueError):
        comfyui_cfg = defaults["comfyui"]["cfg"]

    try:
        comfyui_timeout = int(
            raw_comfyui.get("timeout_seconds", defaults["comfyui"]["timeout_seconds"])
        )
    except (TypeError, ValueError):
        comfyui_timeout = defaults["comfyui"]["timeout_seconds"]

    provider = str(raw_image_config.get("provider", defaults["provider"])).strip().lower()
    if provider not in {"none", "gemini", "comfyui"}:
        provider = defaults["provider"]

    return {
        "provider": provider,
        "gemini": {
            "api_base_url": str(
                raw_root.get("nanobanana2_api_base_url", defaults["gemini"]["api_base_url"])
            ).strip()
            or defaults["gemini"]["api_base_url"],
            "api_key": str(raw_root.get("nanobanana2_api_key", "")).strip()
            or os.environ.get("GEMINI_API_KEY", ""),
            "model": str(raw_root.get("nanobanana2_model", defaults["gemini"]["model"])).strip()
            or defaults["gemini"]["model"],
            "aspect_ratio": str(
                raw_root.get("nanobanana2_aspect_ratio", defaults["gemini"]["aspect_ratio"])
            ).strip()
            or defaults["gemini"]["aspect_ratio"],
        },
        "comfyui": {
            "base_url": str(raw_comfyui.get("base_url", defaults["comfyui"]["base_url"])).strip()
            or defaults["comfyui"]["base_url"],
            "workflow_path": str(
                raw_comfyui.get("workflow_path", defaults["comfyui"]["workflow_path"])
            ).strip(),
            "checkpoint": str(
                raw_comfyui.get("checkpoint", defaults["comfyui"]["checkpoint"])
            ).strip(),
            "negative_prompt": str(
                raw_comfyui.get("negative_prompt", defaults["comfyui"]["negative_prompt"])
            ).strip()
            or defaults["comfyui"]["negative_prompt"],
            "steps": max(1, min(comfyui_steps, 50)),
            "cfg": max(1.0, min(comfyui_cfg, 20.0)),
            "sampler_name": str(
                raw_comfyui.get("sampler_name", defaults["comfyui"]["sampler_name"])
            ).strip()
            or defaults["comfyui"]["sampler_name"],
            "scheduler": str(
                raw_comfyui.get("scheduler", defaults["comfyui"]["scheduler"])
            ).strip()
            or defaults["comfyui"]["scheduler"],
            "timeout_seconds": max(10, min(comfyui_timeout, 900)),
        },
    }

def get_threads() -> int:
    """
    Gets the amount of threads to use for example when writing to a file with MoviePy.

    Returns:
        threads (int): Amount of threads
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["threads"]
    
def get_zip_url() -> str:
    """
    Gets the URL to the zip file containing the songs.

    Returns:
        url (str): The URL to the zip file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["zip_url"]

def get_is_for_kids() -> bool:
    """
    Gets the is for kids flag from the config file.

    Returns:
        is_for_kids (bool): The is for kids flag
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["is_for_kids"]

def get_google_maps_scraper_zip_url() -> str:
    """
    Gets the URL to the zip file containing the Google Maps scraper.

    Returns:
        url (str): The URL to the zip file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["google_maps_scraper"]

def get_google_maps_scraper_niche() -> str:
    """
    Gets the niche for the Google Maps scraper.

    Returns:
        niche (str): The niche
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["google_maps_scraper_niche"]

def get_scraper_timeout() -> int:
    """
    Gets the timeout for the scraper.

    Returns:
        timeout (int): The timeout
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["scraper_timeout"] or 300

def get_outreach_message_subject() -> str:
    """
    Gets the outreach message subject.

    Returns:
        subject (str): The outreach message subject
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["outreach_message_subject"]
    
def get_outreach_message_body_file() -> str:
    """
    Gets the outreach message body file.

    Returns:
        file (str): The outreach message body file
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["outreach_message_body_file"]

def get_tts_voice() -> str:
    """
    Gets the TTS voice from the config file.

    Returns:
        voice (str): The TTS voice
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("tts_voice", "Jasper")

def get_assemblyai_api_key() -> str:
    """
    Gets the AssemblyAI API key.

    Returns:
        key (str): The AssemblyAI API key
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["assembly_ai_api_key"]

def get_stt_provider() -> str:
    """
    Gets the configured STT provider.

    Returns:
        provider (str): The STT provider
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("stt_provider", "local_whisper")

def get_whisper_model() -> str:
    """
    Gets the local Whisper model name.

    Returns:
        model (str): Whisper model name
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("whisper_model", "base")

def get_whisper_device() -> str:
    """
    Gets the target device for Whisper inference.

    Returns:
        device (str): Whisper device
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("whisper_device", "auto")

def get_whisper_compute_type() -> str:
    """
    Gets the compute type for Whisper inference.

    Returns:
        compute_type (str): Whisper compute type
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file).get("whisper_compute_type", "int8")
    
def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
    """
    Equalizes the subtitles in a SRT file.

    Args:
        srt_path (str): The path to the SRT file
        max_chars (int): The maximum amount of characters in a subtitle

    Returns:
        None
    """
    if srt_equalizer is None:
        return

    srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)
    
def get_font() -> str:
    """
    Gets the font from the config file.

    Returns:
        font (str): The font
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["font"]

def get_fonts_dir() -> str:
    """
    Gets the fonts directory.

    Returns:
        dir (str): The fonts directory
    """
    return os.path.join(ROOT_DIR, "fonts")

def get_imagemagick_path() -> str:
    """
    Gets the path to ImageMagick.

    Returns:
        path (str): The path to ImageMagick
    """
    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        return json.load(file)["imagemagick_path"]

def get_script_sentence_length() -> int:
    """
    Gets the forced script's sentence length.
    In case there is no sentence length in config, returns 4 when none

    Returns:
        length (int): Length of script's sentence
    """
    config_json = _read_config()
    if config_json.get("script_sentence_length") is not None:
        return config_json["script_sentence_length"]

    return 4

def get_post_bridge_config() -> dict:
    """
    Gets the Post Bridge configuration with safe defaults.

    Returns:
        config (dict): Sanitized Post Bridge configuration
    """
    defaults = {
        "enabled": False,
        "api_key": "",
        "platforms": ["tiktok", "instagram"],
        "account_ids": [],
        "auto_crosspost": False,
    }
    supported_platforms = {"tiktok", "instagram"}

    with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
        config_json = json.load(file)

    raw_config = config_json.get("post_bridge", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    raw_platforms = raw_config.get("platforms")
    normalized_platforms = []
    seen_platforms = set()

    if raw_platforms is None:
        normalized_platforms = defaults["platforms"].copy()
    elif isinstance(raw_platforms, list):
        for platform in raw_platforms:
            normalized_platform = str(platform).strip().lower()
            if (
                normalized_platform in supported_platforms
                and normalized_platform not in seen_platforms
            ):
                normalized_platforms.append(normalized_platform)
                seen_platforms.add(normalized_platform)
    else:
        normalized_platforms = []

    raw_account_ids = raw_config.get("account_ids", defaults["account_ids"])
    normalized_account_ids = []
    if isinstance(raw_account_ids, list):
        for account_id in raw_account_ids:
            try:
                normalized_account_ids.append(int(account_id))
            except (TypeError, ValueError):
                continue

    api_key = str(raw_config.get("api_key", "")).strip()
    if not api_key:
        api_key = os.environ.get("POST_BRIDGE_API_KEY", "").strip()

    return {
        "enabled": bool(raw_config.get("enabled", defaults["enabled"])),
        "api_key": api_key,
        "platforms": normalized_platforms,
        "account_ids": normalized_account_ids,
        "auto_crosspost": bool(
            raw_config.get("auto_crosspost", defaults["auto_crosspost"])
        ),
    }


def get_cardnews_config() -> dict:
    """
    Gets the CardNews configuration with safe defaults.

    Returns:
        config (dict): Sanitized CardNews configuration
    """
    defaults = {
        "slides_per_post": 6,
        "review_required": True,
        "default_channels": ["instagram"],
        "render_width": 1080,
        "render_height": 1350,
        "background_strategy": "deck_pair",
        "background_style": "editorial_abstract",
    }
    supported_channels = {"instagram", "tiktok"}
    supported_background_strategies = {"per_slide", "deck_pair", "shared_single"}
    supported_background_styles = {"editorial_abstract", "paper_layers", "minimal_gradient"}

    raw_config = _read_config().get("cardnews", {})
    if not isinstance(raw_config, dict):
        raw_config = {}

    raw_channels = raw_config.get("default_channels", defaults["default_channels"])
    normalized_channels = []
    if isinstance(raw_channels, list):
        for channel in raw_channels:
            normalized = str(channel).strip().lower()
            if normalized in supported_channels and normalized not in normalized_channels:
                normalized_channels.append(normalized)

    if not normalized_channels:
        normalized_channels = defaults["default_channels"].copy()

    try:
        slides_per_post = int(raw_config.get("slides_per_post", defaults["slides_per_post"]))
    except (TypeError, ValueError):
        slides_per_post = defaults["slides_per_post"]

    try:
        render_width = int(raw_config.get("render_width", defaults["render_width"]))
        render_height = int(raw_config.get("render_height", defaults["render_height"]))
    except (TypeError, ValueError):
        render_width = defaults["render_width"]
        render_height = defaults["render_height"]

    background_strategy = str(
        raw_config.get("background_strategy", defaults["background_strategy"])
    ).strip().lower()
    if background_strategy not in supported_background_strategies:
        background_strategy = defaults["background_strategy"]

    background_style = str(
        raw_config.get("background_style", defaults["background_style"])
    ).strip().lower()
    if background_style not in supported_background_styles:
        background_style = defaults["background_style"]

    return {
        "slides_per_post": max(3, min(slides_per_post, 12)),
        "review_required": bool(raw_config.get("review_required", defaults["review_required"])),
        "default_channels": normalized_channels,
        "render_width": max(720, render_width),
        "render_height": max(720, render_height),
        "background_strategy": background_strategy,
        "background_style": background_style,
    }


def get_dashboard_host() -> str:
    """
    Gets the dashboard host binding.

    Returns:
        host (str): Hostname or IP
    """
    dashboard_config = _read_config().get("dashboard", {})
    if not isinstance(dashboard_config, dict):
        dashboard_config = {}

    return str(dashboard_config.get("host", "127.0.0.1")).strip() or "127.0.0.1"


def get_dashboard_port() -> int:
    """
    Gets the dashboard port.

    Returns:
        port (int): Dashboard port
    """
    dashboard_config = _read_config().get("dashboard", {})
    if not isinstance(dashboard_config, dict):
        dashboard_config = {}

    try:
        return int(dashboard_config.get("port", 5000))
    except (TypeError, ValueError):
        return 5000
