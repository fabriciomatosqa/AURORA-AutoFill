"""Inserção de tabelas editáveis, formas e gráficos no editor de comandos.

Tabelas usam QTextTable nativo. Formas e gráficos geram QImage em memória
e passam pelo mesmo limitador de imagens, SQLite e backup já existentes.
Não baixa arquivos, executa scripts, nem altera outros atalhos do usuário.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath,
                           QPen, QPolygonF, QTextCursor, QTextTableFormat)
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox, QPlainTextEdit, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

from .ribbon import RibbonFooter


def insert_table(editor, rows: int, columns: int):
    """Insere tabela nativa, nunca HTML em imagem; mantém células editáveis."""
    if not 1 <= rows <= 12 or not 1 <= columns <= 8 or rows * columns > 80:
        raise ValueError("Use no máximo 12 linhas, 8 colunas e 80 células.")
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    try:
        table_format = QTextTableFormat()
        table_format.setBorder(1)
        table_format.setCellPadding(5)
        table_format.setCellSpacing(0)
        table_format.setWidth(90)
        table = cursor.insertTable(rows, columns, table_format)
    finally:
        cursor.endEditBlock()
    editor.setFocus()
    return table


SHAPES = (
    ("Retângulo", "rectangle"), ("Retângulo arredondado", "rounded"),
    ("Elipse", "ellipse"), ("Triângulo", "triangle"),
    ("Losango", "diamond"), ("Linha", "line"),
    ("Seta para a direita", "arrow"), ("Estrela", "star"),
)


def render_shape(shape: str) -> QImage:
    if shape not in {value for _, value in SHAPES}:
        raise ValueError("Forma não disponível.")
    image = QImage(420, 240, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#2a9d9b"), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor("#8de8e1"))
    rect = QRectF(32, 28, 356, 180)
    if shape == "rectangle":
        painter.drawRect(rect)
    elif shape == "rounded":
        painter.drawRoundedRect(rect, 26, 26)
    elif shape == "ellipse":
        painter.drawEllipse(rect)
    elif shape == "triangle":
        painter.drawPolygon(QPolygonF([QPointF(210, 20), QPointF(380, 205), QPointF(40, 205)]))
    elif shape == "diamond":
        painter.drawPolygon(QPolygonF([QPointF(210, 20), QPointF(385, 120),
                                       QPointF(210, 220), QPointF(35, 120)]))
    elif shape == "line":
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(35, 195), QPointF(385, 45))
    elif shape == "arrow":
        painter.drawPolygon(QPolygonF([
            QPointF(32, 85), QPointF(248, 85), QPointF(248, 35),
            QPointF(385, 120), QPointF(248, 205), QPointF(248, 155), QPointF(32, 155)]))
    elif shape == "star":
        points = []
        for i in range(10):
            theta = -math.pi / 2 + i * math.pi / 5
            radius = 98 if i % 2 == 0 else 44
            points.append(QPointF(210 + math.cos(theta) * radius,
                                  120 + math.sin(theta) * radius))
        painter.drawPolygon(QPolygonF(points))
    painter.end()
    return image


CHART_TYPES = ("Colunas", "Linhas", "Pizza")


def parse_chart_data(raw: str) -> list[tuple[str, float]]:
    """2 a 12 pares Rótulo;valor. Sem eval, NaN, infinito ou dados externos."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not 2 <= len(lines) <= 12:
        raise ValueError("Informe entre 2 e 12 linhas de dados.")
    result = []
    for line in lines:
        fields = line.split(";")
        if len(fields) != 2:
            raise ValueError("Cada linha deve ter o formato Rótulo;valor.")
        label = fields[0].strip()
        if not label or len(label) > 24:
            raise ValueError("O nome de cada item deve ter de 1 a 24 caracteres.")
        try:
            amount = float(fields[1].strip().replace(",", "."))
        except ValueError as exc:
            raise ValueError("Digite valores numéricos, como 12 ou 12,5.") from exc
        if not math.isfinite(amount) or amount < 0 or amount > 1_000_000:
            raise ValueError("Os valores devem estar entre 0 e 1.000.000.")
        result.append((label, amount))
    if not any(amount > 0 for _, amount in result):
        raise ValueError("Pelo menos um valor precisa ser maior que zero.")
    return result


