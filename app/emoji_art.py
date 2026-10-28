"""Offline Microsoft Fluent 3D artwork; inserted messages remain Unicode text."""
from functools import lru_cache
import json
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap

_RESOURCE = Path(__file__).resolve().parents[1]/'assets/emoji/fluent-3d.json'


@lru_cache(maxsize=1)
def emoji_artwork():
    try:
        data = json.loads(_RESOURCE.read_text(encoding='utf-8'))
        return data['emoji']
    except (OSError, ValueError, KeyError, TypeError):
        return {}


@lru_cache(maxsize=1)
def _atlas():
    return QPixmap(str(_RESOURCE.with_name('fluent-3d.png')))


@lru_cache(maxsize=512)
def emoji_icon(emoji):
    record = emoji_artwork().get(emoji)
    if not record or _atlas().isNull():
        return QIcon()
    rect = record.get('rect',[])
    if len(rect)!=4:
        return QIcon()
    pixmap = _atlas().copy(*rect)
    pixmap.setDevicePixelRatio(3)
    return QIcon(pixmap)
