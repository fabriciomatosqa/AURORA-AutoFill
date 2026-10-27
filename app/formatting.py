"""Renderização simples de formatação no clipboard (sem dependências da UI)."""
from __future__ import annotations

from datetime import datetime
from html import escape
import re

from .core import render_snippet

# QTextEdit emite spans para fonte, tamanho, cor e destaque; preservar no clipboard.
_FORMATTED_RE = re.compile(
    r'(?:font-weight\s*:\s*(?:bold|[6-9]00)|font-style\s*:\s*italic'
    r'|text-decoration[^;"]*(?:underline|line-through)|font-family\s*:'
    r'|font-size\s*:|(?:^|[;\s])color\s*:|background-color\s*:'
    r'|vertical-align\s*:|text-align\s*:\s*(?:center|right|justify)'
    r'|align\s*=\s*[\"\'](?:center|right|justify)'
    r'|(?:margin-(?:top|bottom|left|right)|text-indent)\s*:\s*-?(?:[1-9]|0\.\d*[1-9])'
    r'|line-height\s*:|page-break-(?:before|after)\s*:\s*always'
    r'|aurora-paragraphs|<(?:b|strong|i|em|u|s|strike|sup|sub|ol|ul|li|h[1-6])(?:\s|>))',
    re.I)

_TOKEN_RE = re.compile(r'\{\{(?:data_hora|data|hora|clipboard|area_transferencia|cursor)\}\}')


def has_rich_formatting(html: str) -> bool:
    # Imagens data URI pedem HTML no clipboard mesmo sem negrito ou itálico.
    if not html:
        return False
    if "<img" in html.lower() and "data:image/" in html.lower():
        return True
    # Qt coloca font-family/font-size padrão no <body> de *todo* QTextEdit.
    # Não marcar texto simples como HTML formatado só por esse estilo base.
    content = re.sub(r"<body\b[^>]*>", "<body>", html, count=1, flags=re.I)
    return bool(_FORMATTED_RE.search(content))


def render_rich_html(html: str, clipboard_text: str, now: datetime | None = None) -> str:
    """Substitui tokens do editor HTML por texto escapado (mantém tags de estilo)."""
    def replace_token(match: re.Match[str]) -> str:
        value = render_snippet(match.group(0), clipboard_text, now).text
        return escape(value).replace('\n', '<br/>')

    return _TOKEN_RE.sub(replace_token, html)
