"""Formules de niveaux/XP."""
from __future__ import annotations


def xp_for_level(level: int) -> int:
    """XP necessaire pour passer du `level` au niveau suivant."""
    return 5 * (level ** 2) + 50 * level + 100


def level_details(total_xp: int) -> tuple[int, int, int]:
    """A partir de l'XP totale, renvoie (niveau, xp_dans_le_niveau, xp_pour_le_prochain)."""
    level = 0
    remaining = max(0, total_xp)
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level, remaining, xp_for_level(level)
