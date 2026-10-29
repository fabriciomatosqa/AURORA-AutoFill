"""Diálogos isolados: formulários, pesquisa global e estatísticas do AURORA."""
from __future__ import annotations

from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QScrollArea, QVBoxLayout, QWidget, QPushButton,
)

from .smart_templates import fields_in
from .themes import current_theme


def dialog_style():
    if current_theme() == "light":
        return """
        QDialog { background: #f5fbff; color: #18314b; }
        QLabel { color: #18314b; }
        QLineEdit, QComboBox, QListWidget { background: white; color: #193451;
          border: 1px solid #8aabbc; border-radius: 6px; padding: 6px; }
        QPushButton { padding: 7px 12px; background: #d9eaf1; color: #173348;
          border: 1px solid #91b5bf; border-radius: 7px; }
        QProgressBar { border: 1px solid #a2c7cf; border-radius: 5px;
          background: white; color: #193451; text-align: center; }
        QProgressBar::chunk { background: #36aab6; border-radius: 4px; }
        """
    return """
        QDialog { background: #0b1a2c; color: #e6f6ff; }
        QLabel { color: #e6f6ff; }
        QLineEdit, QComboBox, QListWidget { background: #172d46; color: #e9f7ff;
          border: 1px solid #456a81; border-radius: 6px; padding: 6px; }
        QPushButton { padding: 7px 12px; background: #173e54; color: #e9f7ff;
          border: 1px solid #4b7989; border-radius: 7px; }
        QProgressBar { border: 1px solid #456a81; border-radius: 5px;
          background: #152d44; color: #eafaff; text-align: center; }
        QProgressBar::chunk { background: #38c9bc; border-radius: 4px; }
        """


class FieldsDialog(QDialog):
    """Recebe respostas, sem salvar valores preenchidos no modelo ou em logs."""

    def __init__(self, template, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preencher campos do AURORA")
        self.setMinimumWidth(460)
        self.setStyleSheet(dialog_style())
        self.fields = fields_in(template)
        self.controls = {}
        main = QVBoxLayout(self)
        info = QLabel("Preencha os campos antes de inserir o comando.")
        info.setWordWrap(True)
        main.addWidget(info)
        form = QFormLayout()
        for field in self.fields:
            if field.kind == "choice":
                control = QComboBox()
                control.addItems(field.options)
            else:
                control = QLineEdit()
                control.setText(field.default)
                control.setMaxLength(600)
                control.setPlaceholderText(field.label)
            control.setAccessibleName(field.label)
            form.addRow(field.label + ":", control)
            self.controls[field.label.casefold()] = control
        main.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Continuar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)
        if self.fields:
            self.controls[self.fields[0].label.casefold()].setFocus()

    def values(self) -> dict[str, str]:
        return {name: (widget.currentText() if isinstance(widget, QComboBox)
                       else widget.text()) for name, widget in self.controls.items()}


class QuickSearchDialog(QDialog):
    """Localiza comandos em todas as pastas sem abrir o editor."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected_snippet = None
        self.setWindowTitle("AURORA — Pesquisa global de comandos")
        self.setMinimumSize(510, 430)
        self.setStyleSheet(dialog_style())
        root = QVBoxLayout(self)
        label = QLabel("Pesquise pelo nome, atalho ou conteúdo do comando")
        root.addWidget(label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ex.: chamado, bom dia, /resposta...")
        self.search.setAccessibleName("Pesquisar comandos")
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        root.addWidget(self.search)
        self.matches = QListWidget()
        self.matches.setAccessibleName("Resultados da pesquisa")
        self.matches.itemDoubleClicked.connect(lambda _: self.choose())
        self.matches.currentItemChanged.connect(self._update_preview)
        root.addWidget(self.matches, 1)
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setMaximumHeight(80)
        root.addWidget(self.preview)
        row = QHBoxLayout()
        row.addStretch()
        close_button = QPushButton("Cancelar")
        close_button.clicked.connect(self.reject)
        insert = QPushButton("Selecionar comando")
        insert.clicked.connect(self.choose)
        row.addWidget(close_button)
        row.addWidget(insert)
        root.addLayout(row)
        self.refresh()
        self.search.setFocus()

    def refresh(self, *_):
        query = self.search.text().strip()
        rows = self.store.snippets(query=query)[:60]
        self.matches.clear()
        for snippet in rows:
            item = QListWidgetItem(f"{snippet.title}   ·   {snippet.shortcut}")
            item.setData(Qt.UserRole, snippet)
            self.matches.addItem(item)
        if rows:
            self.matches.setCurrentRow(0)
        else:
            self.preview.setText("Nenhum comando encontrado.")

    def _update_preview(self, current, _previous):
        if current:
            snippet = current.data(Qt.UserRole)
            self.preview.setText(snippet.content[:230])
        else:
            self.preview.clear()

    def choose(self):
        current = self.matches.currentItem()
        if current is None:
            return
        self.selected_snippet = current.data(Qt.UserRole)
        self.accept()


class UsageStatisticsDialog(QDialog):
    """Contadores agregados e barras mensais; nenhuma telemetria externa."""

    def __init__(self, store, parent=None, *, today=None):
        super().__init__(parent)
        self.store = store
        self.today = today
        self.setWindowTitle("Estatísticas locais — AURORA")
        self.setMinimumSize(550, 500)
        self.setStyleSheet(dialog_style())
        root = QVBoxLayout(self)
        title = QLabel("Uso dos comandos")
        title.setStyleSheet("font-weight: bold; font-size: 17px")
        root.addWidget(title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        root.addWidget(QLabel("Expansões por mês"))
        self.container = QWidget()
        self.months_layout = QVBoxLayout(self.container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.container)
        root.addWidget(scroll, 1)
        self.top_label = QLabel()
        self.top_label.setWordWrap(True)
        root.addWidget(self.top_label)
        row = QHBoxLayout()
        clear = QPushButton("Limpar estatísticas")
        clear.clicked.connect(self._clear)
        row.addWidget(clear)
        row.addStretch()
        close = QPushButton("Fechar")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)
        self.refresh()

    def refresh(self):
        report = self.store.usage_report(self.today)
        self.summary.setText(
            f"Hoje: {report['today']}    |    Este mês: {report['month']}    |    "
            f"Este ano: {report['year']}    |    Total: {report['total']}")
        while self.months_layout.count():
            item = self.months_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        months = dict(report["months"])
        anchor = self.today or date.today()
        first = (anchor.year * 12 + anchor.month - 1)
        values = []
        for index in range(11, -1, -1):
            serial = first - index
            year, month_index = divmod(serial, 12)
            key = f"{year:04d}-{month_index+1:02d}"
            values.append((key, months.get(key, 0)))
        maximum = max(1, *(count for _, count in values))
        for key, count in values:
            bar = QProgressBar()
            bar.setRange(0, maximum)
            bar.setValue(count)
            bar.setFormat(f"{key}     {count} expansões")
            bar.setMinimumHeight(22)
            self.months_layout.addWidget(bar)
        top = report["top"][:5]
        self.top_label.setText(
            "Mais usados: " + (", ".join(f"{title} ({n})" for _, title, _, n in top)
                              if top else "nenhuma expansão confirmada ainda"))
        self.months_layout.addStretch()

    def _clear(self):
        answer = QMessageBox.question(
            self, "Limpar estatísticas",
            "Excluir apenas os contadores de uso? Seus comandos e pastas permanecerão intactos.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.store.reset_usage()
            self.refresh()
