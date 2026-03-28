import hashlib
import math
import os
import re
from functools import lru_cache

from PIL import Image
from PIL import ImageColor
from PIL import ImageDraw
from PIL import ImageEnhance
from PIL import ImageFilter
from PIL import ImageFont

from config import get_font
from config import get_fonts_dir


CARDNEWS_THEMES = [
    {
        "name": "ocean",
        "bg_start": "#0A2342",
        "bg_end": "#126A7A",
        "surface": "#F4F8FF",
        "surface_alt": "#DDEBFA",
        "accent": "#69E2FF",
        "accent_alt": "#8FE3B0",
        "text": "#0D1B2A",
        "muted": "#5E6D82",
        "light_text": "#FFFFFF",
    },
    {
        "name": "ember",
        "bg_start": "#28112B",
        "bg_end": "#C44935",
        "surface": "#FFF6F0",
        "surface_alt": "#FFE2D3",
        "accent": "#FF936A",
        "accent_alt": "#FFD166",
        "text": "#24161E",
        "muted": "#735866",
        "light_text": "#FFFDFB",
    },
    {
        "name": "forest",
        "bg_start": "#0E3B35",
        "bg_end": "#3A7D44",
        "surface": "#F4FAF4",
        "surface_alt": "#DCEFD8",
        "accent": "#C2F970",
        "accent_alt": "#78D7C3",
        "text": "#11241D",
        "muted": "#54685C",
        "light_text": "#F8FFFC",
    },
    {
        "name": "sand",
        "bg_start": "#4B2E39",
        "bg_end": "#C8815F",
        "surface": "#FFF8EF",
        "surface_alt": "#F7E1CF",
        "accent": "#F5C26B",
        "accent_alt": "#FFDCA8",
        "text": "#2A1C20",
        "muted": "#7A6561",
        "light_text": "#FFFDFC",
    },
    {
        "name": "slate",
        "bg_start": "#101827",
        "bg_end": "#455A64",
        "surface": "#F7F9FC",
        "surface_alt": "#E1E8F1",
        "accent": "#8BF0BA",
        "accent_alt": "#87C9FF",
        "text": "#0F1724",
        "muted": "#5F6D7A",
        "light_text": "#FCFDFF",
    },
]

SLIDE_TYPE_LABELS = {
    "cover": "SWIPE GUIDE",
    "insight": "WHY IT MATTERS",
    "list": "QUICK CHECK",
    "stat": "KEY POINT",
    "quote": "ONE LINE",
    "cta": "NEXT STEP",
    "poster": "VISUAL GUIDE",
}


def _contains_multilingual_text(text: str) -> bool:
    return any(ord(character) > 127 for character in str(text or ""))


@lru_cache(maxsize=128)
def _load_font(role: str, size: int, multilingual: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    configured_font = os.path.join(get_fonts_dir(), get_font())
    candidates = []

    if role == "display":
        if not multilingual and os.path.exists(configured_font):
            candidates.append(configured_font)
        candidates.extend(
            [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/HelveticaNeue.ttc",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                configured_font,
            ]
        )
    else:
        candidates.extend(
            [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/System/Library/Fonts/HelveticaNeue.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                configured_font,
            ]
        )

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue

    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
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
    cropped = ImageEnhance.Brightness(cropped).enhance(0.72)
    return cropped.filter(ImageFilter.GaussianBlur(radius=1.2))


def _color_with_alpha(hex_color: str, alpha: int) -> tuple[int, int, int, int]:
    return ImageColor.getrgb(hex_color) + (max(0, min(alpha, 255)),)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _truncate_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    normalized = str(text or "").rstrip()
    if _text_width(draw, normalized, font) <= max_width:
        return normalized

    while normalized and _text_width(draw, f"{normalized}…", font) > max_width:
        normalized = normalized[:-1]

    return f"{normalized.rstrip()}…"


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int | None = None,
) -> list[str]:
    lines = []
    overflow = False
    paragraphs = str(text or "").splitlines() or [""]

    for paragraph in paragraphs:
        normalized = " ".join(paragraph.strip().split())
        if not normalized:
            continue

        words = normalized.split(" ")
        current = ""
        index = 0

        while index < len(words):
            word = words[index]
            trial = f"{current} {word}".strip()
            if not current or _text_width(draw, trial, font) <= max_width:
                current = trial
                index += 1
                continue

            if current:
                lines.append(current)
                current = ""
                if max_lines and len(lines) >= max_lines:
                    overflow = True
                    break
                continue

            token = ""
            for character in word:
                trial = f"{token}{character}"
                if token and _text_width(draw, trial, font) > max_width:
                    lines.append(token)
                    token = character
                    if max_lines and len(lines) >= max_lines:
                        overflow = True
                        break
                else:
                    token = trial
            current = token
            index += 1

        if overflow:
            break

        if current:
            lines.append(current)
            if max_lines and len(lines) >= max_lines and index < len(words):
                overflow = True
                break

    if max_lines and len(lines) > max_lines:
        overflow = True
        lines = lines[:max_lines]

    if overflow and lines:
        lines[-1] = _truncate_to_width(draw, lines[-1], font, max_width)

    return lines


