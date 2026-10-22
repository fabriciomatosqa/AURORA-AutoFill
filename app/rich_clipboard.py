"""Representações interoperáveis de texto rico para Word e editores WebView.

QTextEdit serializa estilos numa árvore HTML Qt; muitos destinos Windows
preferem um fragmento HTML simples ou Rich Text Format. Emitimos os dois
sem alterar os snippets salvos e sem rasterizar o texto como imagem.
"""
from __future__ import annotations

from html import escape
from io import StringIO

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextDocument, QTextFormat


def _runs(html: str):
    document = QTextDocument()
    document.setHtml(html)
    blocks = []
    block = document.begin()
    while block.isValid():
        row = []
        fragment = block.begin()
        while not fragment.atEnd():
            value = fragment.fragment()
            if value.isValid():
                row.append((value.text(), value.charFormat()))
            fragment += 1
        blocks.append(row)
        block = block.next()
    return blocks


def _color(formatting: QTextCharFormat, property_id: int) -> QColor | None:
    if not formatting.hasProperty(property_id):
        return None
    if property_id == QTextFormat.ForegroundBrush:
        result = formatting.foreground().color()
    else:
        result = formatting.background().color()
    return result if result.isValid() else None


def _family(fmt: QTextCharFormat) -> str | None:
    families = fmt.fontFamilies()
    if families:
        return str(families[0])
    return None


def interoperable_html(html: str) -> str:
    """HTML simples com cores em spans e atributos legados para Word/Teams.

    Não gera novos espaços, bitmap, nem quebra a edição dos caracteres.
    Imagens são tratadas pela rota antiga, que conserva recursos independentes.
    """
    result = []
    for row in _runs(html):
        pieces = []
        for text, fmt in row:
            if not text:
                continue
            # Não inserir substitutos de objetos que só existem no QTextDocument.
            if "\ufffc" in text:
                raise ValueError("Não converter HTML com imagens por essa rota.")
            styles = []
            color = _color(fmt, QTextFormat.ForegroundBrush)
            highlight = _color(fmt, QTextFormat.BackgroundBrush)
            if color is not None:
                styles.append(f"color:{color.name()}")
            if highlight is not None:
                # Teams e Word importam marcações distintas. Informar cor
                # CSS nos dois atributos, sem depender do tema escuro do app.
                styles.append(f"background-color:{highlight.name()}")
                styles.append(f"background:{highlight.name()}")
            family = _family(fmt)
            if family:
                styles.append("font-family:'" + family.replace("'", "&#39;") + "'")
            size = fmt.fontPointSize()
            if size > 0:
                styles.append(f"font-size:{size:g}pt")
            if fmt.fontWeight() >= 700:
                styles.append("font-weight:bold")
            if fmt.fontItalic():
                styles.append("font-style:italic")
            decorations = []
            if fmt.fontUnderline():
                decorations.append("underline")
            if fmt.fontStrikeOut():
                decorations.append("line-through")
            if decorations:
                styles.append("text-decoration:" + " ".join(decorations))
            escaped = escape(text)
            # <mark> representa um REALCE sem converter o texto em imagem.
            # Alguns editores WebView reconhecem mark mesmo descartando CSS
            # do span; ambos usam o tom exato escolhido, quando aceito.
            if highlight is not None:
                escaped = (
                    f'<mark style="background-color:{highlight.name()};'
                    f'background:{highlight.name()}">{escaped}</mark>'
                )
            span = f'<span style="{";".join(styles)}">{escaped}</span>' if styles else escaped
            # Alguns editores Office antigos utilizam <font color> em vez de
            # color CSS. Fornecer ambos sem alterar a semântica do fragmento.
            if color is not None:
                span = f'<font color="{color.name()}">{span}</font>'
            pieces.append(span)
        # Blocos vazios entre textos devem continuar como uma linha vazia.
        # Qt ignora <p></p>, mas <p><br></p> introduz uma quebra EXTRA;
        # separar os blocos com <br> mantém exatamente a sequência original.
        result.append("".join(pieces))
    return '<div style="white-space:pre-wrap">' + '<br>'.join(result) + '</div>'


def _rtf_escape(text: str) -> str:
    result = []
    for character in text:
        if character in "{}\\":
            result.append("\\" + character)
        elif character == "\t":
            result.append(r"\tab ")
        elif character in "\r\n\u2028\u2029":
            result.append(r"\line ")
        elif 0x20 <= ord(character) <= 0x7e:
            result.append(character)
        else:
            # RTF \u espera valores assinados de UTF-16, não codepoints.
            encoded = character.encode("utf-16-le")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset:offset+2], "little")
                if unit >= 32768:
                    unit -= 65536
                result.append(f"\\u{unit}?")
    return "".join(result)


