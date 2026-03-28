import os
from PIL import Image
from PIL import ImageColor
from PIL import ImageDraw
from PIL import ImageEnhance
from PIL import ImageFilter
from PIL import ImageFont

from config import get_font
from config import get_fonts_dir


BACKGROUND_COLORS = [
    ("#102542", "#1E5F74"),
    ("#3E1F47", "#C06C84"),
    ("#0B3C49", "#4DAA57"),
    ("#3C1642", "#086375"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = os.path.join(get_fonts_dir(), get_font())
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def _vertical_gradient(width: int, height: int, top_hex: str, bottom_hex: str) -> Image.Image:
    top_rgb = ImageColor.getrgb(top_hex)
    bottom_rgb = ImageColor.getrgb(bottom_hex)
    gradient = Image.new("RGB", (width, height), top_rgb)
    draw = ImageDraw.Draw(gradient)

    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            int(top_rgb[index] + (bottom_rgb[index] - top_rgb[index]) * ratio)
            for index in range(3)
        )
        draw.line([(0, y), (width, y)], fill=color)

    return gradient


def _fit_background(background_path: str, width: int, height: int) -> Image.Image | None:
    if not background_path or not os.path.exists(background_path):
        return None

    background = Image.open(background_path).convert("RGB")
    scale = max(width / background.width, height / background.height)
    resized = background.resize(
        (int(background.width * scale), int(background.height * scale)),
        Image.Resampling.LANCZOS,
    )

    left = max((resized.width - width) // 2, 0)
    top = max((resized.height - height) // 2, 0)
    cropped = resized.crop((left, top, left + width, top + height))
    cropped = ImageEnhance.Brightness(cropped).enhance(0.55)
    return cropped.filter(ImageFilter.GaussianBlur(radius=1.5))


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    max_width: int,
    fill: str,
    line_spacing: int,
) -> int:
    words = str(text or "").split()
    lines = []
    current = []

    for word in words:
        trial = " ".join(current + [word]).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(word)
            continue

        lines.append(" ".join(current))
        current = [word]

    if current:
        lines.append(" ".join(current))

    cursor_y = y
    for line in lines:
        draw.text((x, cursor_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, cursor_y), line, font=font)
        cursor_y = bbox[3] + line_spacing

    return cursor_y


def render_cardnews_slides(
    slides: list[dict],
    output_dir: str,
    width: int,
    height: int,
) -> list[str]:
    """
    Render carousel slides to PNG files.

    Args:
        slides (list[dict]): Normalized slide payloads
        output_dir (str): Output directory
        width (int): Canvas width
        height (int): Canvas height

    Returns:
        asset_paths (list[str]): Rendered PNG paths
    """
    os.makedirs(output_dir, exist_ok=True)
    asset_paths = []

    for index, slide in enumerate(slides, start=1):
        palette = BACKGROUND_COLORS[(index - 1) % len(BACKGROUND_COLORS)]
        canvas = _vertical_gradient(width, height, palette[0], palette[1])
        background = _fit_background(slide.get("background_path", ""), width, height)
        if background is not None:
            canvas = Image.blend(canvas, background, alpha=0.62)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        card_left = int(width * 0.07)
        card_top = int(height * 0.44)
        card_right = int(width * 0.93)
        card_bottom = int(height * 0.91)
        overlay_draw.rounded_rectangle(
            (card_left, card_top, card_right, card_bottom),
            radius=36,
            fill=(7, 12, 19, 190),
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(canvas)
        badge_font = _load_font(28)
        title_font = _load_font(54)
        body_font = _load_font(34)
        footer_font = _load_font(24)

        draw.rounded_rectangle(
            (card_left, 56, card_left + 220, 112),
            radius=22,
            fill=(255, 255, 255),
        )
        draw.text((card_left + 22, 70), f"SLIDE {index}", font=badge_font, fill="#0C1220")

        title_y = card_top + 34
        next_y = _draw_wrapped_text(
            draw,
            slide.get("title", ""),
            title_font,
            card_left + 28,
            title_y,
            card_right - card_left - 56,
            "#FFFFFF",
            12,
        )
        _draw_wrapped_text(
            draw,
            slide.get("body", ""),
            body_font,
            card_left + 28,
            next_y + 18,
            card_right - card_left - 56,
            "#D9E2EC",
            10,
        )
        draw.text(
            (card_left + 28, card_bottom - 42),
            slide.get("topic", ""),
            font=footer_font,
            fill="#9FB3C8",
        )

        output_path = os.path.join(output_dir, f"{index:02d}.png")
        canvas.save(output_path, format="PNG")
        asset_paths.append(output_path)

    return asset_paths
