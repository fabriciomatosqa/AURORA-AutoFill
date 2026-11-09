"""Galeria visual de estilos de tabela, construída com controles Qt nativos.

As tabelas permanecem QTextTable editáveis no HTML/SQLite. Miniaturas são
pintadas localmente, sem imagens externas ou dependências adicionais.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)


@dataclass(frozen=True)
class TableStyle:
    key: str
    name: str
    group: str
    accent: str
    variant: str


TABLE_STYLES = (
    TableStyle("simple", "Tabela simples", "Tabelas Simples", "#53677a", "simple"),
    TableStyle("plain", "Sem bordas", "Tabelas Simples", "#53677a", "plain"),
    TableStyle("thin", "Grade fina", "Tabelas Simples", "#8da4b5", "thin"),
    TableStyle("horizontal", "Linhas horizontais", "Tabelas Simples", "#617789", "horizontal"),
    TableStyle("outer", "Borda externa", "Tabelas Simples", "#445e75", "outer"),
    TableStyle("neutral", "Cinza discreto", "Tabelas Simples", "#84939f", "grid"),
    TableStyle("classic", "Cabeçalho clássico", "Tabelas Simples", "#303f50", "grid"),
    TableStyle("grid-blue", "Azul", "Tabelas de Grade", "#1976b9", "grid"),
    TableStyle("grid-orange", "Laranja", "Tabelas de Grade", "#e37435", "grid"),
    TableStyle("grid-green", "Verde", "Tabelas de Grade", "#298a55", "grid"),
    TableStyle("grid-cyan", "Turquesa", "Tabelas de Grade", "#009db1", "grid"),
    TableStyle("grid-purple", "Roxo", "Tabelas de Grade", "#974cba", "grid"),
    TableStyle("grid-red", "Vermelho", "Tabelas de Grade", "#bf515b", "grid"),
    TableStyle("grid-lime", "Verde claro", "Tabelas de Grade", "#63a74d", "grid"),
    TableStyle("list-blue", "Azul", "Tabelas de Lista", "#1976b9", "list"),
    TableStyle("list-orange", "Laranja", "Tabelas de Lista", "#e37435", "list"),
    TableStyle("list-green", "Verde", "Tabelas de Lista", "#298a55", "list"),
    TableStyle("list-cyan", "Turquesa", "Tabelas de Lista", "#009db1", "list"),
    TableStyle("list-purple", "Roxo", "Tabelas de Lista", "#974cba", "list"),
    TableStyle("list-red", "Vermelho", "Tabelas de Lista", "#bf515b", "list"),
    TableStyle("list-lime", "Verde claro", "Tabelas de Lista", "#63a74d", "list"),
)
DEFAULT_STYLE = next(style for style in TABLE_STYLES if style.key == "plain")


def _tint(color: str, strength: int = 225) -> QColor:
    base = QColor(color)
    return QColor(
        (base.red() * (255 - strength) + 255 * strength) // 255,
        (base.green() * (255 - strength) + 255 * strength) // 255,
        (base.blue() * (255 - strength) + 255 * strength) // 255,
    )


def cell_colors(style: TableStyle, row: int, col: int, *,
                header: bool = True, banded: bool = True,
                first_column: bool = False) -> tuple[QColor, QColor]:
    """Retorna fundo e borda; prévia e tabela real usam a mesma paleta."""
    background = QColor("#ffffff")
    accent = QColor(style.accent)
    line = QColor(style.accent)
    if style.variant in ("plain", "horizontal"):
        line = QColor("#b9c9d4")
    if style.variant in ("simple", "outer"):
        line = QColor("#6a7a89")
    if style.variant in ("grid", "list"):
        if header and row == 0:
            background = accent
        elif first_column and col == 0:
            background = _tint(style.accent, 195)
        elif banded and row % 2:
            background = _tint(style.accent, 218)
    elif style.variant == "thin" and banded and row % 2:
        background = QColor("#f2f5f8")
    elif style.variant == "simple" and header and row == 0:
        background = QColor("#e4ebef")
    return background, line


def apply_table_style(table, style: TableStyle, *, header: bool = True,
                      banded: bool = True, first_column: bool = False):
    """Estiliza células sem trocar a QTextTable nem apagar textos existentes."""
    fmt = table.format()
    fmt.setCellPadding(5)
    fmt.setCellSpacing(0)
    fmt.setWidth(fmt.width())
    fmt.setBorder(0 if style.variant in ("plain", "list", "horizontal") else 1)
    fmt.setBorderBrush(QBrush(QColor(style.accent)))
    table.setFormat(fmt)
    for row in range(table.rows()):
        for col in range(table.columns()):
            cell = table.cellAt(row, col)
            background, _ = cell_colors(
                style, row, col, header=header, banded=banded,
                first_column=first_column)
            cell_format = cell.format()
            cell_format.setBackground(QBrush(background))
            cell.setFormat(cell_format)
    from .insert_objects import stabilize_table_columns
    stabilize_table_columns(table)
    return table


class TableStylePreview(QToolButton):
    """Miniatura desenhada, sem arquivos de imagem e sem texto ilegível."""
    def __init__(self, style: TableStyle, parent=None):
        super().__init__(parent)
        self.style_spec = style
        self.setFixedSize(59, 51)
        self.setToolTip(f"{style.group} — {style.name}")
        self.setAccessibleName(f"Estilo de tabela: {style.name} ({style.group})")
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#7a9bab") if self.underMouse()
                            else QColor("#cad6df"), 1))
        painter.setBrush(QColor("#ecf8fa") if self.underMouse() else QColor("#ffffff"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        left, top, w, h = 5, 6, 49, 39
        rows, cols = 5, 6
        for row in range(rows):
            for col in range(cols):
                x, y = left + col * w / cols, top + row * h / rows
                bg, border = cell_colors(self.style_spec, row, col)
                rect = QRectF(x, y, w / cols, h / rows)
                painter.fillRect(rect.adjusted(0.65, 0.65, -0.65, -0.65), bg)
                variant = self.style_spec.variant
                if variant in ("grid", "thin", "simple"):
                    painter.setPen(QPen(border, 0.55))
                    painter.drawRect(rect)
                elif variant in ("list", "horizontal"):
                    painter.setPen(QPen(border, 0.65))
                    painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if self.style_spec.variant == "outer":
            painter.setPen(QPen(QColor(self.style_spec.accent), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(left, top, w, h))
        painter.end()


def build_table_styles_menu(button, on_style, on_clear, *,
                            custom_styles=(), on_new=None, on_modify=None,
                            menu_factory=QMenu):
    """Galeria agrupada com miniaturas e estilos realmente aplicáveis."""
    menu = menu_factory(button)
    menu.setObjectName("auroraTableStylesMenu")
    host = QWidget(menu)
    root = QVBoxLayout(host)
    root.setContentsMargins(9, 7, 9, 7)
    root.setSpacing(7)

    intro = QLabel("Escolha um estilo para aplicar à tabela atual.\n"
                   "Sem tabela selecionada, uma nova será criada.")
    intro.setWordWrap(True)
    intro.setStyleSheet("font-size: 11px; color: #96c6d4;")
    root.addWidget(intro)

    groups = ["Tabelas Simples", "Tabelas de Grade", "Tabelas de Lista"]
    if custom_styles:
        groups.append("Meus Estilos")
    styles = TABLE_STYLES + tuple(custom_styles)
    for group in groups:
        label = QLabel(group)
        label.setStyleSheet("font-size: 12px; font-weight: 700; color: #d3edf5;")
        root.addWidget(label)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)
        for idx, style in enumerate(item for item in styles
                                    if item.group == group):
            preview = TableStylePreview(style, host)
            preview.clicked.connect(lambda _=False, s=style: (
                menu.close(), on_style(s)))
            grid.addWidget(preview, idx // 7, idx % 7)
        root.addLayout(grid)

    action = QWidgetAction(menu)
    action.setDefaultWidget(host)
    menu.addAction(action)
    menu.addSeparator()
    if on_modify is not None:
        modify_action = menu.addAction("Modificar Estilo de Tabela…")
        modify_action.triggered.connect(lambda _=False: on_modify())
    clear_action = menu.addAction("Limpar formatação da tabela")
    clear_action.triggered.connect(lambda _=False: on_clear())
    if on_new is not None:
        new_action = menu.addAction("Novo Estilo de Tabela…")
        new_action.triggered.connect(lambda _=False: on_new())
    return menu
