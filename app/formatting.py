"""Renderização simples de formatação no clipboard (sem dependências da UI)."""
from __future__ import annotations

from datetime import datetime
from html import escape
import re

from .core import render_snippet

_FORMATTED_RE = re.compile(r'(?:font-weight\s*:\s*(?:bold|[6-9]00)|font-style\s*:\s*italic|text-decoration[^;\"]*underline|<(?:b|strong|i|em|u)(?:\s|>))', re.I)
_TOKEN_RE = re.compile(r'\{\{(?:data_hora|data|hora|clipboard|area_transferencia|cursor)\}\}')


def has_rich_formatting(html: str) -> bool:
    return bool(html and _FORMATTED_RE.search(html))


def render_rich_html(html: str, clipboard_text: str, now: datetime | None = None) -> str:
    """Substitui tokens do editor HTML por texto escapado (mantém tags de estilo)."""
    def replace_token(match: re.Match[str]) -> str:
        value = render_snippet(match.group(0), clipboard_text, now).text
        return escape(value).replace('\n', '<br/>')

    return _TOKEN_RE.sub(replace_token, html)