"""Paragraph properties shared by the editor, saved HTML and clipboard.

Qt writes most block properties as HTML. The small, versioned metadata entry
preserves the additional Word pagination/border/tab settings that HTML drops.
It contains formatting only, never another copy of the message text.
"""
from __future__ import annotations

import base64
from html import escape
import json
import math
import re

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QPainter, QPen, QTextBlockFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextOption)

PX_PER_PT = 96 / 72
PX_PER_CM = 96 / 2.54
OPTIONS_PROPERTY = QTextFormat.UserProperty + 41
META_NAME = "aurora-paragraphs"
META_RE = re.compile(r'<meta\s+name=["\']aurora-paragraphs["\']\s+content=["\']([A-Za-z0-9_=\-]+)["\']\s*/?>', re.I)
ALIGNMENTS = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter,
              "right": Qt.AlignRight, "justify": Qt.AlignJustify}
LINE_MODES = {"single", "onehalf", "double", "multiple", "minimum", "exact"}
BOOL_OPTIONS = ("keep_next", "keep_lines", "widow_control", "no_line_numbers",
                "no_hyphen", "mirror", "collapsed", "contextual")
BORDER_MODES = {"none", "all", "outside", "top", "bottom", "left", "right"}


def number(value, default=0.0, minimum=-10000.0, maximum=10000.0):
    try:
        result = float(value)
        return max(minimum, min(maximum, result)) if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def normalize_options(raw):
    if not isinstance(raw, dict):
        return {}
    result = {key: raw[key] for key in BOOL_OPTIONS if type(raw.get(key)) is bool}
    if raw.get("border") in BORDER_MODES:
        result["border"] = raw["border"]
    if "border_color" in raw:
        color = QColor(str(raw["border_color"])[:32])
        if color.isValid():
            result["border_color"] = color.name()
    for key, minimum, maximum in (("border_width", .5, 6), ("base_top", 0, 600),
                                  ("base_bottom", 0, 600), ("tab_default", 8, 600)):
        if key in raw:
            result[key] = number(raw[key], minimum, minimum, maximum)
    if raw.get("list_mode") in {"bullet", "number", "multilevel"}:
        result["list_mode"] = raw["list_mode"]
    if raw.get("text_wrap") in {"none", "all", "firstlast", "first", "last"}:
        result["text_wrap"] = raw["text_wrap"]
    if 'outline_level' in raw:
        result['outline_level'] = int(number(raw['outline_level'],0,0,9))
    if isinstance(raw.get('geometry'),dict):
        result['geometry'] = {key:number(value,0,-4000 if key in ('left','right','first') else 0,4000)
                              for key,value in raw['geometry'].items()
                              if key in ('left','right','first','top','bottom','line_height','line_type')}
    if isinstance(raw.get("tabs"), list):
        tabs = []
        for item in raw["tabs"][:64]:
            if not isinstance(item, dict) or item.get("type") not in {"left", "right", "center", "decimal"}:
                continue
            tabs.append({"position": number(item.get("position"), 48, 1, 4000),
                         "type": item["type"], "leader": int(number(item.get("leader"), 0, 0, 3))})
        result["tabs"] = sorted(tabs, key=lambda item: item["position"])
    return result


def options(fmt):
    return normalize_options(fmt.property(OPTIONS_PROPERTY))


def set_options(fmt, raw):
    safe = normalize_options(raw)
    if safe:
        fmt.setProperty(OPTIONS_PROPERTY, safe)
    else:
        fmt.clearProperty(OPTIONS_PROPERTY)
    if "tabs" in safe or "tab_default" in safe:
        stops = {}
        if safe.get("tab_default"):
            step = safe["tab_default"]
            stops.update({round(step * i, 3): {"position": step * i, "type": "left"}
                          for i in range(1, min(256, math.ceil(4096 / step)) + 1)})
        stops.update({round(item["position"], 3): item for item in safe.get("tabs", [])})
        native = []
        types = {"left": QTextOption.LeftTab, "right": QTextOption.RightTab,
                 "center": QTextOption.CenterTab, "decimal": QTextOption.DelimiterTab}
        for _, item in sorted(stops.items()):
            tab = QTextOption.Tab()
            tab.position = item["position"]
            tab.type = types[item["type"]]
            tab.delimiter = ','
            native.append(tab)
        fmt.setTabPositions(native)


