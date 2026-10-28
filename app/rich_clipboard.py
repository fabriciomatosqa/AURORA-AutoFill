"""Representações interoperáveis de texto rico para Word e editores WebView.

QTextEdit serializa estilos numa árvore HTML Qt; muitos destinos Windows
preferem um fragmento HTML simples ou Rich Text Format. Emitimos os dois
sem alterar os snippets salvos e sem rasterizar o texto como imagem.
"""
from __future__ import annotations

from html import escape
from io import StringIO
from dataclasses import dataclass
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextBlockFormat, QTextCharFormat, QTextListFormat, QTextFormat
from .paragraph_format import (OPTIONS_PROPERTY, add_metadata, document_blocks,
                                document_from_html, options)


@dataclass
class Paragraph:
    runs: list
    formatting: object
    listing: object = None
    list_id: int = -1
    number: int = 1
    marker: str = ''


def _paragraphs(html):
    document = document_from_html(html)
    result = []
    for block in document_blocks(document):
        row = []
        fragment = block.begin()
        while not fragment.atEnd():
            value = fragment.fragment()
            if value.isValid():
                row.append((value.text(), value.charFormat()))
            fragment += 1
        listing = block.textList()
        result.append(Paragraph(row,block.blockFormat(),
                                listing.format() if listing is not None else None,
                                listing.objectIndex() if listing is not None else -1,
                                listing.itemNumber(block)+listing.format().start() if listing is not None else 1,
                                listing.itemText(block) if listing is not None else ''))
    return result


def _runs(html: str):
    return [paragraph.runs for paragraph in _paragraphs(html)]


def _color(formatting: QTextCharFormat, property_id: int) -> QColor | None:
    if not formatting.hasProperty(property_id):
        return None
    if property_id == QTextFormat.ForegroundBrush:
        brush = formatting.foreground()
    else:
        brush = formatting.background()
    if brush.style() == Qt.NoBrush:
        return None
    result = brush.color()
    return result if result.isValid() and result.alpha() else None


def _family(fmt: QTextCharFormat) -> str | None:
    families = fmt.fontFamilies()
    if families:
        return str(families[0])
    return None


def _legacy_interoperable_html(html: str) -> str:
    """HTML interoperável com parágrafos reais e estilos por fragmento.

    Blocos com texto viram parágrafos reais; blocos vazios viram
    quebras dentro do parágrafo adjacente. Assim os destinos WebView/Office
    recebem blocos sem <br> soltos e Qt não duplica os espaçamentos.
    Imagens continuam na rota independente, sem rasterizar o texto.
    """
    # O Qt interpreta <p><br></p> como *duas* quebras e ignora <p></p>.
    # Guardar os blocos vazios como quebras INTERNAS do parágrafo anterior
    # preserva a contagem sem depender de <br> soltos entre divs.
    paragraphs = []
    pending_empty = 0
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
                styles.append(f"background-color:{highlight.name()}")
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
            if fmt.verticalAlignment() == QTextCharFormat.AlignSuperScript:
                styles.append('vertical-align:super')
            elif fmt.verticalAlignment() == QTextCharFormat.AlignSubScript:
                styles.append('vertical-align:sub')
            # Quebras suaves (Shift+Enter/\u2028) devem viajar dentro do
            # mesmo parágrafo como <br>, não como caracteres invisíveis.
            escaped = escape(text).replace("\r\n", "\n").replace("\r", "\n")
            for separator in ("\n", "\u2028", "\u2029"):
                escaped = escaped.replace(separator, "<br>")
            span = f'<span style="{";".join(styles)}">{escaped}</span>' if styles else escaped
            # Alguns editores Office antigos utilizam <font color> em vez de
            # color CSS. Fornecer ambos sem alterar a semântica do fragmento.
            if color is not None:
                span = f'<font color="{color.name()}">{span}</font>'
            pieces.append(span)
        body = "".join(pieces)
        if not body:
            pending_empty += 1
            continue
        if paragraphs:
            if pending_empty:
                paragraphs[-1] += "<br>" * pending_empty
        elif pending_empty:
            body = "<br>" * pending_empty + body
        paragraphs.append(body)
        pending_empty = 0
    if not paragraphs:
        # Apenas blocos vazios. O primeiro não introduz quebra por si só.
        paragraphs.append("<br>" * max(0, pending_empty - 1))
    elif pending_empty:
        paragraphs[-1] += "<br>" * pending_empty
    return "<div>" + "".join(f'<p style="margin:0">{body}</p>'
                           for body in paragraphs) + "</div>"