def _fit_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    role: str,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int,
) -> tuple[ImageFont.ImageFont, list[str]]:
    multilingual = _contains_multilingual_text(text)
    last_font = _load_font(role, min_size, multilingual)
    last_lines = _wrap_text(draw, text, last_font, max_width, max_lines)

    for size in range(start_size, min_size - 1, -2):
        font = _load_font(role, size, multilingual)
        lines = _wrap_text(draw, text, font, max_width, max_lines)
        if len(lines) <= max_lines:
            return font, lines
        last_font = font
        last_lines = lines[:max_lines]

    return last_font, last_lines[:max_lines]


def _draw_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    fill: str,
    line_height: float,
) -> int:
    if not lines:
        return y

    line_step = int(max(getattr(font, "size", 18) * line_height, getattr(font, "size", 18) + 6))
    cursor_y = y

    for line in lines:
        draw.text((x, cursor_y), line, font=font, fill=fill)
        cursor_y += line_step

    return cursor_y


def _draw_centered_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    center_x: int,
    y: int,
    fill: str,
    line_height: float,
) -> int:
    if not lines:
        return y

    line_step = int(max(getattr(font, "size", 18) * line_height, getattr(font, "size", 18) + 6))
    cursor_y = y

    for line in lines:
        draw.text(
            (center_x - (_text_width(draw, line, font) // 2), cursor_y),
            line,
            font=font,
            fill=fill,
        )
        cursor_y += line_step

    return cursor_y


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    x: int,
    y: int,
    fill: str | tuple[int, int, int, int],
    text_fill: str,
    padding_x: int = 22,
    padding_y: int = 14,
) -> tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + padding_x * 2
    height = bbox[3] - bbox[1] + padding_y * 2
    rect = (x, y, x + width, y + height)
    draw.rounded_rectangle(rect, radius=height // 2, fill=fill)
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=text_fill)
    return rect


def _draw_page_indicator(
    draw: ImageDraw.ImageDraw,
    width: int,
    total: int,
    index: int,
    theme: dict,
    light: bool,
) -> None:
    font = _load_font("body", 24, False)
    fill = theme["light_text"] if light else theme["text"]
    draw.text((width - 170, 74), f"{index:02d} / {total:02d}", font=font, fill=fill)


def _draw_surface_panel(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    radius: int,
    shadow_alpha: int = 42,
    outline: str | None = None,
) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shadow_box = (box[0], box[1] + 18, box[2], box[3] + 18)
    draw.rounded_rectangle(shadow_box, radius=radius, fill=(7, 12, 19, shadow_alpha))
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 0)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def _fit_image_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / max(image.width, 1), height / max(image.height, 1))
    resized = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = max((resized.width - width) // 2, 0)
    top = max((resized.height - height) // 2, 0)
    return resized.crop((left, top, left + width, top + height))


def _paste_rounded_image(
    canvas: Image.Image,
    image_path: str,
    box: tuple[int, int, int, int],
    radius: int,
) -> bool:
    if not image_path or not os.path.exists(image_path):
        return False

    fitted = _fit_image_cover(
        Image.open(image_path).convert("RGB"),
        max(box[2] - box[0], 1),
        max(box[3] - box[1], 1),
    )
    mask = Image.new("L", (fitted.width, fitted.height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, fitted.width, fitted.height), radius=radius, fill=255)
    canvas.paste(fitted, (box[0], box[1]), mask)
    return True


def _draw_arrow_path(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    fill: tuple[int, int, int, int],
    width: int = 6,
) -> None:
    if len(points) < 2:
        return

    draw.line(points, fill=fill, width=width)
    end_x, end_y = points[-1]
    prev_x, prev_y = points[-2]
    dx = end_x - prev_x
    dy = end_y - prev_y
    length = max((dx ** 2 + dy ** 2) ** 0.5, 1)
    ux = dx / length
    uy = dy / length
    arrow_size = 18
    left = (
        end_x - int(ux * arrow_size - uy * (arrow_size * 0.55)),
        end_y - int(uy * arrow_size + ux * (arrow_size * 0.55)),
    )
    right = (
        end_x - int(ux * arrow_size + uy * (arrow_size * 0.55)),
        end_y - int(uy * arrow_size - ux * (arrow_size * 0.55)),
    )
    draw.polygon([(end_x, end_y), left, right], fill=fill)


def _derive_bullets(slide: dict) -> list[str]:
    bullets = slide.get("bullets", [])
    if isinstance(bullets, list):
        normalized = [" ".join(str(bullet).strip().split()) for bullet in bullets if str(bullet).strip()]
        if normalized:
            return normalized[:3]

    body = str(slide.get("body", "")).strip()
    chunks = re.split(r"(?:\n|[.!?]|(?:\s*[-•]\s*))", body)
    normalized = [" ".join(chunk.strip().split()) for chunk in chunks if " ".join(chunk.strip().split())]
    return normalized[:3]


def _add_background_motifs(canvas: Image.Image, theme: dict, slide_type: str, index: int) -> Image.Image:
    width, height = canvas.size
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.ellipse(
        (
            int(width * 0.58),
            int(height * -0.02),
            int(width * 1.02),
            int(height * 0.34),
        ),
        fill=_color_with_alpha(theme["accent"], 48),
    )
    draw.ellipse(
        (
            int(width * -0.12),
            int(height * 0.72),
            int(width * 0.34),
            int(height * 1.08),
        ),
        fill=_color_with_alpha(theme["accent_alt"], 32),
    )

    if slide_type in {"list", "cta"}:
        draw.rounded_rectangle(
            (
                int(width * 0.62),
                int(height * 0.16),
                int(width * 0.96),
                int(height * 0.30),
            ),
            radius=48,
            fill=_color_with_alpha(theme["surface"], 34),
        )
    elif slide_type == "stat":
        draw.rectangle(
            (
                int(width * 0.68),
                int(height * 0.08),
                int(width * 0.92),
                int(height * 0.62),
            ),
            fill=_color_with_alpha(theme["accent"], 18),
        )
    elif slide_type == "quote":
        draw.rounded_rectangle(
            (
                int(width * 0.12),
                int(height * 0.10),
                int(width * 0.32),
                int(height * 0.30),
            ),
            radius=42,
            fill=_color_with_alpha(theme["accent_alt"], 24),
        )

    draw.text(
        (int(width * 0.82), int(height * 0.78)),
        f"{index:02d}",
        font=_load_font("display", 160, False),
        fill=_color_with_alpha(theme["surface"], 28),
    )

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def _select_theme(deck_topic: str) -> dict:
    fingerprint = hashlib.sha256(str(deck_topic or "cardnews").encode("utf-8")).hexdigest()
    return CARDNEWS_THEMES[int(fingerprint[:8], 16) % len(CARDNEWS_THEMES)]


def _prepare_canvas(width: int, height: int, theme: dict, slide: dict, index: int) -> Image.Image:
    canvas = _vertical_gradient(width, height, theme["bg_start"], theme["bg_end"])
    background = _fit_background(slide.get("background_path", ""), width, height)
    if background is not None:
        canvas = Image.blend(canvas, background, alpha=0.30)
    return _add_background_motifs(canvas, theme, str(slide.get("type", "insight")), index)


def _render_cover(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)

    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["cover"]
    eyebrow_font = _load_font("body", 25, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 70, _color_with_alpha(theme["surface"], 235), theme["text"])
    _draw_page_indicator(draw, width, total, index, theme, light=True)

    accent_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent_overlay)
    accent_draw.rounded_rectangle(
        (
            int(width * 0.69),
            int(height * 0.18),
            int(width * 0.93),
            int(height * 0.67),
        ),
        radius=54,
        fill=_color_with_alpha(theme["surface"], 32),
    )
    accent_draw.text(
        (int(width * 0.72), int(height * 0.23)),
        f"{index:02d}",
        font=_load_font("display", 220, False),
        fill=_color_with_alpha(theme["accent"], 110),
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), accent_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        int(width * 0.62),
        4,
        94,
        58,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        int(width * 0.54),
        4,
        34,
        26,
    )

    title_y = int(height * 0.23)
    draw.rounded_rectangle(
        (margin, title_y - 34, margin + 112, title_y - 22),
        radius=6,
        fill=theme["accent"],
    )
    cursor_y = _draw_text_lines(draw, title_lines, title_font, margin, title_y, theme["light_text"], 1.08)
    cursor_y = _draw_text_lines(
        draw,
        body_lines,
        body_font,
        margin,
        cursor_y + 14,
        theme["light_text"],
        1.36,
    )

    highlight = str(slide.get("highlight", "")).strip()
    if highlight:
        highlight_font = _load_font("body", 24, _contains_multilingual_text(highlight))
        _draw_pill(
            draw,
            highlight,
            highlight_font,
            margin,
            cursor_y + 24,
            _color_with_alpha(theme["accent"], 215),
            theme["text"],
            padding_x=18,
            padding_y=12,
        )

    topic = str(slide.get("topic", "")).strip() or "CardNews"
    footer_panel = (margin, height - 200, width - margin, height - 88)
    canvas = _draw_surface_panel(canvas, footer_panel, _color_with_alpha(theme["surface"], 226), radius=40)
    draw = ImageDraw.Draw(canvas)
    footer_font = _load_font("body", 25, _contains_multilingual_text(topic))
    hint_font = _load_font("body", 23, False)
    draw.text((margin + 28, height - 168), topic, font=footer_font, fill=theme["text"])
    draw.text(
        (margin + 28, height - 128),
        "Swipe for the breakdown",
        font=hint_font,
        fill=theme["muted"],
    )
    return canvas


