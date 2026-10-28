"""Emoji colorido estável independente das fontes do sistema operacional.

Os SVG Twemoji são recursos locais CC BY 4.0, listados em
assets/emoji/ATTRIBUTION.md. Emojis inseridos continuam sendo Unicode.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_RESOURCE = Path(__file__).resolve().parents[1] / "assets" / "emoji" / "twemoji-vectors.json"


@lru_cache(maxsize=1)
def emoji_svgs() -> dict[str, str]:
    """Carrega uma vez o catálogo offline, também distribuído pelo PyInstaller."""
    try:
        with _RESOURCE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data["emoji"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}


@lru_cache(maxsize=512)
def emoji_icon(emoji: str) -> QIcon:
    """Desenha o SVG colorido em pixmap HiDPI; sem texto/tofu nos botões."""
    vector = emoji_svgs().get(emoji)
    if not vector:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(vector.encode("utf-8")))
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, 64, 64))
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)