def rich_text_rtf(html: str) -> bytes:
    """Formato RTF nativo do Windows, com cores de texto e realce por trecho."""
    blocks = _runs(html)
    fonts: dict[str, int] = {"Segoe UI": 0}
    colors: dict[str, int] = {}
    for row in blocks:
        for text, fmt in row:
            if "\ufffc" in text:
                raise ValueError("Imagens devem permanecer em payload próprio.")
            family = _family(fmt)
            if family and family not in fonts:
                fonts[family] = len(fonts)
            for prop in (QTextFormat.ForegroundBrush, QTextFormat.BackgroundBrush):
                chosen = _color(fmt, prop)
                if chosen is not None and chosen.name() not in colors:
                    colors[chosen.name()] = len(colors) + 1
    buf = StringIO()
    buf.write(r"{\rtf1\ansi\ansicpg1252\uc1\deff0")
    buf.write(r"{\fonttbl")
    for family, index in fonts.items():
        buf.write(f"{{\\f{index}\\fnil {_rtf_escape(family)};}}")
    buf.write("}")
    buf.write(r"{\colortbl ;")
    for hex_color in colors:
        rgb = QColor(hex_color)
        buf.write(f"\\red{rgb.red()}\\green{rgb.green()}\\blue{rgb.blue()};")
    buf.write("}")
    for index, row in enumerate(blocks):
        if index:
            buf.write(r"\par ")
        buf.write(r"\pard\plain ")
        if not row:
            continue
        for text, fmt in row:
            family = _family(fmt) or "Segoe UI"
            font_size = fmt.fontPointSize() or 11
            size = max(2, min(32767, round(font_size * 2)))
            fg = _color(fmt, QTextFormat.ForegroundBrush)
            bg = _color(fmt, QTextFormat.BackgroundBrush)
            fg_index = colors.get(fg.name(), 0) if fg else 0
            bg_index = colors.get(bg.name(), 0) if bg else 0
            flags = [f"\\f{fonts[family]}", f"\\fs{size}", f"\\cf{fg_index}",
                     f"\\highlight{bg_index}"]
            if fmt.fontWeight() >= 700:
                flags.append(r"\b")
            if fmt.fontItalic():
                flags.append(r"\i")
            if fmt.fontUnderline():
                flags.append(r"\ul")
            if fmt.fontStrikeOut():
                flags.append(r"\strike")
            align = fmt.verticalAlignment()
            if align == QTextCharFormat.AlignSuperScript:
                flags.append(r"\super")
            if align == QTextCharFormat.AlignSubScript:
                flags.append(r"\sub")
            buf.write("{" + "".join(flags) + " " + _rtf_escape(text) + "}")
    buf.write("}")
    # Formato ANSI com escapes \u para caracteres Unicode.
    return buf.getvalue().encode("ascii")


def cf_html_bytes(fragment: str) -> bytes:
    """Cria HTML Format/CF_HTML documentado pela Microsoft, offsets em bytes UTF-8."""
    before = '<html><head><meta charset="utf-8"></head><body><!--StartFragment-->'
    after = '<!--EndFragment--></body></html>'
    prefix = (b"Version:1.0\r\n"
              b"StartHTML:0000000000\r\n"
              b"EndHTML:0000000000\r\n"
              b"StartFragment:0000000000\r\n"
              b"EndFragment:0000000000\r\n")
    before_bytes, fragment_bytes, after_bytes = (
        before.encode("utf-8"), fragment.encode("utf-8"), after.encode("utf-8"))
    start_html = len(prefix)
    start_fragment = start_html + len(before_bytes)
    end_fragment = start_fragment + len(fragment_bytes)
    end_html = end_fragment + len(after_bytes)
    header = (f"Version:1.0\r\nStartHTML:{start_html:010d}\r\n"
              f"EndHTML:{end_html:010d}\r\n"
              f"StartFragment:{start_fragment:010d}\r\n"
              f"EndFragment:{end_fragment:010d}\r\n").encode("ascii")
    if len(header) != start_html:
        raise ValueError("Offsets do CF_HTML inconsistentes.")
    return header + before_bytes + fragment_bytes + after_bytes