def _render_insight(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    margin = int(width * 0.08)
    panel = (margin, int(height * 0.26), width - margin, height - 96)
    canvas = _draw_surface_panel(canvas, panel, _color_with_alpha(theme["surface"], 244), radius=42)
    draw = ImageDraw.Draw(canvas)

    _draw_page_indicator(draw, width, total, index, theme, light=True)
    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["insight"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 72, theme["accent"], theme["text"], padding_x=18, padding_y=12)

    draw.rounded_rectangle(
        (panel[0] + 24, panel[1] + 26, panel[0] + 38, panel[3] - 26),
        radius=7,
        fill=theme["accent"],
    )

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        panel[2] - panel[0] - 120,
        3,
        70,
        42,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        panel[2] - panel[0] - 120,
        5,
        31,
        24,
    )

    cursor_y = _draw_text_lines(
        draw,
        title_lines,
        title_font,
        panel[0] + 62,
        panel[1] + 58,
        theme["text"],
        1.08,
    )
    cursor_y = _draw_text_lines(
        draw,
        body_lines,
        body_font,
        panel[0] + 62,
        cursor_y + 16,
        theme["muted"],
        1.42,
    )

    highlight = str(slide.get("highlight", "")).strip()
    if highlight:
        highlight_box = (panel[0] + 62, min(cursor_y + 26, panel[3] - 126), panel[2] - 62, panel[3] - 38)
        canvas = _draw_surface_panel(canvas, highlight_box, _color_with_alpha(theme["surface_alt"], 255), radius=28, shadow_alpha=18)
        draw = ImageDraw.Draw(canvas)
        highlight_font, highlight_lines = _fit_text_block(
            draw,
            highlight,
            "display",
            highlight_box[2] - highlight_box[0] - 40,
            2,
            38,
            26,
        )
        _draw_text_lines(
            draw,
            highlight_lines,
            highlight_font,
            highlight_box[0] + 20,
            highlight_box[1] + 18,
            theme["text"],
            1.08,
        )

    return canvas