def _has_paragraph_formatting(html, paragraphs):
    if re.search(r'(?:margin-(?:top|bottom|left|right)|text-indent)\s*:\s*-?(?:[1-9]|0\.\d*[1-9])',html,re.I):
        return True
    for paragraph in paragraphs:
        fmt = paragraph.formatting
        if (paragraph.listing is not None or options(fmt) or fmt.headingLevel()
                or fmt.alignment() & (Qt.AlignHCenter|Qt.AlignRight|Qt.AlignJustify)
                or fmt.leftMargin() or fmt.rightMargin() or fmt.textIndent() or fmt.indent()
                or fmt.lineHeightType() or fmt.hasProperty(QTextFormat.BackgroundBrush)
                or fmt.pageBreakPolicy()):
            return True
    return False


def _span_html(text, fmt):
    if '\ufffc' in text:
        raise ValueError('Não converter HTML com imagens por essa rota.')
    styles = []
    color, highlight = _color(fmt,QTextFormat.ForegroundBrush), _color(fmt,QTextFormat.BackgroundBrush)
    if color is not None:styles.append('color:'+color.name())
    if highlight is not None:styles.append('background-color:'+highlight.name())
    family = _family(fmt)
    if family:styles.append("font-family:'"+escape(family,quote=True)+"'")
    if fmt.fontPointSize()>0:styles.append(f'font-size:{fmt.fontPointSize():g}pt')
    if fmt.fontWeight()>=700:styles.append('font-weight:bold')
    if fmt.fontItalic():styles.append('font-style:italic')
    decorations = [name for name, active in (('underline',fmt.fontUnderline()),('line-through',fmt.fontStrikeOut())) if active]
    if decorations:styles.append('text-decoration:'+' '.join(decorations))
    if fmt.verticalAlignment()==QTextCharFormat.AlignSuperScript:styles.append('vertical-align:super')
    if fmt.verticalAlignment()==QTextCharFormat.AlignSubScript:styles.append('vertical-align:sub')
    value = escape(text).replace('\r\n','\n').replace('\r','\n')
    for separator in ('\n','\u2028','\u2029'):value=value.replace(separator,'<br>')
    value = f'<span style="{";".join(styles)}">{value}</span>' if styles else value
    return f'<font color="{color.name()}">{value}</font>' if color is not None else value


def _paragraph_alignment(fmt):
    return ('center' if fmt.alignment()&Qt.AlignHCenter else 'right' if fmt.alignment()&Qt.AlignRight
            else 'justify' if fmt.alignment()&Qt.AlignJustify else 'left')


def _paragraph_css(paragraph):
    fmt, opts = paragraph.formatting, options(paragraph.formatting)
    alignment = _paragraph_alignment(fmt)
    left = fmt.leftMargin() + (fmt.indent()*40 if paragraph.listing is None else 0)
    styles = ['margin:0',f'margin-top:{fmt.topMargin():g}px',f'margin-bottom:{fmt.bottomMargin():g}px',
              f'margin-left:{left:g}px',f'margin-right:{fmt.rightMargin():g}px',
              f'text-indent:{fmt.textIndent():g}px','text-align:'+alignment,'white-space:pre-wrap']
    kind, height = fmt.lineHeightType(), fmt.lineHeight()
    if kind==QTextBlockFormat.ProportionalHeight.value:styles.append(f'line-height:{height:g}%')
    elif kind in (QTextBlockFormat.FixedHeight.value,QTextBlockFormat.MinimumHeight.value):
        styles.extend((f'line-height:{height:g}px','mso-line-height-rule:'+('exactly' if kind==2 else 'at-least')))
    color = _color(fmt,QTextFormat.BackgroundBrush)
    if color is not None:styles.append('background-color:'+color.name())
    if fmt.pageBreakPolicy()&QTextFormat.PageBreak_AlwaysBefore:styles.append('page-break-before:always')
    if fmt.pageBreakPolicy()&QTextFormat.PageBreak_AlwaysAfter:styles.append('page-break-after:always')
    if opts.get('keep_next'):styles.append('page-break-after:avoid')
    if opts.get('keep_lines'):styles.append('page-break-inside:avoid')
    if 'widow_control' in opts:styles.extend((f'widows:{2 if opts["widow_control"] else 1}',f'orphans:{2 if opts["widow_control"] else 1}'))
    if opts.get('contextual'):styles.append('mso-contextual-spacing:yes')
    if opts.get('no_hyphen'):styles.append('hyphens:none')
    level = opts.get('outline_level',fmt.headingLevel())
    if level:styles.append(f'mso-outline-level:{level}')
    border = opts.get('border','none')
    sides = ('top','right','bottom','left') if border in ('all','outside') else (border,)
    if border!='none':
        for side in sides:styles.append(f'border-{side}:{opts.get("border_width",1):g}px solid {opts.get("border_color","#4f6b86")}')
    return ';'.join(styles)


