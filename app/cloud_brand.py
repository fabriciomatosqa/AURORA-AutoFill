"""Offline provider marks for the desktop backup UI (no network assets)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

BRAND_ASSETS = {
    "google": "google-drive.svg",
    "onedrive": "onedrive.svg",
}

BRAND_NAMES = {
    "google": "Google Drive",
    "onedrive": "Microsoft OneDrive",
}


def provider_pixmap(provider: str, size: int = 40) -> QPixmap:
    """Rasterize bundled vector marks at requested size; suitable for HiDPI Qt."""
    if provider not in BRAND_ASSETS:
        raise ValueError("Provedor de backup desconhecido.")
    if not 16 <= size <= 192:
        raise ValueError("Dimensão de logo inválida.")
    asset = (Path(__file__).resolve().parents[1] / "assets" / "brands"
             / BRAND_ASSETS[provider])
    renderer = QSvgRenderer(str(asset))
    if not renderer.isValid():
        raise RuntimeError(f"Logotipo ausente ou inválido: {BRAND_ASSETS[provider]}")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return pixmap