def _render_list(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)
    _draw_page_indicator(draw, width, total, index, theme, light=True)

    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["list"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 72, _color_with_alpha(theme["surface"], 235), theme["text"], padding_x=18, padding_y=12)

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        width - margin * 2,
        3,
        72,
        42,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        width - margin * 2,
        3,
        29,
        23,
    )

    cursor_y = _draw_text_lines(draw, title_lines, title_font, margin, 170, theme["light_text"], 1.05)
    cursor_y = _draw_text_lines(draw, body_lines, body_font, margin, cursor_y + 10, theme["light_text"], 1.34)

    bullets = _derive_bullets(slide)
    bullet_y = max(int(height * 0.42), cursor_y + 24)
    bullet_height = 122

    for bullet_index, bullet in enumerate(bullets[:3], start=1):
        top = bullet_y + (bullet_index - 1) * (bullet_height + 18)
        box = (margin, top, width - margin, top + bullet_height)
        canvas = _draw_surface_panel(canvas, box, _color_with_alpha(theme["surface"], 242), radius=34, shadow_alpha=24)
        draw = ImageDraw.Draw(canvas)
        badge_center = (box[0] + 56, box[1] + bullet_height // 2)
        draw.ellipse(
            (badge_center[0] - 26, badge_center[1] - 26, badge_center[0] + 26, badge_center[1] + 26),
            fill=theme["accent"],
        )
        number_font = _load_font("display", 28, False)
        draw.text((badge_center[0] - 9, badge_center[1] - 16), str(bullet_index), font=number_font, fill=theme["text"])

        bullet_font, bullet_lines = _fit_text_block(
            draw,
            bullet,
            "body",
            box[2] - box[0] - 130,
            2,
            28,
            22,
        )
        _draw_text_lines(
            draw,
            bullet_lines,
            bullet_font,
            box[0] + 106,
            box[1] + 28,
            theme["text"],
            1.34,
        )

    highlight = str(slide.get("highlight", "")).strip()
    if highlight:
        highlight_font = _load_font("body", 23, _contains_multilingual_text(highlight))
        _draw_pill(
            draw,
            highlight,
            highlight_font,
            margin,
            height - 110,
            _color_with_alpha(theme["surface_alt"], 226),
            theme["text"],
            padding_x=18,
            padding_y=12,
        )

    return canvas


def _render_stat(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)
    _draw_page_indicator(draw, width, total, index, theme, light=True)

    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["stat"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 72, _color_with_alpha(theme["surface"], 230), theme["text"], padding_x=18, padding_y=12)

    highlight = str(slide.get("highlight", "")).strip() or str(slide.get("title", "")).strip()
    highlight_font, highlight_lines = _fit_text_block(
        draw,
        highlight,
        "display",
        int(width * 0.72),
        2,
        148,
        88,
    )
    _draw_text_lines(draw, highlight_lines, highlight_font, margin, 238, theme["accent"], 0.92)

    panel = (margin, int(height * 0.58), width - margin, height - 98)
    canvas = _draw_surface_panel(canvas, panel, _color_with_alpha(theme["surface"], 244), radius=42)
    draw = ImageDraw.Draw(canvas)

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        panel[2] - panel[0] - 56,
        2,
        44,
        28,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        panel[2] - panel[0] - 56,
        4,
        29,
        22,
    )
    cursor_y = _draw_text_lines(draw, title_lines, title_font, panel[0] + 28, panel[1] + 26, theme["text"], 1.05)
    _draw_text_lines(draw, body_lines, body_font, panel[0] + 28, cursor_y + 12, theme["muted"], 1.36)
    return canvas