def interoperable_html(html: str) -> str:
    paragraphs = _paragraphs(html)
    if not _has_paragraph_formatting(html,paragraphs):
        return _legacy_interoperable_html(html)
    output, stack, metadata = ['<div>'], [], []
    def close():
        entry = stack.pop()
        output.append('</li></'+entry['tag']+'>')
    for index, paragraph in enumerate(paragraphs):
        opts = options(paragraph.formatting)
        if opts:metadata.append([index,opts])
        body = ''.join(_span_html(text,fmt) for text,fmt in paragraph.runs)
        style = _paragraph_css(paragraph)
        if not body:
            style += ';-qt-paragraph-type:empty'
            body = '<br>'
        if paragraph.listing is None:
            while stack:close()
            output.append(f'<p align="{_paragraph_alignment(paragraph.formatting)}" style="{escape(style,quote=True)}">{body}</p>')
            continue
        listing = paragraph.listing
        level = max(1,min(9,listing.indent()))
        while stack and stack[-1]['level']>level:close()
        if stack and stack[-1]['level']==level and stack[-1]['id']!=paragraph.list_id:close()
        if not stack or stack[-1]['level']<level:
            bullet = listing.style() in (QTextListFormat.ListDisc,QTextListFormat.ListCircle,QTextListFormat.ListSquare)
            tag = 'ul' if bullet else 'ol'
            types = {QTextListFormat.ListDisc:'disc',QTextListFormat.ListCircle:'circle',QTextListFormat.ListSquare:'square',
                     QTextListFormat.ListDecimal:'1',QTextListFormat.ListLowerAlpha:'a',QTextListFormat.ListUpperAlpha:'A',
                     QTextListFormat.ListLowerRoman:'i',QTextListFormat.ListUpperRoman:'I'}
            relative = level-(stack[-1]['level'] if stack else 0)
            extra = '' if bullet else f' start="{paragraph.number}"'
            output.append(f'<{tag} type="{types.get(listing.style(),"1")}"{extra} style="margin:0;padding-left:{relative*40}px;-qt-list-indent:{level}">')
            stack.append({'level':level,'id':paragraph.list_id,'tag':tag,'first':True})
        if not stack[-1].pop('first',False):output.append('</li>')
        output.append(f'<li align="{_paragraph_alignment(paragraph.formatting)}" style="{escape(style,quote=True)}">{body}')
    while stack:close()
    output.append('</div>')
    result = ''.join(output)
    return add_metadata(result,metadata) if metadata else result


def mixed_paragraph_html(html: str) -> str:
    """Export extra paragraph CSS without rebuilding images or table cells.

    Qt's canonical HTML has one p/li/heading per visible document block.
    Table boundary markers are structural and do not produce an HTML block.
    """
    paragraphs = _paragraphs(html)
    if not _has_paragraph_formatting(html, paragraphs):
        return html
    document = document_from_html(html)
    blocks = list(document_blocks(document))
    visible = [paragraph for block, paragraph in zip(blocks, paragraphs)
               if not (block.length() == 1 and (document.characterAt(block.position()) in ('\ufdd0', '\ufdd1')
                                               or document.characterAt(block.position()-1) == '\ufdd1'))]
    canonical = document.toHtml()
    tags = re.compile(r'<(?:p|li|h[1-6])\b[^>]*>', re.I)
    if len(tags.findall(canonical)) != len(visible):
        # Preserve an unfamiliar structure intact instead of assigning a
        # paragraph's formatting to a different table cell.
        return html
    records = iter(visible)
    def style(match):
        tag = match[0]
        css = _paragraph_css(next(records))
        existing = re.search(r'\bstyle="([^"]*)"', tag)
        if existing:
            return tag[:existing.end(1)] + ';' + escape(css, quote=True) + tag[existing.end(1):]
        return tag[:-1] + ' style="' + escape(css, quote=True) + '">'
    result = tags.sub(style, canonical)
    metadata = [[index, options(paragraph.formatting)] for index, paragraph in enumerate(paragraphs)
                if options(paragraph.formatting)]
    return add_metadata(result, metadata) if metadata else result


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


