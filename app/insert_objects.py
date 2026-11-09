"""Tabela editável para a faixa Parágrafo do editor AURORA AutoFill.

Tabelas são elementos QTextTable nativos; o conteúdo continua editável
e é salvo no HTML existente dos comandos, sem formatos novos ou imagens.
"""
from __future__ import annotations

from PySide6.QtGui import QTextLength, QTextTableFormat
from PySide6.QtWidgets import (
    QGridLayout, QInputDialog, QMenu, QToolButton, QWidget, QWidgetAction,
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
        rows, ok = QInputDialog.getInt(button.window(), "Inserir tabela",
                                       "Número de linhas:", 3, 1, 12)
        if not ok:
            return
        columns, ok = QInputDialog.getInt(
            button.window(), "Inserir tabela",
            "Número de colunas:", 3, 1, min(8, 80 // rows))
        if ok:
            callback(rows, columns)

    menu.addAction("Definir linhas e colunas…", custom_table)
    return menu
