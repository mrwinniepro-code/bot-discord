"""Parsing de durees du type 10s / 5m / 2h / 1d / 1w."""
from __future__ import annotations

import re
from datetime import timedelta

_UNITS = {"s": 1, "m": 60, "h": 3600, "j": 86400, "d": 86400, "w": 604800}
_PATTERN = re.compile(r"(\d+)\s*([smhjdw])", re.IGNORECASE)


def parse_duration(value: str) -> timedelta | None:
    """'1h30m' / '2d' / '45m' -> timedelta. None si invalide."""
    if not value:
        return None
    matches = _PATTERN.findall(value.lower())
    if not matches:
        return None
    total = 0
    for amount, unit in matches:
        total += int(amount) * _UNITS[unit]
    if total <= 0:
        return None
    return timedelta(seconds=total)


def human_duration(delta: timedelta) -> str:
    """timedelta -> texte lisible en francais."""
    seconds = int(delta.total_seconds())
    parts = []
    for label, size in (("j", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        if seconds >= size:
            qty, seconds = divmod(seconds, size)
            parts.append(f"{qty} {label}")
    return " ".join(parts) if parts else "0 s"