def _twips(value):
    return max(-65535,min(65535,round(value*15)))


def _bullet(style):
    return {QTextListFormat.ListDisc:'•',QTextListFormat.ListCircle:'◦',QTextListFormat.ListSquare:'▪'}.get(style)


def _write_list_tables(buf, paragraphs):
    definitions = {}
    for paragraph in paragraphs:
        if paragraph.listing is not None and paragraph.list_id not in definitions:
            definitions[paragraph.list_id] = (len(definitions)+1,paragraph)
    if not definitions:
        return {}
    buf.write(r'{\*\listtable')
    nfc = {QTextListFormat.ListDecimal:0,QTextListFormat.ListUpperRoman:1,
           QTextListFormat.ListLowerRoman:2,QTextListFormat.ListUpperAlpha:3,QTextListFormat.ListLowerAlpha:4}
    for _, (identifier, paragraph) in definitions.items():
        listing = paragraph.listing
        mode = options(paragraph.formatting).get('list_mode')
        buf.write(f'{{\\list\\listtemplateid{identifier}\\listhybrid')
        for level in range(9):
            style = listing.style()
            if mode=='multilevel' and level != listing.indent()-1:
                style = (QTextListFormat.ListDecimal,QTextListFormat.ListLowerAlpha,QTextListFormat.ListLowerRoman)[level%3]
            symbol = _bullet(style)
            code = 23 if symbol else nfc.get(style,0)
            start = listing.start() if level==listing.indent()-1 else 1
            buf.write(f'{{\\listlevel\\levelnfc{code}\\levelnfcn{code}\\leveljc0\\leveljcn0\\levelfollow0\\levelstartat{start}')
            if symbol:
                buf.write("{\\leveltext\\'01"+_rtf_escape(symbol)+r';}{\levelnumbers;}')
            else:
                buf.write('{\\leveltext\\\'02\\\''+f'{level:02x}'+'.;}{\\levelnumbers\\\'01;}')
            indent = 600*(level+1)
            buf.write(f'\\f0\\fi-300\\li{indent}\\jclisttab\\tx{indent}'+'}')
        buf.write(f'\\listid{identifier}'+'}')
    buf.write('}')
    buf.write(r'{\*\listoverridetable')
    for identifier,_ in definitions.values():
        buf.write(f'{{\\listoverride\\listid{identifier}\\listoverridecount0\\ls{identifier}}}')
    buf.write('}')
    return {key:value[0] for key,value in definitions.items()}


