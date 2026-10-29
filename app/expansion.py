"""Small immutable contracts shared by the keyboard hook and expansion stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class FocusContext:
    window: int | None = None
    control: int | None = None


@dataclass(frozen=True)
class ExpansionCandidate:
    identifier: int
    shortcut: str
    revision: int
    context: FocusContext
    created: float = field(default_factory=monotonic)
    selected_shortcut: str | None = None


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, start: int, end: int | None = None) -> str:
    data = text.encode("utf-16-le")
    return data[start * 2:None if end is None else end * 2].decode("utf-16-le")


def prefix_offset(text: str, prefix: str) -> int:
    """Map a rendered prefix to a native UTF-16 caret, including CRLF editors."""
    wanted = prefix.replace('\r\n', '\n').replace('\r', '\n')
    offset = 0
    for character in wanted:
        if offset >= len(text):
            raise ValueError('O texto mudou antes de posicionar o cursor.')
        current = text[offset]
        step = 2 if text[offset:offset + 2] == '\r\n' else 1
        if ('\n' if current == '\r' else current) != character:
            raise ValueError('O texto mudou antes de posicionar o cursor.')
        offset += step
    return utf16_length(text[:offset])


@dataclass(frozen=True)
class EditSnapshot:
    context: FocusContext
    text: str
    start: int
    end: int
    identity: tuple[str, ...] = ()

    def shortcut_range(self, shortcut: str) -> tuple[int, int] | None:
        # An explicit picker request inserts at the caret or replaces the
        # existing selection; there is no typed abbreviation to erase.
        if shortcut == "":
            return (self.start, self.end) if 0 <= self.start <= self.end <= utf16_length(self.text) else None
        if self.start != self.end or self.start < utf16_length(shortcut):
            return None
        begin = self.start - utf16_length(shortcut)
        if utf16_slice(self.text, begin, self.start) != shortcut:
            return None
        return begin, self.start

    def replace(self, begin: int, end: int, text: str) -> str:
        return utf16_slice(self.text, 0, begin) + text + utf16_slice(self.text, end)


@dataclass
class ClipboardLease:
    identifier: int
    original: Any
    text: str
    token: bytes
    sequence: int | None
    consumed: bool = False


@dataclass
class ExpansionOperation:
    candidate: ExpansionCandidate
    before: EditSnapshot | None
    text: str
    left_moves: int
    cursor_prefix: str = ""
    rich_html: str = ""
    stage: str = "prepared"
    deadline: float = 0
    lease: ClipboardLease | None = None
    document_text: str = ""
    document_cursor_prefix: str = ""
    image_count: int = 0
    image_only: bool = False
    images_confirmed: bool = False
    feedback_played: bool = False
    # Segunda via para Word/Teams: só cola após Ctrl+C confirmar que a seleção
    # contém exatamente o atalho; não depende da leitura integral por UIA.
    keyboard_verify: bool = False
    verify_original: Any = None
    verify_marker: str = ""
    verify_sequence: int | None = None
    verify_select_keyboard: bool = False
    # Teams/WebView: não anunciar RTF Office junto com o HTML ao colar.
    teams_web_html: bool = False
    tracked_replace: bool = False
    word_native: bool = False
    word_request: Any = None