def exact_geometry(fmt):
    values = {'left':fmt.leftMargin(),'right':fmt.rightMargin(),'first':fmt.textIndent(),
              'top':fmt.topMargin(),'bottom':fmt.bottomMargin(),'line_height':fmt.lineHeight(),
              'line_type':fmt.lineHeightType()}
    return values if any(abs(value-round(value))>1e-7 for value in values.values()) else None


def remember_geometry(fmt):
    set_options(fmt, export_options(fmt))


def export_options(fmt):
    """Refresh geometry after native editing or contextual spacing changes."""
    opts = options(fmt)
    opts.pop('geometry',None)
    geometry = exact_geometry(fmt)
    if geometry:opts['geometry'] = geometry
    return opts


def document_blocks(document):
    block = document.begin()
    while block.isValid():
        yield block
        block = block.next()


def selected_blocks(editor):
    cursor = editor.textCursor()
    start, end = cursor.selectionStart(), cursor.selectionEnd()
    block = editor.document().findBlock(start)
    last = editor.document().findBlock(max(start, end - 1))
    while block.isValid():
        yield block
        if block == last:
            break
        block = block.next()


def serialize_document(document):
    html = document.toHtml()
    if document.property('auroraHasParagraphMetadata') is False:
        return html
    entries = []
    for block in document_blocks(document):
        fmt = block.blockFormat()
        opts = export_options(fmt)
        if opts:entries.append([block.blockNumber(),opts])
    if not entries:
        if document.property('auroraHasParagraphMetadata') is None:
            document.setProperty('auroraHasParagraphMetadata', False)
        return html
    document.setProperty('auroraHasParagraphMetadata', True)
    return add_metadata(html, entries)


def add_metadata(html, entries):
    data = json.dumps({"version": 1, "paragraphs": entries}, ensure_ascii=True,
                      separators=(',', ':')).encode('ascii')
    if len(data) > 1_000_000:
        raise ValueError("As opções de parágrafo excedem o limite do comando.")
    encoded = base64.urlsafe_b64encode(data).decode('ascii')
    marker = f'<meta name="{META_NAME}" content="{encoded}" />'
    html = META_RE.sub('',html)
    return html.replace('</head>',marker+'</head>',1) if '</head>' in html else marker+html


def read_metadata(html):
    match = META_RE.search(html)
    if not match or len(match[1]) > 1_400_000:
        return []
    try:
        data = json.loads(base64.urlsafe_b64decode(match[1]))
        entries = data.get('paragraphs') if data.get('version') == 1 else None
        if not isinstance(entries, list):
            return []
        result = []
        for entry in entries[:10000]:
            if (isinstance(entry, list) and len(entry) == 2 and type(entry[0]) is int
                    and 0 <= entry[0] < 100000):
                result.append((entry[0], normalize_options(entry[1])))
        return result
    except (ValueError, TypeError, AttributeError, RecursionError):
        return []


def restore_metadata(document, html, first_block=0):
    entries = read_metadata(html)
    if entries:
        document.setProperty('auroraHasParagraphMetadata', True)
    for index, opts in entries:
        block = document.findBlockByNumber(first_block + index)
        if block.isValid():
            cursor = QTextCursor(block)
            fmt = block.blockFormat()
            geometry = opts.get('geometry',{})
            for key,setter in (('left',fmt.setLeftMargin),('right',fmt.setRightMargin),('first',fmt.setTextIndent),
                               ('top',fmt.setTopMargin),('bottom',fmt.setBottomMargin)):
                if key in geometry:setter(geometry[key])
            if 'line_height' in geometry:
                fmt.setLineHeight(geometry['line_height'],int(number(geometry.get('line_type'),0,0,4)))
            set_options(fmt, opts)
            cursor.setBlockFormat(fmt)


def document_from_html(html):
    document = QTextDocument()
    document.setHtml(html)
    restore_metadata(document, html)
    return document