def _rtf_paragraph(paragraph, colors, lists):
    fmt, opts = paragraph.formatting, options(paragraph.formatting)
    controls = [r'\qc' if fmt.alignment()&Qt.AlignHCenter else r'\qr' if fmt.alignment()&Qt.AlignRight
                else r'\qj' if fmt.alignment()&Qt.AlignJustify else r'\ql']
    left = fmt.leftMargin() + (paragraph.listing.indent()*40 if paragraph.listing is not None else fmt.indent()*40)
    first = fmt.textIndent() - (20 if paragraph.listing is not None else 0)
    controls += [f'\\li{_twips(left)}',f'\\ri{_twips(fmt.rightMargin())}',f'\\fi{_twips(first)}',
                 f'\\sb{_twips(opts.get("base_top",fmt.topMargin()))}',
                 f'\\sa{_twips(opts.get("base_bottom",fmt.bottomMargin()))}']
    if fmt.layoutDirection()==Qt.RightToLeft:controls.append(r'\rtlpar')
    kind,height = fmt.lineHeightType(),fmt.lineHeight()
    if kind==QTextBlockFormat.ProportionalHeight.value:
        controls.append(f'\\sl{max(1,round(height/100*240))}\\slmult1')
    elif kind in (QTextBlockFormat.FixedHeight.value,QTextBlockFormat.MinimumHeight.value):
        controls.append(f'\\sl{(-1 if kind==2 else 1)*_twips(height)}\\slmult0')
    if fmt.pageBreakPolicy()&QTextFormat.PageBreak_AlwaysBefore:controls.append(r'\pagebb')
    for key, word in (('keep_next',r'\keepn'),('keep_lines',r'\keep'),('no_line_numbers',r'\noline'),
                      ('no_hyphen',r'\hyphpar0'),('mirror',r'\indmirror'),('collapsed',r'\collapsed'),
                      ('contextual',r'\contextualspace')):
        if opts.get(key):controls.append(word)
    if 'widow_control' in opts:controls.append(r'\widctlpar' if opts['widow_control'] else r'\nowidctlpar')
    heading = opts.get('outline_level',fmt.headingLevel())
    if heading:controls.append(f'\\outlinelevel{heading-1}')
    wrap = opts.get('text_wrap')
    if wrap in {'none','all','firstlast','first','last'}:
        controls.append('\\'+{'none':'txbxtwno','all':'txbxtwalways','firstlast':'txbxtwfirstlast',
                                'first':'txbxtwfirst','last':'txbxtwlast'}[wrap])
    color = _color(fmt,QTextFormat.BackgroundBrush)
    if color is not None:controls.append(f'\\shading0\\cbpat{colors[color.name()]}')
    border = opts.get('border','none')
    if border!='none':
        sides = ('top','right','bottom','left') if border in ('all','outside') else (border,)
        if border=='all':sides += ('between',)
        for side in sides:
            name = {'top':'t','right':'r','bottom':'b','left':'l','between':'btw'}[side]
            controls.append(f'\\brdr{name}\\brdrs\\brdrw{max(1,_twips(opts.get("border_width",1)))}'
                            f'\\brdrcf{colors[opts.get("border_color","#4f6b86")]}\\brsp30')
    tab_types = {0:'',1:r'\tqr',2:r'\tqc',3:r'\tqdec'}
    for tab in fmt.tabPositions():
        position = tab.position
        spec = next((item for item in opts.get('tabs',[]) if abs(item['position']-position)<.5),None)
        leader = ('',r'\tldot',r'\tlhyph',r'\tlul')[spec.get('leader',0)] if spec else ''
        controls.append(tab_types.get(tab.type.value,'')+leader+f'\\tx{_twips(position)}')
    if paragraph.listing is not None:
        style = paragraph.listing.style()
        bullet = _bullet(style)
        marker = bullet or paragraph.marker
        # RichEdit's RTF reader uses Word 6 paragraph numbering. Supply that
        # native definition as well as Word's modern list tables. An unstarred
        # listtext group becomes literal text in readers without Word 97 lists.
        controls.append('{\\pntext\\f0 '+_rtf_escape(marker)+r'\tab}')
        legacy = {QTextListFormat.ListDecimal:r'\pndec',QTextListFormat.ListLowerAlpha:r'\pnlcltr',
                  QTextListFormat.ListUpperAlpha:r'\pnucltr',QTextListFormat.ListLowerRoman:r'\pnlcrm',
                  QTextListFormat.ListUpperRoman:r'\pnucrm'}
        definition = r'\pnlvlblt' if bullet else r'\pnlvlbody'+legacy.get(style,r'\pndec')
        prefix = bullet or paragraph.listing.numberPrefix()
        suffix = '' if bullet else paragraph.listing.numberSuffix() or '.'
        controls.append('{\\*\\pn'+definition+f'\\pnf0\\pnstart{paragraph.number}\\pnindent300\\pnhang'
                        +'{\\pntxtb '+_rtf_escape(prefix)+'}{\\pntxta '+_rtf_escape(suffix)+'}}')
        controls.append(f'\\ls{lists[paragraph.list_id]}\\ilvl{max(0,min(8,paragraph.listing.indent()-1))}')
    return ''.join(controls)+' '


def rich_text_rtf(html: str) -> bytes:
    """Formato RTF nativo do Windows, com cores de texto e realce por trecho."""
    paragraphs = _paragraphs(html)
    blocks = [paragraph.runs for paragraph in paragraphs]
    formatted = _has_paragraph_formatting(html,paragraphs)
    fonts: dict[str, int] = {"Segoe UI": 0}
    colors: dict[str, int] = {}
    for paragraph in paragraphs:
        fmt,opts = paragraph.formatting,options(paragraph.formatting)
        shade = _color(fmt,QTextFormat.BackgroundBrush)
        if shade is not None and shade.name() not in colors:colors[shade.name()] = len(colors)+1
        if opts.get('border','none')!='none':
            border = opts.get('border_color','#4f6b86')
            if border not in colors:colors[border] = len(colors)+1
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
    lists = _write_list_tables(buf,paragraphs)
    for index, row in enumerate(blocks):
        if index:
            buf.write(r"\par ")
        buf.write(r"\pard\plain ")
        if formatted:
            buf.write(_rtf_paragraph(paragraphs[index],colors,lists))
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