def _render_quote(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.08)
    _draw_page_indicator(draw, width, total, index, theme, light=True)

    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["quote"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 72, _color_with_alpha(theme["surface"], 230), theme["text"], padding_x=18, padding_y=12)

    quote_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    quote_draw = ImageDraw.Draw(quote_overlay)
    quote_draw.text(
        (margin - 10, 180),
        "“",
        font=_load_font("display", 240, False),
        fill=_color_with_alpha(theme["surface"], 54),
    )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), quote_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    highlight = str(slide.get("highlight", "")).strip() or str(slide.get("title", "")).strip()
    highlight_font, highlight_lines = _fit_text_block(
        draw,
        highlight,
        "display",
        width - margin * 2,
        3,
        76,
        44,
    )
    cursor_y = _draw_text_lines(
        draw,
        highlight_lines,
        highlight_font,
        margin,
        290,
        theme["light_text"],
        1.04,
    )

    panel = (margin, min(cursor_y + 26, int(height * 0.64)), width - margin, height - 94)
    canvas = _draw_surface_panel(canvas, panel, _color_with_alpha(theme["surface"], 244), radius=40)
    draw = ImageDraw.Draw(canvas)
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        panel[2] - panel[0] - 56,
        5,
        29,
        22,
    )
    _draw_text_lines(draw, body_lines, body_font, panel[0] + 28, panel[1] + 28, theme["muted"], 1.40)
    return canvas


