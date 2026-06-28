"""Generation de la carte de bienvenue en image (Pillow)."""
from __future__ import annotations

import asyncio
import io
import unicodedata
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


def _normalize_text(text: str) -> str:
    """Convertit les "fausses polices" Unicode (caracteres mathematiques stylises,
    pleine chasse, etc.) en lettres normales pour qu'elles s'affichent sur la carte."""
    if not text:
        return text
    return unicodedata.normalize("NFKC", text)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> str:
    """Coupe le texte avec "..." s'il depasse la largeur max."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "..."
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text + ell


def _open_background(background) -> Image.Image | None:
    """Ouvre un fond depuis des octets (URL telechargee) ou un chemin local."""
    try:
        if isinstance(background, (bytes, bytearray)):
            return Image.open(io.BytesIO(background)).convert("RGB")
        if isinstance(background, str) and background and Path(background).exists():
            return Image.open(background).convert("RGB")
    except Exception:
        return None
    return None


def _render_card(
    avatar_bytes: bytes,
    title: str,
    username: str,
    subtitle: str,
    background=None,
) -> io.BytesIO:
    """Dessine la carte (operation CPU, executee dans un thread).

    background : octets d'image, chemin local, ou None (=> degrade par defaut).
    """
    title = _normalize_text(title)
    username = _normalize_text(username)
    subtitle = _normalize_text(subtitle)

    # Fond : image perso si dispo, sinon degrade "blurple" facon Discord
    bg = _open_background(background)
    if bg is not None:
        bg = ImageOps.fit(bg, (CARD_W, CARD_H), Image.LANCZOS)
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


async def _resolve_background(background):
    """Transforme la source de fond (octets ou URL) en octets utilisables par Pillow.

    background : octets (image stockee en base) | URL http(s) | None.
    """
    if not background:
        return None
    if isinstance(background, (bytes, bytearray)):
        return bytes(background)
    if isinstance(background, str) and background.startswith(("http://", "https://")):
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.get(background) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            return None
    return None


async def generate_welcome_card(
    member: discord.Member,
    title: str = "Bienvenue",
    subtitle: str | None = None,
    background=None,
) -> io.BytesIO:
    """Genere la carte de bienvenue d'un membre et renvoie un buffer PNG.

    background : octets d'image (depuis la base) | URL http(s) | None.
    """
    avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
    bg = await _resolve_background(background)
    if subtitle is None:
        count = member.guild.member_count or 0
        subtitle = f"Membre n°{count}" if count else member.guild.name
    username = member.display_name

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _render_card, avatar_bytes, title, username, subtitle, bg
    )


def _render_rank_card(
    avatar_bytes: bytes,
    username: str,
    level: int,
    rank: int,
    xp_into: int,
    xp_needed: int,
) -> io.BytesIO:
    """Carte de niveau : avatar, pseudo, niveau, rang, barre de progression."""
    username = _normalize_text(username)
    W, H = 900, 250
    card = _vertical_gradient(W, H, (30, 32, 54), (45, 48, 80)).convert("RGBA")
    card = Image.alpha_composite(card, Image.new("RGBA", (W, H), (0, 0, 0, 60)))
    draw = ImageDraw.Draw(card)

    # Avatar
    av_size = 160
    avatar = _circular(Image.open(io.BytesIO(avatar_bytes)), av_size)
    ax, ay = 45, (H - av_size) // 2
    ring = Image.new("RGBA", (av_size + 12, av_size + 12), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, av_size + 12, av_size + 12), fill=(88, 101, 242, 255))
    card.paste(ring, (ax - 6, ay - 6), ring)
    card.paste(avatar, (ax, ay), avatar)

    tx = ax + av_size + 40
    name_font = _load_font(40, bold=True)
    info_font = _load_font(26, bold=True)
    small_font = _load_font(22)

    draw.text((tx, 45), _truncate(draw, username, name_font, 480), font=name_font, fill=(255, 255, 255))
    draw.text((tx, 100), f"Niveau {level}", font=info_font, fill=(173, 216, 255))
    rank_text = f"#{rank}"
    rw = draw.textlength(rank_text, font=info_font)
    draw.text((W - 45 - rw, 100), rank_text, font=info_font, fill=(255, 215, 0))

    # Barre de progression
    bar_x, bar_y, bar_w, bar_h = tx, 165, W - tx - 45, 32
    radius = bar_h // 2
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=radius, fill=(20, 21, 36))
    ratio = 0 if xp_needed <= 0 else max(0.0, min(1.0, xp_into / xp_needed))
    fill_w = int(bar_w * ratio)
    if fill_w >= bar_h:
        draw.rounded_rectangle(
            (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=radius, fill=(88, 101, 242)
        )
    draw.text(
        (bar_x, bar_y + bar_h + 8),
        f"{xp_into} / {xp_needed} XP",
        font=small_font,
        fill=(200, 200, 210),
    )

    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def generate_rank_card(
    member: discord.Member, level: int, rank: int, xp_into: int, xp_needed: int
) -> io.BytesIO:
    """Genere la carte de niveau d'un membre."""
    avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _render_rank_card, avatar_bytes, member.display_name, level, rank, xp_into, xp_needed
    )


def placeholder_avatar_bytes() -> bytes:
    """Avatar neutre (silhouette) pour l'apercu du dashboard."""
    img = Image.new("RGB", (256, 256), (88, 101, 242))
    d = ImageDraw.Draw(img)
    d.ellipse((90, 52, 166, 128), fill=(255, 255, 255))      # tete
    d.ellipse((54, 140, 202, 300), fill=(255, 255, 255))     # epaules
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
