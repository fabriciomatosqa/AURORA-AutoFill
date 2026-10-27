"""Imagens embutidas em modelos ricos: sem referências a arquivos locais.

As imagens são incorporadas como data URI no HTML salvo no SQLite,
nos backups e no clipboard HTML. A colagem só exibe a figura quando
o aplicativo de destino aceita HTML com imagens embutidas.
"""
from __future__ import annotations

import base64
import binascii
import re
from html.parser import HTMLParser

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl, Signal, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QTextEdit

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 12
MAX_DIMENSION = 1400
DISPLAY_WIDTH = 580
MAX_IMAGE_PIXELS = 16_000_000
MAX_TOTAL_IMAGE_PIXELS = 16_000_000
DATA_URL_PATTERN = re.compile(
    r'^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$', re.IGNORECASE
)


def image_sources(html: str) -> list[str]:
    """Recolhe fontes <img> — inclusive para rejeitar fontes externas."""
    class Images(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.sources = []

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                values = [value for key, value in attrs if key == "src"]
                # Missing/duplicate sources are invalid, including unquoted URLs.
                self.sources.append((values[0] or "") if len(values) == 1 else "")

    parser = Images()
    parser.feed(html or "")
    return parser.sources


def contains_inline_images(html: str) -> bool:
    return any(source.startswith("data:image/") for source in image_sources(html))


def plain_text_fallback(text: str) -> str:
    """Qt guarda imagens como U+FFFC no texto simples."""
    return text.replace("\ufffc", "[Imagem]")


def decode_embedded_image(source: str) -> QImage:
    match = DATA_URL_PATTERN.fullmatch(source)
    if not match:
        raise ValueError("Somente imagens PNG/JPEG incorporadas são permitidas.")
    encoded = re.sub(r"\s+", "", match.group(2))
    if len(encoded) > (MAX_IMAGE_BYTES + 2) * 4 // 3 + 8:
        raise ValueError("Uma imagem ultrapassa o limite de 2 MB.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Imagem incorporada inválida.") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Uma imagem ultrapassa o limite de 2 MB.")
    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.ReadOnly)
    reader = QImageReader(buffer)
    size = reader.size()
    # Check metadata BEFORE allocating a potentially huge decoded bitmap.
    if (not size.isValid() or size.width() > 8192 or size.height() > 8192
            or size.width() * size.height() > MAX_IMAGE_PIXELS):
        raise ValueError("Imagem muito grande para exibição.")
    if bytes(reader.format()).lower() not in (b"png", b"jpeg", b"jpg"):
        raise ValueError("Somente imagens PNG/JPEG incorporadas são permitidas.")
    image = reader.read()
    if image.isNull():
        raise ValueError("O arquivo da imagem não pôde ser decodificado.")
    if image.width() > 8192 or image.height() > 8192:
        raise ValueError("Imagem muito grande para exibição.")
    return image


def validate_inline_html(html: str) -> None:
    """Limites seguros para importar/salvar imagens (incluindo backup JSON)."""
    sources = image_sources(html)
    if len(sources) > MAX_IMAGES:
        raise ValueError("Um comando permite até 12 imagens.")
    total = pixels = 0
    for source in sources:
        image = decode_embedded_image(source)
        # Base64 payload size is checked above; count decoded bytes here.
        encoded = re.sub(r"\s+", "", source.split(",", 1)[1])
        total += len(encoded) * 3 // 4 - (len(encoded) - len(encoded.rstrip("=")))
        pixels += image.width() * image.height()
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("As imagens do comando ultrapassam 10 MB.")
        if pixels > MAX_TOTAL_IMAGE_PIXELS:
            raise ValueError("As imagens do comando ultrapassam 16 milhões de pixels.")


def add_inline_resources(document: QTextDocument, html: str) -> None:
    """Registra recursos na memória para Qt desenhar data URIs sem buscar disco/rede."""
    for source in set(image_sources(html)):
        try:
            document.addResource(QTextDocument.ImageResource, QUrl(source),
                                 decode_embedded_image(source))
        except ValueError:
            # Conteúdo antigo inválido pode continuar editável como texto;
            # gravação posterior impede inserir recursos não permitidos.
            continue