def _render_cta(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    margin = int(width * 0.08)
    panel = (margin, 154, width - margin, height - 96)
    canvas = _draw_surface_panel(canvas, panel, _color_with_alpha(theme["surface"], 245), radius=46)
    draw = ImageDraw.Draw(canvas)

    _draw_page_indicator(draw, width, total, index, theme, light=True)
    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["cta"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    _draw_pill(draw, eyebrow_text, eyebrow_font, margin, 72, theme["accent"], theme["text"], padding_x=18, padding_y=12)

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        panel[2] - panel[0] - 56,
        3,
        68,
        40,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        panel[2] - panel[0] - 56,
        4,
        30,
        23,
    )

    cursor_y = _draw_text_lines(draw, title_lines, title_font, panel[0] + 28, panel[1] + 42, theme["text"], 1.04)
    cursor_y = _draw_text_lines(draw, body_lines, body_font, panel[0] + 28, cursor_y + 14, theme["muted"], 1.38)

    bullets = _derive_bullets(slide)
    bullet_top = cursor_y + 18
    bullet_font = _load_font("body", 24, _contains_multilingual_text(" ".join(bullets)))
    for bullet in bullets[:3]:
        box = (panel[0] + 28, bullet_top, panel[2] - 28, bullet_top + 66)
        canvas = _draw_surface_panel(canvas, box, _color_with_alpha(theme["surface_alt"], 255), radius=24, shadow_alpha=12)
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((box[0] + 18, box[1] + 18, box[0] + 48, box[1] + 48), fill=theme["accent"])
        draw.text((box[0] + 25, box[1] + 13), "✓", font=_load_font("display", 24, False), fill=theme["text"])
        draw.text((box[0] + 66, box[1] + 18), bullet, font=bullet_font, fill=theme["text"])
        bullet_top += 80

    highlight = str(slide.get("highlight", "")).strip() or "Save this carousel"
    cta_box = (panel[0] + 28, panel[3] - 122, panel[2] - 28, panel[3] - 34)
    canvas = _draw_surface_panel(canvas, cta_box, _color_with_alpha(theme["accent"], 236), radius=30, shadow_alpha=10)
    draw = ImageDraw.Draw(canvas)
    cta_font, cta_lines = _fit_text_block(draw, highlight, "display", cta_box[2] - cta_box[0] - 40, 2, 34, 24)
    _draw_text_lines(draw, cta_lines, cta_font, cta_box[0] + 20, cta_box[1] + 18, theme["text"], 1.04)
    return canvas


def _prepare_poster_canvas(width: int, height: int, theme: dict, slide: dict) -> Image.Image:
    canvas = _vertical_gradient(width, height, theme["surface"], theme["surface_alt"])
    background = _fit_background(slide.get("background_path", ""), width, height)
    if background is not None:
        canvas = Image.blend(canvas, background, alpha=0.18)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse(
        (int(width * -0.08), int(height * 0.04), int(width * 0.30), int(height * 0.30)),
        fill=_color_with_alpha(theme["accent"], 34),
    )
    draw.ellipse(
        (int(width * 0.70), int(height * 0.62), int(width * 1.06), int(height * 0.96)),
        fill=_color_with_alpha(theme["accent_alt"], 24),
    )
    draw.ellipse(
        (int(width * 0.58), int(height * 0.02), int(width * 0.96), int(height * 0.28)),
        fill=_color_with_alpha(theme["surface_alt"], 122),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=20))
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def _draw_poster_placeholder(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    theme: dict,
) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        (box[0] + 18, box[1] + 18, box[2] - 18, box[3] - 24),
        fill=_color_with_alpha(theme["surface_alt"], 255),
    )
    draw.rounded_rectangle(
        (
            box[0] + int((box[2] - box[0]) * 0.22),
            box[1] + int((box[3] - box[1]) * 0.28),
            box[2] - int((box[2] - box[0]) * 0.22),
            box[1] + int((box[3] - box[1]) * 0.70),
        ),
        radius=24,
        fill=_color_with_alpha(theme["accent"], 188),
    )
    draw.ellipse(
        (
            box[0] + int((box[2] - box[0]) * 0.36),
            box[1] + int((box[3] - box[1]) * 0.18),
            box[0] + int((box[2] - box[0]) * 0.64),
            box[1] + int((box[3] - box[1]) * 0.46),
        ),
        fill=_color_with_alpha(theme["accent_alt"], 210),
    )


