"""Paragraph editing commands, independent of ribbon/dialog geometry."""
from __future__ import annotations

from functools import cmp_to_key
import re

from PySide6.QtCore import QCollator, QEvent, QLocale, QObject, Qt, Signal
from PySide6.QtGui import (QColor, QKeySequence, QShortcut, QTextBlockFormat, QTextCursor, QTextFormat,
                           QTextList, QTextListFormat, QTextOption)

from .paragraph_format import (ALIGNMENTS, OPTIONS_PROPERTY, PX_PER_CM, apply_settings,
                                document_blocks, normalize_contextual_spacing,
                                options, remember_geometry, selected_blocks, set_options)


class ParagraphEditor(QObject):
    updated = Signal()

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self._normalizing = False
        self._changed_range = None
        editor.document().contentsChange.connect(self._contents_changed)
        editor.cursorPositionChanged.connect(self.updated)
        editor.selectionChanged.connect(self.updated)
        editor.textChanged.connect(self._document_changed)
        editor.installEventFilter(self)
        # Scope Word-style paragraph shortcuts to the message editor only.
        commands = {'Ctrl+L':lambda:self.align('left'), 'Ctrl+E':lambda:self.align('center'),
                    'Ctrl+R':lambda:self.align('right'), 'Ctrl+J':lambda:self.align('justify'),
                    'Ctrl+M':lambda:self.indent(1), 'Ctrl+Shift+M':lambda:self.indent(-1),
                    'Ctrl+1':lambda:self.apply({'line_mode':'single'}),
                    'Ctrl+2':lambda:self.apply({'line_mode':'double'}),
                    'Ctrl+5':lambda:self.apply({'line_mode':'onehalf'}),
                    'Ctrl+Shift+8':self._toggle_marks}
        for key, callback in commands.items():
            shortcut = QShortcut(QKeySequence(key), editor)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(callback)

    def _toggle_marks(self):
        flags = self.editor.document().defaultTextOption().flags()
        self.show_marks(not bool(flags & QTextOption.ShowLineAndParagraphSeparators))
        self.updated.emit()

    def _contents_changed(self, position, removed, added):
        if self._normalizing:
            return
        start, end = position, position + added
        if self._changed_range is not None:
            start = min(start, self._changed_range[0])
            end = max(end, self._changed_range[1])
        self._changed_range = start, end

    def _document_changed(self):
        if self._normalizing:
            return
        self._normalizing = True
        try:
            region, self._changed_range = self._changed_range, None
            if region is not None:
                normalize_contextual_spacing(self.editor.document(), *region)
        finally:
            self._normalizing = False
        self.editor.viewport().update()
        self.updated.emit()

    def _edit(self, transform):
        original = self.editor.textCursor()
        blocks = list(selected_blocks(self.editor))
        cursor = QTextCursor(original)
        cursor.beginEditBlock()
        for block in blocks:
            fmt = block.blockFormat()
            transform(fmt, block)
            remember_geometry(fmt)
            if options(fmt):
                self.editor.document().setProperty('auroraHasParagraphMetadata', True)
            QTextCursor(block).setBlockFormat(fmt)
        cursor.endEditBlock()
        self.editor.setTextCursor(original)
        self.editor.setFocus()
        self.updated.emit()

    def apply(self, settings):
        self._edit(lambda fmt, _: apply_settings(fmt, settings))

    def align(self, alignment):
        if alignment in ALIGNMENTS:
            self.apply({"alignment": alignment})

    def shade(self, color):
        def transform(fmt, _):
            if color is None:
                fmt.clearProperty(QTextFormat.BackgroundBrush)
            else:
                fmt.setBackground(QColor(color))
        self._edit(transform)

    def border(self, mode, color='#4f6b86', width=1):
        def transform(fmt, _):
            opts = options(fmt)
            if mode == 'none':
                for key in ('border', 'border_color', 'border_width'):
                    opts.pop(key, None)
            else:
                opts.update(border=mode, border_color=QColor(color).name(), border_width=width)
            set_options(fmt, opts)
        self._edit(transform)

    def list(self, style=None, mode='bullet', *, toggle=False):
        blocks = list(selected_blocks(self.editor))
        if not blocks:
            return
        if toggle and all(block.textList() is not None
                          and block.textList().format().style() == style
                          and options(block.blockFormat()).get('list_mode', mode) == mode for block in blocks):
            style = None
        root = self.editor.textCursor()
        root.beginEditBlock()
        if style is None:
            for block in blocks:
                listing = block.textList()
                if listing is not None:
                    listing.remove(block)
                fmt = block.blockFormat()
                fmt.setIndent(0)
                opts = options(fmt)
                opts.pop('list_mode', None)
                set_options(fmt, opts)
                QTextCursor(block).setBlockFormat(fmt)
        else:
            self.editor.document().setProperty('auroraHasParagraphMetadata', True)
            current = blocks[0].textList()
            fmt = QTextListFormat(current.format()) if current is not None else QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(max(1, fmt.indent()))
            previous = blocks[0].previous().textList()
            if (previous is not None and previous.format().style() == style
                    and previous.format().indent() == fmt.indent()):
                listing = previous
            else:
                listing = QTextCursor(blocks[0]).createList(fmt)
            for block in blocks:
                listing.add(block)
                bf = block.blockFormat()
                bf.setIndent(0)
                opts = options(bf)
                opts['list_mode'] = mode
                set_options(bf, opts)
                QTextCursor(block).setBlockFormat(bf)
        root.endEditBlock()
        self.editor.setFocus()
        self.updated.emit()

    def indent(self, delta):
        root = self.editor.textCursor()
        blocks = list(selected_blocks(self.editor))
        root.beginEditBlock()
        groups = {}
        for block in blocks:
            listing = block.textList()
            fmt = block.blockFormat()
            if listing is None:
                margin = fmt.leftMargin() + fmt.indent() * self.editor.document().indentWidth()
                fmt.setIndent(0)
                fmt.setLeftMargin(max(0, min(30 * PX_PER_CM, margin + delta * 1.25 * PX_PER_CM)))
                remember_geometry(fmt)
                if options(fmt):self.editor.document().setProperty('auroraHasParagraphMetadata', True)
                QTextCursor(block).setBlockFormat(fmt)
                continue
            old = listing.format()
            level = old.indent() + delta
            if level < 1:
                listing.remove(block)
                fmt = block.blockFormat()
                opts = options(fmt)
                opts.pop('list_mode', None)
                set_options(fmt, opts)
                fmt.setIndent(0)
                QTextCursor(block).setBlockFormat(fmt)
                continue
            level = min(9, level)
            mode = options(fmt).get('list_mode')
            next_format = QTextListFormat(old)
            next_format.setIndent(level)
            if level != old.indent():
                next_format.setStart(1)
            if mode == 'multilevel':
                next_format.setStyle((QTextListFormat.ListDecimal, QTextListFormat.ListLowerAlpha,
                                      QTextListFormat.ListLowerRoman)[(level-1) % 3])
            elif mode == 'bullet':
                next_format.setStyle((QTextListFormat.ListDisc, QTextListFormat.ListCircle,
                                      QTextListFormat.ListSquare)[(level-1) % 3])
            key = (listing.objectIndex(), level, next_format.style())
            target = groups.get(key)
            if target is None:
                previous = block.previous().textList()
                if (previous is not None and previous.format().indent() == level
                        and previous.format().style() == next_format.style()):
                    target = previous
                else:
                    target = QTextCursor(block).createList(next_format)
                groups[key] = target
            target.add(block)
        root.endEditBlock()
        self.editor.setFocus()
        self.updated.emit()

    def show_marks(self, enabled):
        option = self.editor.document().defaultTextOption()
        marks = QTextOption.ShowTabsAndSpaces | QTextOption.ShowLineAndParagraphSeparators
        option.setFlags(option.flags() | marks if enabled else option.flags() & ~marks)
        self.editor.document().setDefaultTextOption(option)
        self.editor.viewport().update()

    def eventFilter(self, watched, event):
        if (watched is self.editor and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Tab, Qt.Key_Backtab)
                and self.editor.textCursor().currentList() is not None
                and (self.editor.textCursor().hasSelection()
                     or self.editor.textCursor().positionInBlock() == 0)):
            self.indent(-1 if event.key() == Qt.Key_Backtab or event.modifiers() & Qt.ShiftModifier else 1)
            return True
        return super().eventFilter(watched, event)

    def sort(self, *, numeric=False, descending=False, header=False):
        blocks = (list(selected_blocks(self.editor)) if self.editor.textCursor().hasSelection()
                  else list(document_blocks(self.editor.document())))
        if len(blocks) < 2:
            raise ValueError('Selecione pelo menos dois parágrafos para classificar.')
        table = QTextCursor(blocks[0]).currentTable()
        cell = table.cellAt(QTextCursor(blocks[0])) if table is not None else None
        records = []
        for block in blocks:
            cursor = QTextCursor(block)
            other_table = cursor.currentTable()
            if other_table != table or (table is not None and table.cellAt(cursor) != cell):
                raise ValueError('Classifique parágrafos de uma mesma área de texto ou célula.')
            runs = []
            fragment = block.begin()
            while not fragment.atEnd():
                item = fragment.fragment()
                if item.isValid():
                    runs.append((item.text(), item.charFormat()))
                fragment += 1
            listing = block.textList()
            records.append((block.text(), block.blockFormat(), runs,
                            (listing.objectIndex(), listing.format()) if listing is not None else None))
        if numeric:
            def sort_key(record):
                value = record[0].strip().replace('.', '').replace(',', '.')
                try:
                    return (0, float(value))
                except ValueError:
                    return (1, record[0].casefold())
            ordered = sorted(records[1:] if header else records, key=sort_key, reverse=descending)
        else:
            collator = QCollator(QLocale('pt_BR'))
            collator.setCaseSensitivity(Qt.CaseInsensitive)
            collator.setNumericMode(True)
            ordered = sorted(records[1:] if header else records,
                             key=cmp_to_key(lambda a,b:collator.compare(a[0],b[0])), reverse=descending)
        if header:
            ordered.insert(0, records[0])
        cursor = QTextCursor(self.editor.document())
        start = blocks[0].position()
        cursor.setPosition(start)
        cursor.setPosition(blocks[-1].position() + blocks[-1].length() - 1, QTextCursor.KeepAnchor)
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        lists = {}
        for index, (_, formatting, runs, listing) in enumerate(ordered):
            fmt = QTextBlockFormat(formatting)
            fmt.clearProperty(QTextFormat.ObjectIndex)
            if index:
                cursor.insertBlock(fmt)
            else:
                cursor.setBlockFormat(fmt)
            for text, char_format in runs:
                cursor.insertText(text, char_format)
            if listing is not None:
                identifier, list_format = listing
                target = lists.get(identifier)
                if target is None:
                    existing = self.editor.document().object(identifier)
                    target = existing if isinstance(existing, QTextList) else cursor.createList(list_format)
                    lists[identifier] = target
                target.add(cursor.block())
        cursor.endEditBlock()
        finish = cursor.position()
        cursor.setPosition(start)
        cursor.setPosition(finish, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.updated.emit()
