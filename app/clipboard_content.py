"""Clipboard representations, without changing the persisted snippet/backup.

HTML preserves the ordered document. A bitmap is an alternative for ONE
isolated image, never a representation of an entire mixed document.
"""
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData
from PySide6.QtGui import QImage, QTextDocument

from .core import render_snippet
from .formatting import render_rich_html
from .inline_images import decode_embedded_image, image_sources, validate_inline_html


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
    # Campos somente texto recebem palavras editáveis, não marcadores
    # artificiais. As imagens são oferecidas separadamente como PNG nativo.
    plain = render_snippet(template.replace("\ufffc", ""), clipboard_text, now)
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


@dataclass(frozen=True)
class ClipboardPart:
    """One *real* text fragment or one native image, in document order.

    A clipboard can offer alternative formats of ONE paste, but it cannot
    represent multiple independent Teams attachments interleaved with text.
    Each part is copied and pasted individually, keeping text editable.
    """
    kind: str
    text: str = ""
    source: str = ""


def ordered_clipboard_parts(html: str, clipboard_text: str = "",
                            now: datetime | None = None) -> tuple[ClipboardPart, ...]:
    """Split saved rich content at the QTextDocument object replacement chars."""
    validate_inline_html(html)
    document = QTextDocument()
    document.setHtml(html)
    template = document.toPlainText()
    sources = image_sources(html)
    fragments = template.split("\ufffc")
    if len(fragments) != len(sources) + 1:
        raise ValueError("Não foi possível preservar a ordem entre texto e imagens.")
    parts = []
    for index, fragment in enumerate(fragments):
        if fragment:
            text = render_snippet(fragment, clipboard_text, now).text
            if text:
                parts.append(ClipboardPart("text", text=text))
        if index < len(sources):
            parts.append(ClipboardPart("image", source=sources[index]))
    return tuple(parts)


def clipboard_part_mime(part: ClipboardPart) -> QMimeData:
    """Editable text stays text; an image uses PNG + native bitmap only."""
    if part.kind == "image":
        return image_mime(part.source)
    if part.kind == "text":
        payload = QMimeData()
        payload.setText(part.text)
        return payload
    raise ValueError("Tipo de conteúdo desconhecido.")



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