_COLORS = ("#42c7be", "#6176d5", "#f5ad64", "#df79bd", "#8ac86e",
           "#e1d464", "#7daee6", "#d98b6a", "#5dc69a", "#a18ad1",
           "#d06b8b", "#84aeb2")


def render_chart(kind: str, values: list[tuple[str, float]], title: str) -> QImage:
    if kind not in CHART_TYPES:
        raise ValueError("Tipo de gráfico inválido.")
    if not 2 <= len(values) <= 12 or not title.strip() or len(title) > 70:
        raise ValueError("Confira o título e os dados do gráfico.")
    image = QImage(760, 450, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor("#18344c"))
    painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
    painter.drawText(QRectF(24, 13, 710, 42), Qt.AlignCenter, title.strip())
    amounts = [value for _, value in values]
    high = max(amounts)
    count = len(values)
    if kind == "Pizza":
        total = sum(amounts)
        start = 0
        for i, (label, value) in enumerate(values):
            span = round(5760 * value / total)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor(_COLORS[i]))
            painter.drawPie(QRectF(56, 89, 310, 310), start, span)
            start += span
            painter.setPen(QColor("#18344c"))
            painter.setBrush(QColor(_COLORS[i]))
            painter.fillRect(QRectF(408, 87 + i * 27, 14, 14), QColor(_COLORS[i]))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(432, 82 + i * 27, 300, 23), Qt.AlignVCenter,
                             f"{label}: {value:g} ({value / total:.0%})")
    else:
        plot = QRectF(72, 85, 632, 278)
        painter.setPen(QPen(QColor("#d5e1e6"), 1))
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#344d61"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRectF(2, y - 10, 64, 22),
                             Qt.AlignRight | Qt.AlignVCenter, f"{high * i / 4:g}")
            painter.setPen(QPen(QColor("#d5e1e6"), 1))
        step = plot.width() / count
        points = []
        for i, (label, value) in enumerate(values):
            cx = plot.left() + (i + 0.5) * step
            top = plot.bottom() - (value / high) * plot.height()
            if kind == "Colunas":
                painter.fillRect(QRectF(cx - step * 0.29, top, step * 0.58,
                                        plot.bottom() - top), QColor(_COLORS[i]))
            else:
                points.append(QPointF(cx, top))
            painter.setPen(QColor("#18344c"))
            painter.setFont(QFont("Segoe UI", 9))
            truncated = label[:11] + ("…" if len(label) > 11 else "")
            painter.drawText(QRectF(cx - step * 0.49, 373, step * 0.98, 24),
                             Qt.AlignHCenter | Qt.AlignVCenter, truncated)
        if kind == "Linhas":
            painter.setPen(QPen(QColor("#219a9d"), 4))
            for i in range(1, len(points)):
                painter.drawLine(points[i - 1], points[i])
            painter.setBrush(QColor("#219a9d"))
            for point in points:
                painter.drawEllipse(point, 5, 5)
    painter.end()
    return image


class ChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir gráfico — AURORA AutoFill")
        self.setMinimumWidth(400)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Tipo do gráfico"))
        self.kind = QComboBox()
        self.kind.addItems(CHART_TYPES)
        root.addWidget(self.kind)
        root.addWidget(QLabel("Título"))
        self.title_edit = QLineEdit("Meu gráfico")
        root.addWidget(self.title_edit)
        root.addWidget(QLabel("Dados: um item por linha (Rótulo;valor)"))
        self.data_edit = QPlainTextEdit("Janeiro;12\nFevereiro;22\nMarço;18")
        self.data_edit.setMinimumHeight(135)
        root.addWidget(self.data_edit)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#f2aa8f")
        self.error_label.setWordWrap(True)
        root.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.values = None

    def _validate(self):
        try:
            values = parse_chart_data(self.data_edit.toPlainText())
            title = self.title_edit.text().strip()
            if not title or len(title) > 70:
                raise ValueError("Informe um título de até 70 caracteres.")
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        self.values = values
        self.accept()


