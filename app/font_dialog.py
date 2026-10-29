"""Full font controls for the ribbon's Fonte launcher."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QFont, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout)

from .color_dialog import AuroraColorDialog
from .font_catalog import AuroraFontCombo, AuroraFontSizeSpinBox
from .inline_images import AuroraImageEditor
from .paragraph_dialog import DIALOG_STYLE, ParagraphCheckBox, buttons, combo
from .themes import set_ui_style


class FontDialog(QDialog):
    def __init__(self, formatting, font, parent=None, *, sample='AaBbCc ÁÉÍÓÚ 123'):
        super().__init__(parent)
        self.setWindowTitle('Fonte')
        self.setMinimumWidth(560)
        self.resize(610,440)
        set_ui_style(self,DIALOG_STYLE+'''
            QSpinBox { background:#18394d; color:#effaff; border:1px solid #427084;
                border-radius:4px; padding:3px 6px; min-height:22px; }
            QToolButton { background:#19364b; color:#effaff; border:1px solid #365a71;
                border-radius:4px; padding:5px 8px; min-height:22px; }
            QToolButton:hover { border-color:#79ead8; background:#28546a; }
            QToolButton::menu-indicator { image:none; width:0px; height:0px; }
            QComboBox#fontFamily::down-arrow { image:none; }
        ''')
        self._original = QTextCharFormat(formatting)
        self._foreground = formatting.foreground() if formatting.hasProperty(QTextFormat.ForegroundBrush) else QBrush(Qt.NoBrush)
        self._background = formatting.background() if formatting.hasProperty(QTextFormat.BackgroundBrush) else QBrush(Qt.NoBrush)
        self.reset_foreground = False
        self.reset_background = False
        self._sample = sample.replace('\u2029',' ').strip()[:240] or 'AaBbCc ÁÉÍÓÚ 123'
        layout = QVBoxLayout(self)
        group = QGroupBox('Fonte')
        fields = QGridLayout(group)
        self.font_family = AuroraFontCombo()
        self.font_family.setCurrentText(font.family())
        self.font_family.setMinimumWidth(245)
        self.font_style = combo([('Regular','regular'),('Itálico','italic'),('Negrito','bold'),
                            ('Negrito e itálico','bolditalic')],
                           'bolditalic' if font.bold() and font.italic() else 'bold' if font.bold()
                           else 'italic' if font.italic() else 'regular')
        self.font_size = AuroraFontSizeSpinBox()
        self.font_size.setRange(6,96)
        self.font_size.setSuffix(' pt')
        self.font_size.setValue(round(font.pointSizeF()) if font.pointSizeF()>0 else 11)
        for column, (label, field) in enumerate((('Fonte:',self.font_family),('Estilo:',self.font_style),('Tamanho:',self.font_size))):
            fields.addWidget(QLabel(label),0,column)
            fields.addWidget(field,1,column)
        fields.setColumnStretch(0,3)
        fields.setColumnStretch(1,2)
        fields.setColumnStretch(2,1)
        layout.addWidget(group)
        colors = QHBoxLayout()
        self.text_color = self._color_button('Cor da fonte',False)
        self.highlight = self._color_button('Realce',True)
        colors.addWidget(self.text_color,1);colors.addWidget(self.highlight,1)
        layout.addLayout(colors)
        effects = QGroupBox('Efeitos')
        grid = QGridLayout(effects)
        self.underline = ParagraphCheckBox('Sublinhado')
        self.underline.setChecked(formatting.fontUnderline())
        self.strike = ParagraphCheckBox('Tachado')
        self.strike.setChecked(formatting.fontStrikeOut())
        self.position = combo([('Normal','normal'),('Sobrescrito','super'),('Subscrito','sub')],
            'super' if formatting.verticalAlignment()==QTextCharFormat.AlignSuperScript else
            'sub' if formatting.verticalAlignment()==QTextCharFormat.AlignSubScript else 'normal')
        grid.addWidget(self.underline,0,0);grid.addWidget(self.strike,0,1)
        grid.addWidget(QLabel('Posição:'),1,0);grid.addWidget(self.position,1,1)
        layout.addWidget(effects)
        preview = QGroupBox('Visualização')
        preview_layout = QVBoxLayout(preview)
        self.preview = AuroraImageEditor()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(85)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview,1)
        layout.addWidget(buttons(self))
        self.font_family.currentTextChanged.connect(self._update_preview)
        self.font_style.currentIndexChanged.connect(self._update_preview)
        self.font_size.valueChanged.connect(self._update_preview)
        self.position.currentIndexChanged.connect(self._update_preview)
        self.underline.toggled.connect(self._update_preview)
        self.strike.toggled.connect(self._update_preview)
        self._update_preview()

    def _color_button(self,title,highlight):
        button = QToolButton()
        button.setPopupMode(QToolButton.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(button)
        menu.addAction('Escolher cor…',lambda:self._choose_color(highlight))
        menu.addAction('Sem realce' if highlight else 'Automática',lambda:self._set_color(highlight,QBrush(Qt.NoBrush)))
        button.setMenu(menu)
        button.setProperty('colorTitle',title)
        self._refresh_color_label(button,highlight)
        return button

    def _refresh_color_label(self,button,highlight):
        brush = self._background if highlight else self._foreground
        color = brush.color().name() if brush.style()!=Qt.NoBrush and brush.color().alpha() else 'Nenhum' if highlight else 'Automática'
        button.setText(button.property('colorTitle')+': '+color+'  ▾')

    def _choose_color(self,highlight):
        brush = self._background if highlight else self._foreground
        accepted, color = AuroraColorDialog.get_choice(
            brush.color(), self, 'Realce' if highlight else 'Cor da fonte')
        if accepted:
            self._set_color(
                highlight, QBrush(color) if color.isValid() else QBrush(Qt.NoBrush))

    def _set_color(self,highlight,brush):
        if highlight:
            self._background = brush
            self.reset_background = brush.style() == Qt.NoBrush
        else:
            self._foreground = brush
            self.reset_foreground = brush.style() == Qt.NoBrush
        self._refresh_color_label(self.highlight if highlight else self.text_color,highlight)
        self._update_preview()

    def value(self):
        result = QTextCharFormat(self._original)
        family = self.font_family.currentText().strip()
        if family:result.setFontFamilies([family])
        result.setFontPointSize(self.font_size.value())
        style = self.font_style.currentData()
        result.setFontWeight(QFont.Bold if style in ('bold','bolditalic') else QFont.Normal)
        result.setFontItalic(style in ('italic','bolditalic'))
        result.setFontUnderline(self.underline.isChecked())
        result.setFontStrikeOut(self.strike.isChecked())
        result.setVerticalAlignment({'normal':QTextCharFormat.AlignNormal,'super':QTextCharFormat.AlignSuperScript,
                                     'sub':QTextCharFormat.AlignSubScript}[self.position.currentData()])
        result.setForeground(self._foreground)
        result.setBackground(self._background)
        return result

    def _update_preview(self,*_):
        self.preview.setPlainText(self._sample)
        self.preview.setAlignment(Qt.AlignCenter)
        cursor = QTextCursor(self.preview.document())
        cursor.select(QTextCursor.Document)
        cursor.mergeCharFormat(self.value())