def settings_from_format(fmt):
    opts = options(fmt)
    alignment = next((name for name in ('center','right','justify')
                      if fmt.alignment() & ALIGNMENTS[name]), 'left')
    height_type = fmt.lineHeightType()
    height = fmt.lineHeight()
    mode, value = "single", 1.0
    if height_type == QTextBlockFormat.ProportionalHeight.value:
        mode, value = "multiple", height / 100
        if height == 150:
            mode = "onehalf"
        elif height == 200:
            mode = "double"
        elif height == 100:
            mode = "single"
    elif height_type == QTextBlockFormat.FixedHeight.value:
        mode, value = "exact", height / PX_PER_PT
    elif height_type == QTextBlockFormat.MinimumHeight.value:
        mode, value = "minimum", height / PX_PER_PT
    return {"alignment": alignment, "left": fmt.leftMargin() / PX_PER_CM,
            "right": fmt.rightMargin() / PX_PER_CM, "first": fmt.textIndent() / PX_PER_CM,
            "before": opts.get("base_top", fmt.topMargin()) / PX_PER_PT,
            "after": opts.get("base_bottom", fmt.bottomMargin()) / PX_PER_PT,
            "line_mode": mode, "line_value": value, "heading": opts.get('outline_level',fmt.headingLevel()),
            "page_before": bool(fmt.pageBreakPolicy() & QTextFormat.PageBreak_AlwaysBefore),
            "options": opts}


def apply_settings(fmt, raw):
    if raw.get("alignment") in ALIGNMENTS:
        fmt.setAlignment(ALIGNMENTS[raw["alignment"]])
    for key, setter, scale, low, high in (
        ("left", fmt.setLeftMargin, PX_PER_CM, -10, 30),
        ("right", fmt.setRightMargin, PX_PER_CM, -10, 30),
        ("first", fmt.setTextIndent, PX_PER_CM, -10, 30),
        ("before", fmt.setTopMargin, PX_PER_PT, 0, 400),
        ("after", fmt.setBottomMargin, PX_PER_PT, 0, 400)):
        if key in raw:
            setter(number(raw[key], 0, low, high) * scale)
    if "heading" in raw:
        # Outline level is structural: do not restyle the user's font as an
        # HTML h1..h6 when the snippet is reloaded.
        fmt.setHeadingLevel(0)
    if "page_before" in raw:
        policy = fmt.pageBreakPolicy() & ~QTextFormat.PageBreak_AlwaysBefore
        fmt.setPageBreakPolicy(policy | (QTextFormat.PageBreak_AlwaysBefore if raw["page_before"] else QTextFormat.PageBreak_Auto))
    mode = raw.get("line_mode")
    if mode in LINE_MODES:
        value = number(raw.get("line_value"), 1, .1, 400)
        if mode in {"single", "onehalf", "double", "multiple"}:
            factor = {"single": 1, "onehalf": 1.5, "double": 2}.get(mode, value)
            fmt.setLineHeight(factor * 100, QTextBlockFormat.ProportionalHeight.value)
        else:
            kind = QTextBlockFormat.FixedHeight if mode == "exact" else QTextBlockFormat.MinimumHeight
            fmt.setLineHeight(value * PX_PER_PT, kind.value)
    if "options" in raw:
        opts = {**options(fmt), **normalize_options(raw["options"])}
        if opts.get("contextual"):
            opts.update(base_top=fmt.topMargin(), base_bottom=fmt.bottomMargin())
        else:
            opts.pop('base_top', None)
            opts.pop('base_bottom', None)
        set_options(fmt, opts)
    if 'heading' in raw:
        opts = options(fmt)
        level = int(number(raw['heading'],0,0,9))
        if level:
            opts['outline_level'] = level
        else:
            opts.pop('outline_level',None)
        set_options(fmt,opts)
    return fmt