class InsertObjectsPanel(QWidget):
    """Terceira coluna compacta da faixa de formatação, à direita de Parágrafo."""
    def __init__(self, editor, parent=None, *, menu_factory=QMenu):
        super().__init__(parent)
        self.editor = editor
        self.setAccessibleName("Inserir")
        self.setFixedSize(300, 115)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.controls = QWidget(self)
        self.controls.setFixedSize(300, 91)
        controls = QHBoxLayout(self.controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(5)
        self.table_button = self._tool("▦", "Tabelas", "Inserir tabela editável")
        self.shape_button = self._tool("⬡", "Formas", "Inserir forma como imagem incorporada")
        self.chart_button = self._tool("▥", "Gráficos", "Criar gráfico com dados")
        for button in (self.table_button, self.shape_button, self.chart_button):
            controls.addWidget(button)
        layout.addWidget(self.controls)
        self.footer = RibbonFooter("Inserir", self._open_chart)
        self.footer.launcher.setToolTip("Criar gráfico")
        layout.addWidget(self.footer)

        table_menu = menu_factory(self.table_button)
        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(7, 7, 7, 7)
        grid.setSpacing(3)
        for row in range(5):
            for col in range(6):
                cell = QToolButton(grid_holder)
                cell.setFixedSize(23, 23)
                cell.setText("□")
                cell.setToolTip(f"{row + 1} linhas × {col + 1} colunas")
                cell.clicked.connect(
                    lambda _=False, r=row + 1, c=col + 1:
                    self._insert_table(r, c))
                grid.addWidget(cell, row, col)
        action = QWidgetAction(table_menu)
        action.setDefaultWidget(grid_holder)
        table_menu.addAction(action)
        table_menu.addAction("Definir linhas e colunas…", self._custom_table)
        self.table_button.setMenu(table_menu)

        shape_menu = menu_factory(self.shape_button)
        for label, key in SHAPES:
            shape_menu.addAction(label, lambda checked=False, k=key: self._insert_shape(k))
        self.shape_button.setMenu(shape_menu)

        chart_menu = menu_factory(self.chart_button)
        chart_menu.addAction("Criar gráfico com meus dados…", self._open_chart)
        self.chart_button.setMenu(chart_menu)

    @staticmethod
    def _tool(symbol, title, tooltip):
        button = QToolButton()
        button.setObjectName("fontTool")
        button.setText(symbol + "\n" + title)
        button.setToolTip(tooltip)
        button.setAccessibleName(title)
        button.setFocusPolicy(Qt.NoFocus)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setFixedSize(96, 87)
        return button

    def _insert_table(self, rows, columns):
        self.table_button.menu().close()
        try:
            insert_table(self.editor, rows, columns)
        except ValueError as exc:
            QMessageBox.warning(self.window(), "Tabela", str(exc))

    def _custom_table(self):
        rows, ok = QInputDialog.getInt(self.window(), "Inserir tabela",
                                       "Número de linhas:", 3, 1, 12)
        if not ok:
            return
        columns, ok = QInputDialog.getInt(self.window(), "Inserir tabela",
                                          "Número de colunas:", 3, 1, min(8, 80 // rows))
        if ok:
            self._insert_table(rows, columns)

    def _insert_shape(self, shape):
        if self.editor.insert_image(render_shape(shape)):
            self.editor.setFocus()

    def _open_chart(self):
        dialog = ChartDialog(self.window())
        if dialog.exec() == QDialog.Accepted and dialog.values:
            self.editor.insert_image(
                render_chart(dialog.kind.currentText(), dialog.values,
                             dialog.title_edit.text()))
            self.editor.setFocus()