def _encode_image(image: QImage) -> tuple[str, QImage]:
    if image.isNull():
        raise ValueError("Não foi possível ler a imagem selecionada.")
    if image.width() > MAX_DIMENSION or image.height() > MAX_DIMENSION:
        image = image.scaled(MAX_DIMENSION, MAX_DIMENSION, Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
    for _ in range(10):
        data = QByteArray()
        buffer = QBuffer(data)
        if not buffer.open(QIODevice.WriteOnly):
            raise ValueError("Não foi possível preparar a imagem.")
        ok = image.save(buffer, "PNG")
        buffer.close()
        if not ok:
            raise ValueError("Falha ao converter a imagem para PNG.")
        if len(data) <= MAX_IMAGE_BYTES:
            return bytes(data).hex(), image
        image = image.scaled(max(32, round(image.width() * .8)),
                             max(32, round(image.height() * .8)),
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
    raise ValueError("Esta imagem não pode ser compactada ao limite de 2 MB.")


def read_image_file(path: str) -> QImage:
    """Inspect dimensions before decoding files chosen in the image picker."""
    reader = QImageReader(path)
    size = reader.size()
    if (not size.isValid() or size.width() > 8192 or size.height() > 8192
            or size.width() * size.height() > MAX_IMAGE_PIXELS):
        raise ValueError("Imagem inválida ou muito grande para exibição.")
    image = reader.read()
    if image.isNull():
        raise ValueError("Não foi possível abrir esse arquivo de imagem.")
    return image


class EmbeddedImageDocument(QTextDocument):
    """Never let Qt fetch image files/URLs or decode an unchecked document."""
    images_allowed = True

    def loadResource(self, resource_type, name):
        if resource_type == QTextDocument.ImageResource:
            try:
                return decode_embedded_image(name.toString()) if self.images_allowed else QImage()
            except ValueError:
                return QImage()
        return super().loadResource(resource_type, name)


class AuroraImageEditor(QTextEdit):
    """QTextEdit com inserção de screenshots e imagens sem caminhos externos."""
    imageRejected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocument(EmbeddedImageDocument(self))
        self.document().setProperty('auroraHasParagraphMetadata', False)

    def setPlainText(self, text):
        self.document().setProperty('auroraHasParagraphMetadata', False)
        super().setPlainText(text)

    def toHtml(self) -> str:
        from .paragraph_format import serialize_document
        return serialize_document(self.document())

    def createMimeDataFromSelection(self):
        from .paragraph_format import add_metadata, export_options, selected_blocks
        payload = super().createMimeDataFromSelection()
        if payload.hasHtml() and self.document().property('auroraHasParagraphMetadata'):
            first = self.document().findBlock(self.textCursor().selectionStart()).blockNumber()
            entries = [[block.blockNumber()-first, opts] for block in selected_blocks(self)
                       if (opts := export_options(block.blockFormat()))]
            if entries:
                payload.setHtml(add_metadata(payload.html(), entries))
        return payload

    def paintEvent(self, event):
        super().paintEvent(event)
        from .paragraph_format import paint_decorations
        paint_decorations(self)

    def insert_image(self, image: QImage | QPixmap) -> bool:
        try:
            if isinstance(image, QPixmap):
                image = image.toImage()
            if not isinstance(image, QImage) or image.isNull():
                raise ValueError("Copie uma imagem válida ou selecione PNG/JPEG.")
            encoded_hex, resized = _encode_image(image)
            data_uri = "data:image/png;base64," + base64.b64encode(bytes.fromhex(encoded_hex)).decode("ascii")
            previous = image_sources(self.toHtml())
            if len(previous) >= MAX_IMAGES:
                raise ValueError("O comando já possui 12 imagens.")
            validate_inline_html(self.toHtml().replace("</body>", f'<img src="{data_uri}"/></body>'))
            fmt = QTextImageFormat()
            fmt.setName(data_uri)
            width = min(DISPLAY_WIDTH, resized.width())
            fmt.setWidth(width)
            fmt.setHeight(max(1, round(resized.height() * width / resized.width())))
            self.document().addResource(QTextDocument.ImageResource, QUrl(data_uri), resized)
            cursor = self.textCursor()
            cursor.insertImage(fmt)
            self.setTextCursor(cursor)
            return True
        except (ValueError, TypeError, OverflowError) as exc:
            self.imageRejected.emit(str(exc))
            return False

    def insertFromMimeData(self, source) -> None:
        from .paragraph_format import read_metadata, restore_metadata
        html = source.html() if source.hasHtml() else ''
        if read_metadata(html):
            cursor = self.textCursor()
            first = self.document().findBlock(cursor.selectionStart()).blockNumber()
            cursor.beginEditBlock()
            try:
                self._insert_payload(source)
                restore_metadata(self.document(), html, first)
            finally:
                cursor.endEditBlock()
            self.viewport().update()
        else:
            self._insert_payload(source)

    def _insert_payload(self, source) -> None:
        # HTML carries the complete sequence. An image flavor may be only a
        # preview; preferring it would silently discard surrounding paragraphs.
        if source.hasHtml() and "<img" in source.html().lower():
            try:
                validate_inline_html(source.html())
                combined = self.document().clone()
                cursor = QTextCursor(combined)
                cursor.setPosition(self.textCursor().selectionStart())
                cursor.setPosition(self.textCursor().selectionEnd(), QTextCursor.KeepAnchor)
                cursor.insertHtml(source.html())
                validate_inline_html(combined.toHtml())
                add_inline_resources(self.document(), source.html())
                super().insertFromMimeData(source)
            except ValueError as exc:
                self.imageRejected.emit(str(exc))
                if source.hasText():
                    self.textCursor().insertText(source.text())
            return
        if source.hasImage():
            self.insert_image(source.imageData())
            return
        super().insertFromMimeData(source)

    def setHtml(self, html: str) -> None:
        self.document().setProperty('auroraHasParagraphMetadata', None)
        try:
            validate_inline_html(html)
        except ValueError as exc:
            # Old/imported invalid snippets remain editable and their saved
            # HTML is untouched, but no image resource is loaded.
            self.document().images_allowed = False
            super().setHtml(html)
            self._restore_paragraphs(html)
            self.imageRejected.emit(str(exc))
            return
        self.document().images_allowed = True
        super().setHtml(html)
        self._restore_paragraphs(html)
        add_inline_resources(self.document(), html)
        self.document().markContentsDirty(0, self.document().characterCount())

    def _restore_paragraphs(self, html):
        from .paragraph_format import normalize_contextual_spacing, restore_metadata
        restore_metadata(self.document(), html)
        normalize_contextual_spacing(self.document())
        self.document().clearUndoRedoStacks()
