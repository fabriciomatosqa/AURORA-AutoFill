"""Remove only a selected QTextCharFormat color, preserving every other style.

Unlike mergeCharFormat(QTextCharFormat()), clearing a property on each source
fragment actually removes a previously applied foreground/background brush.
"""
from __future__ import annotations

from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextFormat


def clear_selected_color(editor, *, highlight: bool) -> None:
    """Reset the foreground or highlight to the document's automatic color.

    For selected text, use source character-format runs instead of replacing
    all formatting. Without selection, only change the insertion format.
    """
    key = (QTextFormat.BackgroundBrush if highlight
           else QTextFormat.ForegroundBrush)
    selection = QTextCursor(editor.textCursor())
    if not selection.hasSelection():
        fmt = QTextCharFormat(editor.currentCharFormat())
        fmt.clearProperty(key)
        editor.setCurrentCharFormat(fmt)
        editor.setFocus()
        return

    start, end = selection.selectionStart(), selection.selectionEnd()
    changes = []
    block = editor.document().findBlock(start)
    while block.isValid() and block.position() < end:
        for fragment in block:
            if not fragment.isValid():
                continue
            left = max(start, fragment.position())
            right = min(end, fragment.position() + fragment.length())
            if left >= right:
                continue
            fmt = QTextCharFormat(fragment.charFormat())
            if fmt.hasProperty(key):
                fmt.clearProperty(key)
                changes.append((left, right, fmt))
        block = block.next()

    if changes:
        selection.beginEditBlock()
        try:
            for left, right, fmt in changes:
                target = QTextCursor(editor.document())
                target.setPosition(left)
                target.setPosition(right, QTextCursor.KeepAnchor)
                target.setCharFormat(fmt)
        finally:
            selection.endEditBlock()
    editor.setTextCursor(selection)
    editor.setFocus()