def normalize_contextual_spacing(document, start=None, end=None):
    changes = []
    if start is None:
        blocks = document_blocks(document)
    else:
        def affected():
            block = document.findBlock(max(0, start-1))
            last = document.findBlock(min(document.characterCount()-1, (end or start)+1)).next()
            while block.isValid():
                yield block
                if block == last:
                    break
                block = block.next()
        blocks = affected()
    for block in blocks:
        fmt = block.blockFormat()
        opts = options(fmt)
        if not opts.get('contextual'):
            continue
        def same(other):
            return (other.isValid() and settings_from_format(other.blockFormat())['heading']
                    == settings_from_format(fmt)['heading'])
        top = 0 if same(block.previous()) else opts.get('base_top', fmt.topMargin())
        bottom = 0 if same(block.next()) else opts.get('base_bottom', fmt.bottomMargin())
        if fmt.topMargin() != top or fmt.bottomMargin() != bottom:
            fmt.setTopMargin(top)
            fmt.setBottomMargin(bottom)
            changes.append((block, fmt))
    if changes:
        cursor = QTextCursor(document)
        cursor.joinPreviousEditBlock()
        for block, fmt in changes:
            QTextCursor(block).setBlockFormat(fmt)
        cursor.endEditBlock()


def paint_decorations(editor):
    """Borders/leaders that QTextDocument does not paint natively."""
    painter = QPainter(editor.viewport())
    painter.setRenderHint(QPainter.Antialiasing)
    dx, dy = editor.horizontalScrollBar().value(), editor.verticalScrollBar().value()
    block = editor.cursorForPosition(QPoint(0, 0)).block()
    layout = editor.document().documentLayout()
    while block.isValid():
        bounds = layout.blockBoundingRect(block).translated(-dx, -dy)
        if bounds.top() > editor.viewport().height():
            break
        fmt, opts = block.blockFormat(), options(block.blockFormat())
        border = opts.get('border', 'none')
        if border != 'none':
            left = editor.document().documentMargin() + fmt.leftMargin() + fmt.indent() * editor.document().indentWidth() - dx
            right = editor.document().size().width() - editor.document().documentMargin() - fmt.rightMargin() - dx
            rect = QRectF(left, bounds.top(), max(1, right-left), max(1, bounds.height())).adjusted(1, 1, -1, -1)
            color = QColor(opts.get('border_color', '#4f6b86'))
            painter.setPen(QPen(color, opts.get('border_width', 1)))
            def joined(other):
                other_opts = options(other.blockFormat()) if other.isValid() else {}
                return (other.isValid() and all(other_opts.get(key) == opts.get(key)
                                               for key in ('border','border_color','border_width'))
                        and other.blockFormat().leftMargin() == fmt.leftMargin()
                        and other.blockFormat().rightMargin() == fmt.rightMargin())
            if border in {'all', 'outside', 'left'}:
                painter.drawLine(rect.topLeft(), rect.bottomLeft())
            if border in {'all', 'outside', 'right'}:
                painter.drawLine(rect.topRight(), rect.bottomRight())
            if border in {'all', 'top'} or border == 'outside' and not joined(block.previous()):
                painter.drawLine(rect.topLeft(), rect.topRight())
            if border in {'all', 'bottom'} or border == 'outside' and not joined(block.next()):
                painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        tabs = opts.get('tabs', [])
        text = block.text() if tabs else ''
        for index, char in enumerate(text):
            if char != '\t':
                continue
            pos = len(text[:index].encode('utf-16-le')) // 2
            line = block.layout().lineForTextPosition(pos)
            if not line.isValid():
                continue
            x0 = line.cursorToX(pos)[0]
            x1 = line.cursorToX(pos + 1)[0]
            stop = next((item for item in tabs if item['position'] >= x1 - 2), None)
            if not stop or not stop.get('leader') or x1 - x0 < 6:
                continue
            painter.setFont(editor.document().defaultFont())
            painter.setPen(editor.palette().text().color())
            if stop['leader'] == 3:
                painter.drawLine(QPointF(bounds.left()+x0+2, bounds.top()+line.y()+line.ascent()),
                                 QPointF(bounds.left()+x1-2, bounds.top()+line.y()+line.ascent()))
            else:
                glyph = '.' if stop['leader'] == 1 else '–'
                advance = max(1, painter.fontMetrics().horizontalAdvance(glyph))
                count = max(0, int((x1-x0-4) / advance))
                painter.drawText(QPointF(bounds.left()+x0+2, bounds.top()+line.y()+line.ascent()), glyph*count)
        block = block.next()
    painter.end()
