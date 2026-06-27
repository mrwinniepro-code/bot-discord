"""Generation de la carte de bienvenue en image (Pillow)."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont, ImageOps

from ..config import FONTS_DIR

CARD_W, CARD_H = 1024, 320


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Charge une police TrueType. Essaie, dans l'ordre :
    polices fournies -> polices systeme (Windows/Linux/Mac) -> police par defaut.
    """
    candidates: list[Path] = []
    if bold:
        candidates += [FONTS_DIR / "DejaVuSans-Bold.ttf", FONTS_DIR / "Roboto-Bold.ttf"]
        candidates += [
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/Library/Fonts/Arial Bold.ttf"),
        ]
    else:
        candidates += [FONTS_DIR / "DejaVuSans.ttf", FONTS_DIR / "Roboto-Regular.ttf"]
        candidates += [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]

    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        except Exception:
            continue

    # Dernier recours : police par defaut de Pillow (>=10.1 accepte une taille)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """Fond degrade vertical, calcule rapidement (colonne 1px puis etirement)."""
    column = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        column.putpixel(
            (0, y),
            tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)),
        )
    return column.resize((w, h))


def _circular(avatar: Image.Image, size: int) -> Image.Image:
    """Rend l'avatar circulaire avec de l'antialiasing."""
    scale = 4
    big = avatar.convert("RGBA").resize((size * scale, size * scale), Image.LANCZOS)
    mask = Image.new("L", (size * scale, size * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * scale, size * scale), fill=255)
    big.putalpha(mask)
    return big.resize((size, size), Image.LANCZOS)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Coupe le texte avec "..." s'il depasse la largeur max."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "..."
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def _render_card(
    avatar_bytes: bytes,
    title: str,
    username: str,
    subtitle: str,
    background_path: str | None,
) -> io.BytesIO:
    """Dessine la carte (operation CPU, executee dans un thread)."""
    # Fond : image perso si dispo, sinon degrade "blurple" facon Discord
    if background_path and Path(background_path).exists():
        try:
            bg = Image.open(background_path).convert("RGB")
            bg = ImageOps.fit(bg, (CARD_W, CARD_H), Image.LANCZOS)
        except Exception:
            bg = _vertical_gradient(CARD_W, CARD_H, (35, 39, 84), (88, 101, 242))
    else:
        bg = _vertical_gradient(CARD_W, CARD_H, (35, 39, 84), (88, 101, 242))

    card = bg.convert("RGBA")
    # Voile sombre pour la lisibilite du texte
    card = Image.alpha_composite(card, Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 110)))
    draw = ImageDraw.Draw(card)

    # Avatar + anneau blanc
    av_size = 200
    avatar = Image.open(io.BytesIO(avatar_bytes))
    avatar = _circular(avatar, av_size)
    ax, ay = 60, (CARD_H - av_size) // 2
    ring_pad = 7
    ring = Image.new("RGBA", (av_size + ring_pad * 2, av_size + ring_pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(
        (0, 0, av_size + ring_pad * 2, av_size + ring_pad * 2), fill=(255, 255, 255, 255)
    )
    card.paste(ring, (ax - ring_pad, ay - ring_pad), ring)
    card.paste(avatar, (ax, ay), avatar)

    # Textes
    tx = ax + av_size + 50
    max_text_w = CARD_W - tx - 40
    title_font = _load_font(52, bold=True)
    name_font = _load_font(46, bold=True)
    sub_font = _load_font(30)

    draw.text((tx, 78), _truncate(draw, title, title_font, max_text_w),
              font=title_font, fill=(255, 255, 255))
    draw.text((tx, 142), _truncate(draw, username, name_font, max_text_w),
              font=name_font, fill=(173, 216, 255))
    draw.text((tx, 208), _truncate(draw, subtitle, sub_font, max_text_w),
              font=sub_font, fill=(220, 220, 225))

    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def generate_welcome_card(
    member: discord.Member,
    title: str = "Bienvenue",
    subtitle: str | None = None,
    background_path: str | None = None,
) -> io.BytesIO:
    """Genere la carte de bienvenue d'un membre et renvoie un buffer PNG."""
    avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
    if subtitle is None:
        count = member.guild.member_count or 0
        subtitle = f"Membre n°{count}" if count else member.guild.name
    username = member.display_name

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _render_card, avatar_bytes, title, username, subtitle, background_path
    )
