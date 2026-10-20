"""Clipboard representations, without changing the persisted snippet/backup.

HTML preserves the ordered document. A bitmap is an alternative for ONE
isolated image, never a representation of an entire mixed document.
"""
from dataclasses import dataclass
from datetime import datetime
from math import ceil

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QRectF
from PySide6.QtGui import QImage, QColor, QFont, QPainter, QTextDocument

from .core import render_snippet
from .formatting import render_rich_html
from .inline_images import (EmbeddedImageDocument, decode_embedded_image,
                            image_sources, validate_inline_html)


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


def bitmap_mime(image: QImage) -> QMimeData:
    """Clipboard de imagem real para destinos que tratam PNG como anexo."""
    if image.isNull():
        raise ValueError("Imagem inválida para a área de transferência.")
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


def image_mime(source: str) -> QMimeData:
    return bitmap_mime(decode_embedded_image(source))


def render_message_as_bitmap(html: str) -> QImage:
    """Converte a mensagem INTEIRA (texto e imagens) em uma única figura.

    Algumas caixas do Teams ignoram <img> no CF_HTML, mas aceitam uma captura
    PNG colada como anexo. Esta alternativa opt-in preserva visualmente a
    mensagem; o texto da imagem não continua editável nem pesquisável.
    """
    validate_inline_html(html)
    document = EmbeddedImageDocument()
    document.setDefaultFont(QFont("Segoe UI", 11))
    document.setDocumentMargin(0)
    document.setHtml(html)
    document.setTextWidth(720)
    content_height = max(1, ceil(document.size().height()))
    width, height = 760, content_height + 40
    if (height > 7000 or width * height > 10_000_000):
        raise ValueError(
            "O comando é muito longo para virar uma única imagem. "
            "Use a cópia de imagens separadas.")
    result = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    if result.isNull():
        raise ValueError("Não foi possível preparar a imagem da mensagem.")
    result.fill(QColor("#ffffff"))
    painter = QPainter(result)
    try:
        painter.translate(20, 20)
        document.drawContents(painter, QRectF(0, 0, 720, content_height))
    finally:
        painter.end()
    return result


def message_as_image_mime(html: str) -> QMimeData:
    """Somente PNG e bitmap: evita Teams preferir texto/plain como fallback."""
    return bitmap_mime(render_message_as_bitmap(html))


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
