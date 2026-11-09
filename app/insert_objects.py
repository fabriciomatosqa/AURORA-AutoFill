"""Tabela editável para a faixa Parágrafo do editor AURORA AutoFill.

Tabelas são elementos QTextTable nativos; o conteúdo continua editável
e é salvo no HTML existente dos comandos, sem formatos novos ou imagens.
"""
from __future__ import annotations

from PySide6.QtGui import QTextLength, QTextTableFormat
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QMenu, QSpinBox,
    QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)


def insert_table(editor, rows: int, columns: int):
    """Insere uma tabela nativa e posiciona o foco na primeira célula."""
    if not 1 <= rows <= 12 or not 1 <= columns <= 8 or rows * columns > 80:
        raise ValueError("Use no máximo 12 linhas, 8 colunas e 80 células.")
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    try:
        table_format = QTextTableFormat()
        table_format.setBorder(1)
        table_format.setCellPadding(5)
        table_format.setCellSpacing(0)
        table_format.setWidth(QTextLength(QTextLength.PercentageLength, 90))
        table = cursor.insertTable(rows, columns, table_format)
    finally:
        cursor.endEditBlock()
    editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
    editor.setFocus()
    return table


class TableDimensionsDialog(QDialog):
    """Uma única janela para definir linhas e colunas da tabela."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inserir tabela")
        self.setModal(True)

        layout = QVBoxLayout(self)
        fields = QFormLayout()
        self.rows_input = QSpinBox(self)
        self.rows_input.setAccessibleName("Número de linhas")
        self.rows_input.setRange(1, 12)
        self.rows_input.setValue(3)
        fields.addRow("Número de linhas:", self.rows_input)

        self.columns_input = QSpinBox(self)
        self.columns_input.setAccessibleName("Número de colunas")
        self.columns_input.setRange(1, 8)
        self.columns_input.setValue(3)
        fields.addRow("Número de colunas:", self.columns_input)
        layout.addLayout(fields)

        # Respeita o limite global de 80 células sem mostrar dois diálogos.
        self.rows_input.valueChanged.connect(self._limit_columns)
        self._limit_columns(self.rows_input.value())

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.rows_input.setFocus()
        self.rows_input.selectAll()

    def _limit_columns(self, rows):
        self.columns_input.setMaximum(min(8, 80 // rows))

    def dimensions(self):
        return self.rows_input.value(), self.columns_input.value()


def build_table_menu(button, callback, *, menu_factory=QMenu):
    """Grade 5x6 e dimensões personalizadas, no menu da faixa Parágrafo."""
    menu = menu_factory(button)
    holder = QWidget(menu)
    grid = QGridLayout(holder)
    grid.setContentsMargins(7, 7, 7, 7)
    grid.setSpacing(3)
    for row in range(5):
        for col in range(6):
            cell = QToolButton(holder)
            cell.setFixedSize(23, 23)
            cell.setText("□")
            cell.setToolTip(f"{row + 1} linhas × {col + 1} colunas")
            cell.setAccessibleName(f"Tabela com {row + 1} linhas e {col + 1} colunas")
            cell.clicked.connect(
                lambda _=False, r=row + 1, c=col + 1: (
                    menu.close(), callback(r, c)))
            grid.addWidget(cell, row, col)
    action = QWidgetAction(menu)
    action.setDefaultWidget(holder)
    menu.addAction(action)

    def custom_table():
        dialog = TableDimensionsDialog(button.window())
        if dialog.exec() == QDialog.Accepted:
            callback(*dialog.dimensions())

    menu.addAction("Definir linhas e colunas…", custom_table)
    return menu
