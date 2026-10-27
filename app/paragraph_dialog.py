"""Aurora paragraph, tab-stop and sorting dialogs."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QStyle, QStyleOptionButton, QTabWidget, QVBoxLayout, QWidget)

from .inline_images import AuroraImageEditor
from .font_catalog import AuroraMeasureSpinBox
from .paragraph_format import PX_PER_CM, apply_settings, normalize_contextual_spacing
from .themes import set_ui_style, ui_color


DIALOG_STYLE = """
QDialog { background: #0c1d31; color: #effaff; }
QWidget#paragraphPage { background: #0c1d31; }
QLabel, QCheckBox, QGroupBox { color: #effaff; background: transparent; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 14px; height: 14px; }
QGroupBox { border: 1px solid #31536b; border-radius: 6px; margin-top: 12px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0px 4px; }
QTabWidget::pane { border: 1px solid #31536b; }
QTabBar::tab { background: #19364b; color: #effaff; padding: 7px 12px; }
QTabBar::tab:selected { background: #28546a; border-bottom: 2px solid #79ead8; }
QComboBox, QDoubleSpinBox { min-height: 22px; padding: 3px 6px; border: 1px solid #427084;
    border-radius: 4px; background: #18394d; color: #effaff; }
QPushButton { min-height: 25px; padding: 4px 10px; background: #19364b;
    color: #effaff; border: 1px solid #365a71; border-radius: 5px; }
QPushButton:hover { background: #28546a; border-color: #79ead8; }
QScrollArea { border: none; background: #0c1d31; }
QTextEdit { background: #10243a; color: #effaff; border: 1px solid #31536b;
    border-radius: 4px; selection-background-color: #257d80; }
QListWidget { background: #10243a; color: #effaff; border: 1px solid #31536b; }
QLabel#paragraphHint { color: #a8bfd2; font-size: 11px; }
"""


class ParagraphCheckBox(QCheckBox):
    """Paint the indicator explicitly so it survives Windows/Qt stylesheets."""
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, self).adjusted(0,0,-1,-1)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(1 if self.isEnabled() else .4)
        painter.setPen(QPen(ui_color('#427084'),1))
        painter.setBrush(ui_color('#257d80' if self.isChecked() else '#18394d'))
        painter.drawRoundedRect(rect,2,2)
        if self.isChecked():
            painter.setPen(QPen(QColor('#ffffff'),1.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            painter.drawLine(QPointF(rect.left()+3,rect.center().y()),QPointF(rect.left()+6,rect.bottom()-3))
            painter.drawLine(QPointF(rect.left()+6,rect.bottom()-3),QPointF(rect.right()-2,rect.top()+3))
        painter.end()


def spin(value=0, *, suffix='', minimum=0, maximum=400, step=1):
    field = AuroraMeasureSpinBox()
    field.setLocale(QLocale('pt_BR'))
    field.setRange(minimum, maximum)
    field.setDecimals(2)
    field.setSingleStep(step)
    field.setSuffix(suffix)
    field.setValue(value)
    field.setMinimumWidth(96)
    return field


def combo(items, current=None):
    field = QComboBox()
    for label, value in items:
        field.addItem(label, value)
    index = field.findData(current)
    if index >= 0:
        field.setCurrentIndex(index)
    return field


def check(label, value=False):
    field = ParagraphCheckBox(label)
    field.setChecked(bool(value))
    return field


def buttons(dialog):
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText('OK')
    box.button(QDialogButtonBox.Cancel).setText('Cancelar')
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def scroll_page():
    area = QScrollArea()
    area.setWidgetResizable(True)
    page = QWidget()
    page.setObjectName('paragraphPage')
    layout = QVBoxLayout(page)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)
    area.setWidget(page)
    return area, layout


class TabStopsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Tabulação')
        self.resize(500, 430)
        set_ui_style(self, DIALOG_STYLE)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.position = spin(suffix=' cm', maximum=100, step=.25)
        self.default = spin(settings.get('tab_default', 80) / PX_PER_CM,
                            suffix=' cm', minimum=.25, maximum=15, step=.25)
        self.alignment = combo([('Esquerda','left'),('Centralizada','center'),
                                ('Direita','right'),('Decimal','decimal')])
        self.leader = combo([('Nenhum',0),('Pontilhado',1),('Traços',2),('Linha',3)])
        form.addRow('Posição da tabulação:', self.position)
        form.addRow('Tabulações padrão:', self.default)
        form.addRow('Alinhamento:', self.alignment)
        form.addRow('Preenchimento:', self.leader)
        layout.addLayout(form)
        self.entries = QListWidget()
        self.entries.currentItemChanged.connect(self._select)
        layout.addWidget(self.entries, 1)
        row = QHBoxLayout()
        for label, callback in (('Definir', self._define), ('Limpar', self._remove), ('Limpar tudo', self._clear)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.hint = QLabel('')
        self.hint.setObjectName('paragraphHint')
        layout.addWidget(self.hint)
        layout.addWidget(buttons(self))
        for entry in settings.get('tabs', []):
            self._add(entry)

    def _add(self, entry):
        align = {'left':'Esquerda','right':'Direita','center':'Centralizada','decimal':'Decimal'}[entry['type']]
        leader = ('Sem preenchimento','Pontilhado','Traços','Linha')[entry.get('leader',0)]
        position = QLocale('pt_BR').toString(entry['position']/PX_PER_CM, 'f', 2)
        item = QListWidgetItem(f'{position} cm — {align} — {leader}')
        item.setData(Qt.UserRole, dict(entry))
        self.entries.addItem(item)

    def _select(self, current, _previous):
        if current is not None:
            entry = current.data(Qt.UserRole)
            self.position.setValue(entry['position']/PX_PER_CM)
            self.alignment.setCurrentIndex(self.alignment.findData(entry['type']))
            self.leader.setCurrentIndex(self.leader.findData(entry.get('leader',0)))

    def _define(self):
        if self.position.value() <= 0:
            return
        entry = {'position': self.position.value()*PX_PER_CM,
                 'type': self.alignment.currentData(), 'leader': self.leader.currentData()}
        for index in range(self.entries.count()-1, -1, -1):
            if abs(self.entries.item(index).data(Qt.UserRole)['position'] - entry['position']) < .5:
                self.entries.takeItem(index)
        if self.entries.count() >= 64:
            self.hint.setText('Use até 64 posições de tabulação por parágrafo.')
            return
        self._add(entry)
        self.hint.clear()

    def _remove(self):
        row = self.entries.currentRow()
        if row >= 0:
            self.entries.takeItem(row)
        self.position.setValue(0)

    def _clear(self):
        self.entries.clear()
        self.position.setValue(0)

    def value(self):
        return {'tab_default': self.default.value()*PX_PER_CM,
                'tabs': sorted((self.entries.item(i).data(Qt.UserRole) for i in range(self.entries.count())),
                               key=lambda item:item['position'])}

    def accept(self):
        self._define()
        super().accept()


class ParagraphDialog(QDialog):
    def __init__(self, settings, parent=None, save_default=None):
        super().__init__(parent)
        self.setWindowTitle('Parágrafo')
        self.setMinimumSize(560, 520)
        screen = QApplication.primaryScreen()
        self.resize(610, min(720, screen.availableGeometry().height()-64) if screen else 700)
        set_ui_style(self, DIALOG_STYLE)
        self._settings = dict(settings)
        self._options = dict(settings.get('options', {}))
        self._save_default = save_default
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        first, first_layout = scroll_page()
        second, second_layout = scroll_page()
        tabs.addTab(first, 'Recuos e espaçamento')
        tabs.addTab(second, 'Quebras de linha e de página')
        layout.addWidget(tabs, 1)

        general = QGroupBox('Geral')
        general_form = QFormLayout(general)
        self.alignment = combo([('Esquerda','left'),('Centralizado','center'),
                                ('Direita','right'),('Justificado','justify')], settings.get('alignment','left'))
        self.heading = combo([('Corpo de texto',0), *[(f'Nível {i}',i) for i in range(1,10)]], settings.get('heading',0))
        self.collapsed = check('Recolhido por padrão', self._options.get('collapsed'))
        general_form.addRow('Alinhamento:', self.alignment)
        general_form.addRow('Nível do tópico:', self.heading)
        general_form.addRow('', self.collapsed)
        first_layout.addWidget(general)

        indentation = QGroupBox('Recuo')
        grid = QGridLayout(indentation)
        self.left = spin(settings.get('left',0), suffix=' cm', minimum=-10, maximum=30, step=.25)
        self.right = spin(settings.get('right',0), suffix=' cm', minimum=-10, maximum=30, step=.25)
        first_line = settings.get('first',0)
        self.special = combo([('(nenhum)','none'),('Primeira linha','first'),('Deslocamento','hanging')],
                             'hanging' if first_line < 0 else 'first' if first_line > 0 else 'none')
        self.special_value = spin(abs(first_line) or 1.25, suffix=' cm', maximum=30, step=.25)
        self.mirror = check('Espelhar recuos', self._options.get('mirror'))
        for row, label, field in ((0,'Esquerda:',self.left),(1,'Direita:',self.right)):
            grid.addWidget(QLabel(label),row,0);grid.addWidget(field,row,1)
        grid.addWidget(QLabel('Especial:'),0,2);grid.addWidget(self.special,0,3)
        grid.addWidget(QLabel('Por:'),1,2);grid.addWidget(self.special_value,1,3)
        grid.addWidget(self.mirror,2,0,1,4)
        first_layout.addWidget(indentation)

        spacing = QGroupBox('Espaçamento')
        grid = QGridLayout(spacing)
        self.before = spin(settings.get('before',0), suffix=' pt')
        self.after = spin(settings.get('after',0), suffix=' pt')
        self.line_mode = combo([('Simples','single'),('1,5 linhas','onehalf'),('Duplo','double'),
                               ('Pelo menos','minimum'),('Exatamente','exact'),('Múltiplos','multiple')],
                              settings.get('line_mode','single'))
        self.line_value = spin(settings.get('line_value',1), minimum=.1, step=.05)
        self._line_points = self.line_mode.currentData() in ('minimum','exact')
        self.contextual = check('Não adicionar espaço entre parágrafos do mesmo estilo', self._options.get('contextual'))
        for row, label, field in ((0,'Antes:',self.before),(1,'Depois:',self.after)):
            grid.addWidget(QLabel(label),row,0);grid.addWidget(field,row,1)
        grid.addWidget(QLabel('Entre linhas:'),0,2);grid.addWidget(self.line_mode,0,3)
        grid.addWidget(QLabel('Em:'),1,2);grid.addWidget(self.line_value,1,3)
        grid.addWidget(self.contextual,2,0,1,4)
        first_layout.addWidget(spacing)
        first_layout.addStretch()

        pagination = QGroupBox('Paginação')
        p = QVBoxLayout(pagination)
        self.widows = check('Controle de linhas órfãs/viúvas',self._options.get('widow_control', True))
        self.keep_next = check('Manter com o próximo',self._options.get('keep_next'))
        self.keep_lines = check('Manter linhas juntas',self._options.get('keep_lines'))
        self.page_before = check('Quebrar página antes',settings.get('page_before'))
        for field in (self.widows,self.keep_next,self.keep_lines,self.page_before):p.addWidget(field)
        second_layout.addWidget(pagination)
        exceptions = QGroupBox('Exceções de formatação')
        e = QVBoxLayout(exceptions)
        self.no_numbers = check('Suprimir números de linha',self._options.get('no_line_numbers'))
        self.no_hyphen = check('Não hifenizar',self._options.get('no_hyphen'))
        e.addWidget(self.no_numbers);e.addWidget(self.no_hyphen)
        second_layout.addWidget(exceptions)
        textbox = QGroupBox('Opções de caixa de texto')
        f = QFormLayout(textbox)
        self.text_wrap = combo([('Nenhuma','none'),('Todas as linhas','all'),
                                ('Primeira e última','firstlast'),('Apenas a primeira','first'),
                                ('Apenas a última','last')],self._options.get('text_wrap','none'))
        f.addRow('Disposição justa:',self.text_wrap)
        second_layout.addWidget(textbox)
        notice = QLabel('Paginação, recolhimento e caixa de texto são preservados para editores compatíveis, como o Word.')
        notice.setWordWrap(True);notice.setObjectName('paragraphHint')
        second_layout.addWidget(notice)
        second_layout.addStretch()

        preview_group = QGroupBox('Visualização')
        pv = QVBoxLayout(preview_group)
        self.preview = AuroraImageEditor()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(100)
        pv.addWidget(self.preview)
        layout.addWidget(preview_group)
        self.saved_hint = QLabel('')
        self.saved_hint.setObjectName('paragraphHint')
        layout.addWidget(self.saved_hint)
        footer = QHBoxLayout()
        tab_button = QPushButton('Tabulação…');tab_button.clicked.connect(self._tabs)
        default_button = QPushButton('Definir como padrão');default_button.clicked.connect(self._default)
        default_button.setEnabled(save_default is not None)
        footer.addWidget(tab_button);footer.addWidget(default_button);footer.addStretch();footer.addWidget(buttons(self))
        layout.addLayout(footer)
        for field in (self.alignment,self.heading,self.special,self.line_mode,self.text_wrap):
            field.currentIndexChanged.connect(self._update_preview)
        for field in (self.left,self.right,self.special_value,self.before,self.after,self.line_value):
            field.valueChanged.connect(self._update_preview)
        for field in (self.collapsed,self.mirror,self.contextual,self.widows,self.keep_next,
                      self.keep_lines,self.page_before,self.no_numbers,self.no_hyphen):
            field.toggled.connect(self._update_preview)
        self._update_preview()

    def value(self):
        mode = self.special.currentData()
        first = (self.special_value.value() * (-1 if mode == 'hanging' else 1)) if mode != 'none' else 0
        opts = {**self._options, 'collapsed':self.collapsed.isChecked() and self.heading.currentData()>0, 'mirror':self.mirror.isChecked(),
                'contextual':self.contextual.isChecked(), 'widow_control':self.widows.isChecked(),
                'keep_next':self.keep_next.isChecked(), 'keep_lines':self.keep_lines.isChecked(),
                'no_line_numbers':self.no_numbers.isChecked(), 'no_hyphen':self.no_hyphen.isChecked(),
                'text_wrap':self.text_wrap.currentData()}
        return {'alignment':self.alignment.currentData(), 'heading':self.heading.currentData(),
                'left':self.left.value(), 'right':self.right.value(), 'first':first,
                'before':self.before.value(), 'after':self.after.value(),
                'line_mode':self.line_mode.currentData(), 'line_value':self.line_value.value(),
                'page_before':self.page_before.isChecked(), 'options':opts}

    def _update_preview(self, *_):
        self.special_value.setEnabled(self.special.currentData() != 'none')
        self.collapsed.setEnabled(self.heading.currentData() != 0)
        points = self.line_mode.currentData() in ('minimum','exact')
        self.line_value.blockSignals(True)
        if points != self._line_points:
            self.line_value.setValue(12 if points else 1)
            self._line_points = points
        fixed = {'single':1,'onehalf':1.5,'double':2}.get(self.line_mode.currentData())
        if fixed is not None:
            self.line_value.setValue(fixed)
        self.line_value.blockSignals(False)
        self.line_value.setSuffix(' pt' if points else '')
        self.line_value.setEnabled(self.line_mode.currentData() in ('minimum','exact','multiple'))
        self.preview.setPlainText('Parágrafo anterior\nTexto de exemplo para visualizar recuos e espaçamento. Texto de exemplo.\nParágrafo seguinte')
        document = self.preview.document()
        block = document.findBlockByNumber(1)
        cursor = QTextCursor(block)
        fmt = apply_settings(block.blockFormat(),self.value())
        # The preview remains a continuous text view, without forced page gaps.
        fmt.setPageBreakPolicy(QTextFormat.PageBreak_Auto)
        cursor.setBlockFormat(fmt)
        normalize_contextual_spacing(document)
        self.preview.viewport().update()

    def _tabs(self):
        dialog = TabStopsDialog(self._options,self)
        if dialog.exec() == QDialog.Accepted:
            self._options.update(dialog.value())
            self._update_preview()

    def _default(self):
        if self._save_default is not None:
            saved = self._save_default(self.value())
            self.saved_hint.setText('Padrão salvo para os novos comandos.' if saved is not False else 'Não foi possível salvar o padrão.')


class ParagraphSortDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Classificar parágrafos')
        set_ui_style(self,DIALOG_STYLE)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = combo([('Texto','text'),('Número','number')])
        self.order = combo([('Crescente (A → Z)','ascending'),('Decrescente (Z → A)','descending')])
        self.header = check('A primeira linha é um cabeçalho')
        form.addRow('Tipo:',self.kind);form.addRow('Ordem:',self.order)
        layout.addLayout(form);layout.addWidget(self.header);layout.addWidget(buttons(self))

    def value(self):
        return {'numeric':self.kind.currentData()=='number','descending':self.order.currentData()=='descending',
                'header':self.header.isChecked()}
