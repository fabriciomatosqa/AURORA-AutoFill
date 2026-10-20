"""Imagens embutidas em modelos ricos: sem referências a arquivos locais.

As imagens são incorporadas como data URI no HTML salvo no SQLite,
nos backups e no clipboard HTML. A colagem só exibe a figura quando
o aplicativo de destino aceita HTML com imagens embutidas.
"""
from __future__ import annotations

import base64
import binascii
import re
from html import unescape

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QTextCursor, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QTextEdit

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 12
MAX_DIMENSION = 1400
DISPLAY_WIDTH = 580
DATA_IMAGE_PATTERN = re.compile(
    r'<img\b[^>]*?\bsrc\s*=\s*([\x22\x27])(.*?)\1', re.IGNORECASE | re.DOTALL
)
DATA_URL_PATTERN = re.compile(
    r'^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$', re.IGNORECASE
)


def image_sources(html: str) -> list[str]:
    """Recolhe fontes <img> — inclusive para rejeitar fontes externas."""
    return [unescape(match.group(2)) for match in DATA_IMAGE_PATTERN.finditer(html or "")]


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
    image = QImage.fromData(data, match.group(1).upper().encode("ascii"))
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
    total = 0
    for source in sources:
        image = decode_embedded_image(source)
        # Base64 payload size is checked above; count decoded bytes here.
        total += (len(re.sub(r"\s+", "", source.split(",", 1)[1])) * 3) // 4
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("As imagens do comando ultrapassam 10 MB.")


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


class AuroraImageEditor(QTextEdit):
    """QTextEdit com inserção de screenshots e imagens sem caminhos externos."""
    imageRejected = Signal(str)

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
        if source.hasImage():
            self.insert_image(source.imageData())
            return
        if source.hasHtml() and "<img" in source.html().lower():
            try:
                validate_inline_html(source.html())
                # Previne a adição de imagens externas ou excessivas.
                current = len(image_sources(self.toHtml()))
                incoming = len(image_sources(source.html()))
                if current + incoming > MAX_IMAGES:
                    raise ValueError("O comando permite até 12 imagens.")
                add_inline_resources(self.document(), source.html())
                super().insertFromMimeData(source)
            except ValueError as exc:
                self.imageRejected.emit(str(exc))
                if source.hasText():
                    self.textCursor().insertText(source.text())
            return
        super().insertFromMimeData(source)

    def setHtml(self, html: str) -> None:
        super().setHtml(html)
        add_inline_resources(self.document(), html)
        self.document().markContentsDirty(0, self.document().characterCount())