def _poster_item_boxes(count: int, width: int, height: int) -> list[tuple[int, int, int, int]]:
    margin = int(width * 0.07)
    gap_x = int(width * 0.04)
    gap_y = int(height * 0.024)
    top = int(height * 0.26)
    bottom = height - int(height * 0.08)
    rows = max(2, math.ceil(max(count, 1) / 2))
    box_width = int((width - (margin * 2) - gap_x) / 2)
    box_height = int((bottom - top - (gap_y * (rows - 1))) / rows)
    left_x = margin
    right_x = margin + box_width + gap_x

    boxes = []
    for index in range(count):
        row = index // 2
        col_in_row = index % 2
        if row % 2 == 0:
            x = left_x if col_in_row == 0 else right_x
        else:
            x = right_x if col_in_row == 0 else left_x
        y = top + row * (box_height + gap_y)
        boxes.append((x, y, x + box_width, y + box_height))

    return boxes


def _render_poster(canvas: Image.Image, slide: dict, theme: dict, index: int, total: int) -> Image.Image:
    width, height = canvas.size
    canvas = _prepare_poster_canvas(width, height, theme, slide)
    draw = ImageDraw.Draw(canvas)
    margin = int(width * 0.07)

    eyebrow_text = str(slide.get("eyebrow", "")).strip() or SLIDE_TYPE_LABELS["poster"]
    eyebrow_font = _load_font("body", 24, _contains_multilingual_text(eyebrow_text))
    pill_width = draw.textbbox((0, 0), eyebrow_text, font=eyebrow_font)[2] + 36
    _draw_pill(
        draw,
        eyebrow_text,
        eyebrow_font,
        max((width - pill_width) // 2, margin),
        62,
        _color_with_alpha(theme["surface"], 236),
        theme["text"],
        padding_x=18,
        padding_y=11,
    )
    if total > 1:
        _draw_page_indicator(draw, width, total, index, theme, light=False)

    title_font, title_lines = _fit_text_block(
        draw,
        slide.get("title", ""),
        "display",
        int(width * 0.78),
        3,
        76,
        46,
    )
    body_font, body_lines = _fit_text_block(
        draw,
        slide.get("body", ""),
        "body",
        int(width * 0.70),
        3,
        28,
        20,
    )

    cursor_y = _draw_centered_text_lines(
        draw,
        title_lines,
        title_font,
        width // 2,
        132,
        theme["text"],
        1.04,
    )
    _draw_centered_text_lines(
        draw,
        body_lines,
        body_font,
        width // 2,
        cursor_y + 12,
        theme["muted"],
        1.34,
    )

    item_boxes = _poster_item_boxes(len(slide.get("poster_items", [])), width, height)
    connector_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    connector_draw = ImageDraw.Draw(connector_overlay)

    for item_index in range(len(item_boxes) - 1):
        current_box = item_boxes[item_index]
        next_box = item_boxes[item_index + 1]
        same_row = abs(current_box[1] - next_box[1]) < 12

        if same_row:
            if current_box[0] < next_box[0]:
                start = (current_box[2] - 8, current_box[1] + int((current_box[3] - current_box[1]) * 0.32))
                end = (next_box[0] + 8, next_box[1] + int((next_box[3] - next_box[1]) * 0.32))
            else:
                start = (current_box[0] + 8, current_box[1] + int((current_box[3] - current_box[1]) * 0.32))
                end = (next_box[2] - 8, next_box[1] + int((next_box[3] - next_box[1]) * 0.32))
            mid_y = start[1] - 24 if current_box[1] < height * 0.55 else start[1] + 24
            points = [start, ((start[0] + end[0]) // 2, mid_y), end]
        else:
            start = (
                current_box[0] + ((current_box[2] - current_box[0]) // 2),
                current_box[3] - 12,
            )
            end = (
                next_box[0] + ((next_box[2] - next_box[0]) // 2),
                next_box[1] + 12,
            )
            via_y = (start[1] + end[1]) // 2
            points = [start, (start[0], via_y), (end[0], via_y), end]

        _draw_arrow_path(
            connector_draw,
            points,
            _color_with_alpha(theme["muted"], 96),
            width=6,
        )

    canvas = Image.alpha_composite(canvas.convert("RGBA"), connector_overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    for item_index, (item, box) in enumerate(zip(slide.get("poster_items", []), item_boxes), start=1):
        canvas = _draw_surface_panel(
            canvas,
            box,
            _color_with_alpha(theme["light_text"], 208),
            radius=34,
            shadow_alpha=16,
            outline=_color_with_alpha(theme["surface_alt"], 255),
        )
        draw = ImageDraw.Draw(canvas)

        badge_box = (box[0] + 14, box[1] + 14, box[0] + 52, box[1] + 52)
        draw.ellipse(badge_box, fill=theme["accent"])
        number_font = _load_font("display", 24, False)
        draw.text((badge_box[0] + 12, badge_box[1] + 7), str(item_index), font=number_font, fill=theme["text"])

        art_box = (box[0] + 22, box[1] + 32, box[2] - 22, box[1] + int((box[3] - box[1]) * 0.58))
        if not _paste_rounded_image(canvas, str(item.get("illustration_path", "")).strip(), art_box, radius=26):
            _draw_poster_placeholder(canvas, art_box, theme)
        draw = ImageDraw.Draw(canvas)

        label_font, label_lines = _fit_text_block(
            draw,
            item.get("label", ""),
            "display",
            box[2] - box[0] - 34,
            2,
            28,
            20,
        )
        sublabel_font, sublabel_lines = _fit_text_block(
            draw,
            item.get("sublabel", ""),
            "body",
            box[2] - box[0] - 38,
            2,
            18,
            14,
        )

        label_top = art_box[3] + 18
        cursor_y = _draw_centered_text_lines(
            draw,
            label_lines,
            label_font,
            box[0] + ((box[2] - box[0]) // 2),
            label_top,
            theme["text"],
            1.06,
        )
        _draw_centered_text_lines(
            draw,
            sublabel_lines,
            sublabel_font,
            box[0] + ((box[2] - box[0]) // 2),
            cursor_y + 6,
            theme["muted"],
            1.30,
        )

    return canvas


def render_cardnews_slides(
    slides: list[dict],
    output_dir: str,
    width: int,
    height: int,
    deck_topic: str = "",
) -> list[str]:
    """
    Render carousel slides to PNG files.

    Args:
        slides (list[dict]): Normalized slide payloads
        output_dir (str): Output directory
        width (int): Canvas width
        height (int): Canvas height
        deck_topic (str): Deck topic used for deterministic theming

    Returns:
        asset_paths (list[str]): Rendered PNG paths
    """
    os.makedirs(output_dir, exist_ok=True)
    asset_paths = []
    theme = _select_theme(deck_topic)
    total = len(slides)

    for index, slide in enumerate(slides, start=1):
        slide_copy = dict(slide)
        slide_type = str(slide_copy.get("type", "")).strip().lower()
        if slide_type not in SLIDE_TYPE_LABELS:
            if index == 1:
                slide_type = "cover"
            elif index == total:
                slide_type = "cta"
            else:
                fallback_types = ["insight", "list", "stat", "quote"]
                slide_type = fallback_types[(index - 2) % len(fallback_types)]
        slide_copy["type"] = slide_type
        slide_copy["topic"] = slide_copy.get("topic", deck_topic)

        if slide_type == "poster":
            canvas = _render_poster(Image.new("RGB", (width, height), theme["surface"]), slide_copy, theme, index, total)
        else:
            canvas = _prepare_canvas(width, height, theme, slide_copy, index)

        if slide_type == "cover":
            canvas = _render_cover(canvas, slide_copy, theme, index, total)
        elif slide_type == "list":
            canvas = _render_list(canvas, slide_copy, theme, index, total)
        elif slide_type == "stat":
            canvas = _render_stat(canvas, slide_copy, theme, index, total)
        elif slide_type == "quote":
            canvas = _render_quote(canvas, slide_copy, theme, index, total)
        elif slide_type == "cta":
            canvas = _render_cta(canvas, slide_copy, theme, index, total)
        else:
            canvas = _render_insight(canvas, slide_copy, theme, index, total)

        output_path = os.path.join(output_dir, f"{index:02d}.png")
        canvas.save(output_path, format="PNG")
        asset_paths.append(output_path)

    return asset_paths
