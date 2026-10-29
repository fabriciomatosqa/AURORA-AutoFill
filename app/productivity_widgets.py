"""Diálogos isolados: formulários, pesquisa global e estatísticas do AURORA."""
from __future__ import annotations

from datetime import date
from calendar import monthrange
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QGridLayout, QScrollArea, QSplitter, QVBoxLayout, QWidget, QPushButton,
)

from .smart_templates import fields_in
from .themes import current_theme
from .inline_images import AuroraReadOnlyPreview


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
    """Pesquisa por nome, atalho e conteúdo com prévia completa e rolável."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.selected_snippet = None
        self.setWindowTitle("AURORA — Pesquisa global de comandos")
        self.setMinimumSize(590, 510)
        self.resize(690, 680)
        self.setStyleSheet(dialog_style() + """
            QFrame#searchPreviewPanel {
                background: transparent; border: 0;
            }
            QLabel#searchPreviewHeading {
                color: #60ddd0; font-size: 12px; font-weight: 700;
            }
            QLabel#searchPreviewName {
                font-weight: 600; padding-bottom: 3px;
            }
            QTextEdit#readonlyPreview {
                background: #172d46; color: #e9f7ff;
                border: 1px solid #456a81; border-radius: 7px;
                padding: 9px;
            }
            QSplitter::handle:vertical {
                background: #315770; height: 5px; margin: 4px 0;
            }
        """ if current_theme() != "light" else dialog_style() + """
            QFrame#searchPreviewPanel { background: transparent; border: 0; }
            QLabel#searchPreviewHeading { color: #167d87; font-weight: 700; }
            QLabel#searchPreviewName { color: #18314b; font-weight: 600; }
            QTextEdit#readonlyPreview {
                background: white; color: #193451;
                border: 1px solid #8aabbc; border-radius: 7px;
                padding: 9px;
            }
            QSplitter::handle:vertical {
                background: #a6c9d3; height: 5px; margin: 4px 0;
            }
        """)
        root = QVBoxLayout(self)
        root.setSpacing(9)
        label = QLabel("Pesquise pelo nome, atalho ou conteúdo do comando")
        root.addWidget(label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ex.: chamado, bom dia, /resposta...")
        self.search.setAccessibleName("Pesquisar comandos")
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        # Keep typing focus in the search box while arrows navigate results.
        self.search.installEventFilter(self)
        root.addWidget(self.search)

        # The user can resize the results and preview without hiding either.
        self.content_splitter = QSplitter(Qt.Vertical)
        self.content_splitter.setObjectName("searchContentSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.matches = QListWidget()
        self.matches.setAccessibleName("Resultados da pesquisa")
        # Enter on the results list must insert, not just change selection.
        self.matches.installEventFilter(self)
        self.matches.itemDoubleClicked.connect(lambda _: self.choose())
        self.matches.currentItemChanged.connect(self._update_preview)
        self.content_splitter.addWidget(self.matches)

        preview_panel = QFrame()
        preview_panel.setObjectName("searchPreviewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(5)
        preview_title = QLabel("PRÉ-VISUALIZAÇÃO DO COMANDO")
        preview_title.setObjectName("searchPreviewHeading")
        preview_layout.addWidget(preview_title)
        self.preview_name = QLabel("Selecione um comando para visualizar o conteúdo completo.")
        self.preview_name.setObjectName("searchPreviewName")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)
        self.preview = AuroraReadOnlyPreview()
        self.preview.setAccessibleName("Texto completo do comando selecionado")
        self.preview.setMinimumHeight(150)
        preview_layout.addWidget(self.preview, 1)
        self.content_splitter.addWidget(preview_panel)
        self.matches.setMinimumHeight(160)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        root.addWidget(self.content_splitter, 1)

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
            self._clear_preview("Nenhum comando encontrado.")

    def _clear_preview(self, message="Selecione um comando para visualizar o conteúdo completo."):
        self.preview_name.setText(message)
        self.preview.clear()

    def _update_preview(self, current, _previous):
        if current is None:
            self._clear_preview()
            return
        snippet = current.data(Qt.UserRole)
        self.preview_name.setText(f"{snippet.title}   ·   {snippet.shortcut}")
        # Show the saved content, not an expanded snippet: this preview must
        # not evaluate variables, execute steps or read the clipboard.
        # AuroraReadOnlyPreview understands the same inline images and rich
        # formatting as the main editor while remaining non-editable.
        if snippet.rich_content:
            self.preview.setHtml(snippet.rich_content)
        else:
            self.preview.setPlainText(snippet.content)
        self.preview.verticalScrollBar().setValue(0)
        self.preview.horizontalScrollBar().setValue(0)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if watched is self.search and key in (Qt.Key_Down, Qt.Key_Up):
                count = self.matches.count()
                if count:
                    current = self.matches.currentRow()
                    step = 1 if key == Qt.Key_Down else -1
                    target = max(0, min(count - 1, current + step))
                    self.matches.setCurrentRow(target)
                    self.matches.scrollToItem(self.matches.item(target))
                # Arrow keys should never move the caret inside the search.
                return True
            if watched is self.matches and key in (Qt.Key_Return, Qt.Key_Enter):
                self.choose()
                return True
        return super().eventFilter(watched, event)

    def choose(self):
        current = self.matches.currentItem()
        if current is None:
            return
        self.selected_snippet = current.data(Qt.UserRole)
        self.accept()


MONTH_NAMES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
WEEKDAY_NAMES = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


class UsageStatisticsDialog(QDialog):
    """Calendário mensal de contagens locais; sem telemetria externa."""

    def __init__(self, store, parent=None, *, today=None):
        super().__init__(parent)
        self.store = store
        self.today = today
        anchor = today or date.today()
        self.display_month = date(anchor.year, anchor.month, 1)
        self.selected_day = anchor.day
        self.day_buttons = {}
        self.day_counts = {}
        self.setWindowTitle("Estatísticas locais — AURORA")
        self.setMinimumSize(590, 640)
        self.resize(610, 665)
        self.setStyleSheet(dialog_style())
        root = QVBoxLayout(self)
        root.setSpacing(9)

        title = QLabel("Uso dos comandos")
        title.setStyleSheet("font-weight: bold; font-size: 17px")
        root.addWidget(title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("‹")
        self.previous_button.setObjectName("usagePreviousMonth")
        self.previous_button.setAccessibleName("Mês anterior")
        self.previous_button.setToolTip("Ver mês anterior")
        self.previous_button.setFixedSize(40, 34)
        self.previous_button.clicked.connect(lambda: self._shift_month(-1))
        self.month_label = QLabel()
        self.month_label.setAlignment(Qt.AlignCenter)
        self.month_label.setStyleSheet("font-weight: bold; font-size: 15px;")
        self.next_button = QPushButton("›")
        self.next_button.setObjectName("usageNextMonth")
        self.next_button.setAccessibleName("Próximo mês")
        self.next_button.setToolTip("Ver próximo mês")
        self.next_button.setFixedSize(40, 34)
        self.next_button.clicked.connect(lambda: self._shift_month(1))
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.month_label, 1)
        navigation.addWidget(self.next_button)
        root.addLayout(navigation)

        calendar_widget = QWidget()
        calendar_layout = QVBoxLayout(calendar_widget)
        calendar_layout.setContentsMargins(0, 0, 0, 0)
        calendar_layout.setSpacing(5)
        weekdays = QGridLayout()
        weekdays.setHorizontalSpacing(5)
        for column, name in enumerate(WEEKDAY_NAMES):
            heading = QLabel(name)
            heading.setAlignment(Qt.AlignCenter)
            heading.setFixedSize(64, 22)
            weekdays.addWidget(heading, 0, column)
        calendar_layout.addLayout(weekdays)
        self.days_host = QWidget()
        self.days_layout = QGridLayout(self.days_host)
        self.days_layout.setContentsMargins(0, 0, 0, 0)
        self.days_layout.setHorizontalSpacing(5)
        self.days_layout.setVerticalSpacing(5)
        for column in range(7):
            self.days_layout.setColumnMinimumWidth(column, 64)
        calendar_layout.addWidget(self.days_host)
        # Keep cells square, centered; don't stretch the calendar into bars.
        wrapper = QHBoxLayout()
        wrapper.addStretch()
        wrapper.addWidget(calendar_widget)
        wrapper.addStretch()
        root.addLayout(wrapper)

        self.day_details = QLabel()
        self.day_details.setObjectName("usageDayDetails")
        self.day_details.setWordWrap(True)
        self.day_details.setMinimumHeight(38)
        root.addWidget(self.day_details)

        self.top_label = QLabel()
        self.top_label.setWordWrap(True)
        root.addWidget(self.top_label)
        root.addStretch(1)
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

    def _shift_month(self, offset: int):
        serial = self.display_month.year * 12 + self.display_month.month - 1 + offset
        year, month_zero = divmod(serial, 12)
        if not 1 <= year <= 9999:
            return
        self.display_month = date(year, month_zero + 1, 1)
        self.selected_day = None
        self.refresh()

    def _day_style(self, day: int):
        count = self.day_counts.get(day, 0)
        peak = max(self.day_counts.values(), default=0)
        light = current_theme() == "light"
        if count == 0:
            background = "#f1f5f9" if light else "#172d42"
        else:
            strength = count / max(1, peak)
            if strength < .35:
                background = "#d4eeec" if light else "#24566b"
            elif strength < .7:
                background = "#9fded8" if light else "#237b83"
            else:
                background = "#55c4b5" if light else "#249d95"
        foreground = "#17364e" if light else "#f5ffff"
        outline = "#106e74" if light else "#8df7dc"
        selected = self.selected_day == day
        border = f"2px solid {outline}" if selected else (
            "1px solid #a8c3d2" if light else "1px solid #3a627b")
        return (
            "QPushButton {"
            f"background: {background}; color: {foreground}; border: {border};"
            "border-radius: 8px; padding: 2px; font-size: 11px;"
            "font-weight: 600; text-align: center; }"
            f"QPushButton:hover {{ border: 2px solid {outline}; }}"
            f"QPushButton:focus {{ border: 2px solid {outline}; }}"
        )

    def _render_days(self):
        while self.days_layout.count():
            item = self.days_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.day_buttons = {}
        first = self.display_month
        self.month_label.setText(f"{MONTH_NAMES[first.month - 1]} {first.year}")
        self.day_counts = self.store.usage_days(first.year, first.month)
        total_days = monthrange(first.year, first.month)[1]
        start_weekday = first.weekday()
        for day in range(1, total_days + 1):
            index = start_weekday + day - 1
            count = self.day_counts.get(day, 0)
            uses = "uso" if count == 1 else "usos"
            button = QPushButton(f"{day}\n{count} {uses}")
            button.setObjectName("usageCalendarDay")
            button.setAccessibleName(
                f"{day} de {MONTH_NAMES[first.month - 1]} de {first.year}: {count} {uses}")
            button.setToolTip(f"{day:02d}/{first.month:02d}/{first.year}: {count} {uses}")
            button.setFixedSize(64, 64)
            button.clicked.connect(lambda checked=False, selected=day: self._select_day(selected))
            self.days_layout.addWidget(button, index // 7, index % 7)
            self.day_buttons[day] = button
        self._update_selected_day()

    def _select_day(self, day: int):
        if day not in self.day_buttons:
            return
        self.selected_day = day
        self._update_selected_day()

    def _update_selected_day(self):
        for day, button in self.day_buttons.items():
            button.setStyleSheet(self._day_style(day))
        if self.selected_day not in self.day_buttons:
            self.day_details.setText(
                "Selecione um dia no calendário para consultar os usos e comandos mais frequentes.")
            return
        day = date(self.display_month.year, self.display_month.month, self.selected_day)
        count = self.day_counts.get(self.selected_day, 0)
        top = self.store.usage_day_top(day)
        detail = (", ".join(f"{title} ({uses})" for title, uses in top)
                  if top else "nenhum comando usado")
        self.day_details.setText(
            f"{day:%d/%m/%Y} — {count} {'uso' if count == 1 else 'usos'}. "
            f"Mais usados no dia: {detail}.")

    def refresh(self):
        # Preserve the previously approved four-number summary verbatim.
        report = self.store.usage_report(self.today)
        self.summary.setText(
            f"Hoje: {report['today']}    |    Este mês: {report['month']}    |    "
            f"Este ano: {report['year']}    |    Total: {report['total']}")
        top = report["top"][:5]
        self.top_label.setText(
            "Mais usados: " + (", ".join(f"{title} ({n})" for _, title, _, n in top)
                              if top else "nenhuma expansão confirmada ainda"))
        self._render_days()

    def _clear(self):
        answer = QMessageBox.question(
            self, "Limpar estatísticas",
            "Excluir apenas os contadores de uso? Seus comandos e pastas permanecerão intactos.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.store.reset_usage()
            self.refresh()
