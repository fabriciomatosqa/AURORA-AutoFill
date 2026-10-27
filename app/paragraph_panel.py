"""Word-style paragraph ribbon with native editing commands."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QTextListFormat, QTextOption
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QToolButton, QVBoxLayout, QWidget)

from .color_dialog import AuroraColorDialog
from .icons import apply_icon
from .paragraph_dialog import ParagraphDialog, ParagraphSortDialog
from .paragraph_editor import ParagraphEditor
from .paragraph_format import options, settings_from_format
from .themes import ui_color


class ParagraphMenuButton(QToolButton):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ui_color('#81e9d9'), 1.25))
        x, y = self.width()-6, self.height()//2
        painter.drawLine(x-2,y-1,x,y+1)
        painter.drawLine(x,y+1,x+2,y-1)
        painter.end()


class ParagraphPanel(QWidget):
    def __init__(self, editor, parent=None, *, menu_factory=QMenu, save_default=None):
        super().__init__(parent)
        self.editor = editor
        self.controller = ParagraphEditor(editor)
        self._menu_factory = menu_factory
        self._save_default = save_default
        self._shade_color = '#fff59d'
        self._border_color = '#4f6b86'
        self._border_width = 1
        self.buttons = {}
        self.setFixedSize(238, 91)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(4)
        row1, row2, row3 = (QHBoxLayout() for _ in range(3))
        for row in (row1,row2,row3):
            row.setSpacing(4)
            layout.addLayout(row)
        bullet = self._button('list-bullets','Marcadores',46,
                              lambda _:self.controller.list(QTextListFormat.ListDisc,'bullet',toggle=True), menu=True)
        number = self._button('list-numbered','Numeração',46,
                              lambda _:self.controller.list(QTextListFormat.ListDecimal,'number',toggle=True), menu=True)
        multilevel = self._button('list-multilevel','Lista de vários níveis',46,
                                  lambda _:self.controller.list(QTextListFormat.ListDecimal,'multilevel',toggle=True), menu=True)
        for button in (bullet,number,multilevel):button.setCheckable(True)
        self.buttons.update(bullet=bullet,number=number,multilevel=multilevel)
        self._list_menu(bullet,[('• Marcador redondo',QTextListFormat.ListDisc),
                                ('○ Marcador vazado',QTextListFormat.ListCircle),
                                ('▪ Marcador quadrado',QTextListFormat.ListSquare)],'bullet')
        self._list_menu(number,[('1. 2. 3.',QTextListFormat.ListDecimal),('a. b. c.',QTextListFormat.ListLowerAlpha),
                                ('A. B. C.',QTextListFormat.ListUpperAlpha),('i. ii. iii.',QTextListFormat.ListLowerRoman),
                                ('I. II. III.',QTextListFormat.ListUpperRoman)],'number')
        number.menu().addSeparator()
        self._action(number.menu(),'Definir início da numeração…',self._number_start)
        self._list_menu(multilevel,[('1. → a. → i.',QTextListFormat.ListDecimal)],'multilevel')
        for button in (bullet,number,multilevel,
                       self._button('indent-less','Diminuir recuo',42,lambda _:self.controller.indent(-1)),
                       self._button('indent-more','Aumentar recuo',42,lambda _:self.controller.indent(1))):
            button.setFixedHeight(29)
            row1.addWidget(button,1)
        for label, name in (('Alinhar à esquerda','left'),('Centralizar','center'),
                            ('Alinhar à direita','right'),('Justificar','justify')):
            button = self._button('align-'+name,label,34,lambda _, n=name:self.controller.align(n))
            button.setCheckable(True)
            self.buttons[name] = button
            row2.addWidget(button,1)
        line = self._button('line-spacing','Espaçamento entre linhas e parágrafos',45,
                            lambda _:self.open_dialog(), menu=True)
        menu = self._menu_factory(line)
        for label, value in (('1,0',1),('1,15',1.15),('1,5',1.5),('2,0',2),('2,5',2.5),('3,0',3)):
            self._action(menu,label,lambda v=value:self.controller.apply({'line_mode':'multiple','line_value':v}))
        menu.addSeparator()
        for label, value in (('Adicionar espaço antes',{'before':12}),('Remover espaço antes',{'before':0}),
                             ('Adicionar espaço depois',{'after':8}),('Remover espaço depois',{'after':0})):
            self._action(menu,label,lambda v=value:self.controller.apply(v))
        self._action(menu,'Opções de espaçamento…',self.open_dialog)
        line.setMenu(menu)
        row2.addWidget(line,1)
        marks = self._button(None,'Mostrar ou ocultar marcas de parágrafo',37,
                             self.controller.show_marks,text='¶')
        marks.setCheckable(True)
        self.buttons['marks'] = marks
        row2.addWidget(marks,1)
        shade = self._button('paragraph-shading','Sombreamento do parágrafo',46,
                             lambda _:self.controller.shade(self._shade_color), menu=True)
        menu = self._menu_factory(shade)
        self._action(menu,'Escolher cor…',self._choose_shading)
        self._action(menu,'Sem cor',lambda:self.controller.shade(None))
        shade.setMenu(menu)
        row3.addWidget(shade,1)
        border = self._button('paragraph-border','Bordas do parágrafo',46,
                              lambda _:self._border('outside'), menu=True)
        menu = self._menu_factory(border)
        for label, mode in (('Sem borda','none'),('Todas as bordas','all'),('Borda externa','outside'),
                            ('Borda inferior','bottom'),('Borda superior','top'),('Borda esquerda','left'),('Borda direita','right')):
            self._action(menu,label,lambda m=mode:self._border(m))
        menu.addSeparator()
        self._action(menu,'Cor da borda…',self._choose_border)
        self._action(menu,'Espessura da borda…',self._border_size)
        border.setMenu(menu)
        row3.addWidget(border,1)
        row3.addWidget(self._button('sort-text','Classificar parágrafos',32,lambda _:self._sort()),1)
        caption = QLabel('Parágrafo')
        caption.setObjectName('paragraphTitle')
        caption.setFixedWidth(75)
        caption.setAlignment(Qt.AlignCenter)
        row3.addWidget(caption)
        row3.addWidget(self._button('paragraph-settings','Opções de parágrafo',23,lambda _:self.open_dialog()),1)
        self.controller.updated.connect(self.sync)
        self.sync()

    def _button(self, icon, label, width, callback, *, menu=False, text=None):
        button = ParagraphMenuButton() if menu else QToolButton()
        button.setObjectName('fontTool')
        button.setFocusPolicy(Qt.NoFocus)
        button.setFixedSize(width,27)
        button.setToolTip(label)
        button.setAccessibleName(label)
        if icon:apply_icon(button,icon,label=label)
        if text:button.setText(text)
        if menu:
            button.setProperty('paragraphMenu',True)
            button.setPopupMode(QToolButton.MenuButtonPopup)
        button.clicked.connect(callback)
        return button

    def _action(self, menu, label, callback):
        action = menu.addAction(label)
        action.triggered.connect(lambda _=False:callback())
        return action

    def _list_menu(self, button, choices, mode):
        menu = self._menu_factory(button)
        for label, style in choices:
            self._action(menu,label,lambda s=style:self.controller.list(s,mode))
        menu.addSeparator()
        self._action(menu,'Remover lista',lambda:self.controller.list(None))
        button.setMenu(menu)

    def sync(self):
        state = settings_from_format(self.editor.textCursor().blockFormat())
        for name in ('left','center','right','justify'):
            button = self.buttons[name]
            button.blockSignals(True);button.setChecked(name==state['alignment']);button.blockSignals(False)
        listing = self.editor.textCursor().currentList()
        mode = state['options'].get('list_mode')
        if listing is not None and mode is None:
            mode = 'bullet' if listing.format().style() in (QTextListFormat.ListDisc,QTextListFormat.ListCircle,
                                                           QTextListFormat.ListSquare) else 'number'
        for name in ('bullet','number','multilevel'):
            button = self.buttons[name]
            button.blockSignals(True);button.setChecked(listing is not None and mode==name);button.blockSignals(False)
        marks = self.buttons['marks']
        marks.blockSignals(True)
        marks.setChecked(bool(self.editor.document().defaultTextOption().flags() & QTextOption.ShowLineAndParagraphSeparators))
        marks.blockSignals(False)

    def open_dialog(self):
        dialog = ParagraphDialog(settings_from_format(self.editor.textCursor().blockFormat()),
                                 self.window(),save_default=self._save_default)
        if dialog.exec() == QDialog.Accepted:
            self.controller.apply(dialog.value())

    def _sort(self):
        dialog = ParagraphSortDialog(self.window())
        if dialog.exec() == QDialog.Accepted:
            try:self.controller.sort(**dialog.value())
            except ValueError as exc:QMessageBox.information(self.window(),'Classificar parágrafos',str(exc))

    def _choose_shading(self):
        color = AuroraColorDialog.get_color(self._shade_color,self.window(),'Sombreamento do parágrafo')
        if color.isValid():
            self._shade_color = color.name()
            self.controller.shade(color)

    def _border(self, mode):
        self.controller.border(mode,self._border_color,self._border_width)

    def _choose_border(self):
        color = AuroraColorDialog.get_color(self._border_color,self.window(),'Cor da borda')
        if color.isValid():
            self._border_color = color.name()
            self._border('outside')

    def _border_size(self):
        value, ok = QInputDialog.getDouble(self.window(),'Bordas','Espessura em pixels:',self._border_width,.5,6,1)
        if ok:
            self._border_width = value
            self._border('outside')

    def _number_start(self):
        listing = self.editor.textCursor().currentList()
        if listing is not None:
            value, ok = QInputDialog.getInt(self.window(),'Numeração','Iniciar em:',listing.format().start(),1,9999)
            if ok:
                fmt = listing.format();fmt.setStart(value);listing.setFormat(fmt)
