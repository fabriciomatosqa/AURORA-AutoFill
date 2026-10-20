"""Clipboard representations, without changing the persisted snippet/backup.

HTML preserves the ordered document. A bitmap is an alternative for ONE
isolated image, never a representation of an entire mixed document.
"""
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData
from PySide6.QtGui import QTextDocument

from .core import render_snippet
from .formatting import render_rich_html
from .inline_images import decode_embedded_image, image_sources, validate_inline_html


def image_notice_text(text: str) -> str:
    parts = text.split("\ufffc")
    return "".join(part + (f"[Imagem {index + 1}: cole separadamente pelo AURORA]"
                          if index < len(parts) - 1 else "")
                   for index, part in enumerate(parts))


@dataclass(frozen=True)
class MixedContent:
    html: str
    text: str
    document_text: str
    cursor_prefix: str
    document_cursor_prefix: str
    left_moves: int
    image_count: int
    image_only: bool


def prepare_mixed_content(html: str, clipboard_text: str, now: datetime) -> MixedContent:
    validate_inline_html(html)
    document = QTextDocument()
    document.setHtml(html)
    template = document.toPlainText()
    rich = render_snippet(template, clipboard_text, now)
    plain = render_snippet(image_notice_text(template), clipboard_text, now)
    sources = image_sources(html)
    return MixedContent(
        render_rich_html(html, clipboard_text, now), plain.text, rich.text,
        plain.text[:-plain.left_moves] if plain.left_moves else plain.text,
        rich.text[:-rich.left_moves] if rich.left_moves else rich.text,
        rich.left_moves, len(sources),
        len(sources) == 1 and rich.text.replace("\ufffc", "").strip() == "",
    )


def image_mime(source: str) -> QMimeData:
    image = decode_embedded_image(source)
    payload = QMimeData()
    payload.setImageData(image)  # Qt maps to native DIB/DIBV5 on Windows.
    png = QByteArray()
    buffer = QBuffer(png)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("Não foi possível preparar a imagem para copiar.")
    buffer.close()
    payload.setData("image/png", png)
    return payload


def expansion_mime(text: str, html: str = "", *, image_only: bool = False) -> QMimeData:
    if image_only:
        sources = image_sources(html)
        if len(sources) != 1:
            raise ValueError("A colagem de imagem isolada exige exatamente uma imagem.")
        payload = image_mime(sources[0])
    else:
        payload = QMimeData()
    payload.setText(text)
    if html:
        payload.setHtml(html)  # Qt owns CF_HTML offsets and UTF-8 encoding.
    return payload


def clone_mime(original) -> QMimeData:
    clone = QMimeData()
    if original:
        for fmt in original.formats():
            clone.setData(fmt, original.data(fmt))
        # application/x-qt-image is a QVariant, not a serialized byte buffer.
        if original.hasImage():
            clone.setImageData(original.imageData())
    return clone
