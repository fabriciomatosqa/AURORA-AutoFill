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


def utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, start: int, end: int | None = None) -> str:
    data = text.encode("utf-16-le")
    return data[start * 2:None if end is None else end * 2].decode("utf-16-le")


@dataclass(frozen=True)
class EditSnapshot:
    context: FocusContext
    text: str
    start: int
    end: int
    identity: tuple[str, ...] = ()

    def shortcut_range(self, shortcut: str) -> tuple[int, int] | None:
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
