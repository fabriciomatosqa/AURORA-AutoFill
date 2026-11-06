"""Guia visual somente leitura dos comandos dinâmicos disponíveis no editor.

Os exemplos correspondem ao menu do AURORA e não executam nenhum comando.
A janela não altera o banco, o conteúdo editado ou a área de transferência.
"""
from __future__ import annotations

from datetime import datetime
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from .themes import set_ui_style
from .date_formats import FORMAT_CODE_GROUPS, format_date_ptbr


# Mantenha estes exemplos sincronizados com o menu em AutoFillWindow._build_editor_page.
# Cada registro contém: nome visível, token inserido pelo menu e explicação.
def _alphabetical_label(label: str) -> str:
    """Ordenação alfabética humana, ignorando os acentos do português."""
    normalized = unicodedata.normalize("NFKD", label)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()


DYNAMIC_HELP_SECTIONS = (
    ("Data e hora",
     "Valores produzidos na hora de usar o comando, a partir do relógio do computador.",
     (
         ("Data atual", "{{data}}",
          "Insere a data de hoje no formato dia/mês/ano. Ex.: 06/11/2026."),
         ("Hora atual", "{{hora}}",
          "Insere a hora atual em formato de 24 horas. Ex.: 14:30."),
         ("Data e hora", "{{data_hora}}",
          "Combina a data e a hora atuais. Ex.: 06/11/2026 14:30."),
         ("Data +7 dias", "{{data:+7}}",
          "Calcula uma data sete dias à frente. É possível alterar o número "
          "de dias, dentro do limite de 3.650 dias."),
         ("Data -1 dia", "{{data:-1}}",
          "Calcula a data de ontem. Use valores negativos para voltar dias."),
         ("Data personalizada", "{{data_formato:%Y-%m-%d}}",
          "Personalize o formato com os códigos da tabela desta ajuda. "
          "Use %a para sex, %A para sexta-feira, %b para nov e %B para novembro. "
          "Os nomes são sempre mostrados em português do Brasil."),
     )),
    ("Área de transferência e cursor",
     "Reaproveite o texto copiado ou indique o ponto onde continuará digitando.",
     (
         ("Área de transferência", "{{clipboard}}",
          "Insere o texto que estiver copiado no momento da expansão. "
          "Este token não transporta imagens ou arquivos."),
         ("Posição do cursor", "{{cursor}}",
          "Marca onde o cursor deverá ficar após inserir o texto. "
          "O posicionamento depende da compatibilidade com o aplicativo de destino."),
     )),
    ("Cálculos",
     "Faça contas simples sem executar código Python.",
     (
         ("Cálculo seguro", "{{calculo:12*3}}",
          "Substitui a expressão pelo resultado da conta. Ex.: 12 × 3 = 36. "
          "Aceita operações aritméticas básicas e parênteses, com limites de segurança."),
     )),
    ("Formulários interativos",
     "Antes de inserir o comando, o AURORA solicita os dados que faltam.",
     (
         ("Campo de formulário", "{{campo:Nome}}",
          "Abre um campo para você preencher o nome na hora. "
          "Campos repetidos podem receber respostas diferentes. "
          "Máximo de 12 campos por comando."),
         ("Lista de opções", "{{escolha:Situação|Aberto|Concluído}}",
          "Mostra uma lista para escolher entre valores predefinidos. "
          "Separe as alternativas com o caractere |."),
     )),
    ("Automações",
     "Ações em sequência que precisam da sua confirmação antes de executar.",
     (
         ("Avançar campo (Tab)", "{{tab}}",
          "Avança para o próximo campo do formulário, quando o aplicativo "
          "de destino pode ser verificado com segurança."),
         ("Enviar Enter", "{{enter}}",
          "Envia a tecla Enter, que pode confirmar ou enviar formulários. "
          "Confira o destino antes de executar."),
         ("Aguardar 250 ms", "{{espera:250}}",
          "Pausa a sequência por 250 milissegundos. Cada pausa aceita "
          "de 50 a 2.000 ms; o total máximo é de 5 segundos."),
     )),
)


class DynamicCommandsHelpDialog(QDialog):
    """Scrollable, accessible guide matching the existing dark/light UI themes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dynamicCommandsHelpDialog")
        self.setWindowTitle("Ajuda — comandos dinâmicos | AURORA AutoFill")
        self.setMinimumSize(600, 460)
        self.resize(940, 665)
        set_ui_style(self, """
            QDialog#dynamicCommandsHelpDialog {
                background: #091426; color: #eaf4ff;
            }
            QLabel#dynamicHelpTitle {
                color: #eaf4ff; font-size: 20px; font-weight: 750;
                background: transparent;
            }
            QLabel#dynamicHelpIntro, QLabel#dynamicHelpFooter {
                color: #b8cde0; font-size: 12px; background: transparent;
            }
            QScrollArea#dynamicHelpScroll {
                background: #0c2035; border: none;
            }
            QWidget#dynamicHelpContent {
                background: #0c2035;
            }
            QFrame#dynamicHelpSection {
                background: transparent; border: none;
            }
            QLabel#dynamicHelpSectionTitle {
                background: transparent; color: #8cf1d7;
                font-size: 15px; font-weight: 700;
            }
            QLabel#dynamicHelpSectionIntro {
                background: transparent; color: #b8cde0;
                font-size: 12px;
            }
            QFrame#dynamicHelpEntry {
                background: #143345; border: 1px solid #28546a;
                border-radius: 8px;
            }
            QLabel#dynamicHelpEntryName {
                background: transparent; color: #effaff;
                font-size: 12px; font-weight: 700;
            }
            QLabel#dynamicHelpToken {
                background: #102338; border: 1px solid #416777;
                border-radius: 5px; padding: 6px 9px;
                color: #8cf1d7; font-family: Consolas, monospace;
                font-size: 12px;
            }
            QLabel#dynamicHelpDescription {
                background: transparent; color: #d2eafa;
                font-size: 12px;
            }
            QTabWidget#dynamicHelpTabs::pane {
                background: #0c2035;
                border: 1px solid #416777;
                border-top: 1px solid #72e6d5;
                border-top-left-radius: 0px;
                border-top-right-radius: 10px;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                top: -1px;
            }
            QTabWidget#dynamicHelpTabs QTabBar::tab {
                background: #102338; color: #bdd6e6;
                border: 1px solid #416777;
                border-bottom: 1px solid #416777;
                padding: 10px 13px;
                margin-right: 3px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabWidget#dynamicHelpTabs QTabBar::tab:hover:!selected {
                background: #19364b; color: #eaf4ff;
                border-color: #72e6d5;
            }
            QTabWidget#dynamicHelpTabs QTabBar::tab:selected {
                background: #0c2035; color: #8cf1d7;
                border: 1px solid #72e6d5;
                border-bottom: 1px solid #0c2035;
                margin-bottom: -1px;
            }
            QFrame#dateHelpGroup {
                background: #0c2035; border: 1px solid #28546a;
                border-radius: 10px;
            }
            QLabel#dateHelpTitle {
                color: #eaf4ff; font-size: 17px; font-weight: 700;
                background: transparent;
            }
            QLabel#dateHelpSectionTitle {
                color: #8cf1d7; font-size: 14px; font-weight: 700;
                background: transparent;
            }
            QLabel#dateHelpIntro, QLabel#dateHelpExplanation {
                color: #bdd6e6; font-size: 12px; background: transparent;
            }
            QLabel#dateHelpCode {
                color: #8cf1d7; font: bold 12px Consolas, monospace;
                background: #143345; border: 1px solid #416777;
                border-radius: 5px; padding: 5px 7px;
            }
            QLabel#dateHelpExample {
                color: #edfaff; font-size: 12px;
                background: transparent;
            }
            QLabel#dateHelpColumn {
                color: #8baec2; font-size: 11px;
                font-weight: 700; background: transparent;
            }
            QFrame#dateHelpPreview {
                background: #143345; border: 1px solid #416777;
                border-radius: 9px;
            }
            QLabel#dateHelpPreviewCode {
                color: #8cf1d7; font: 12px Consolas, monospace;
                background: transparent;
            }
            QLabel#dateHelpPreviewOutput {
                color: #f5faff; font-size: 14px; font-weight: 700;
                background: transparent;
            }
            QPushButton#dateHelpShortcut {
                background: #19364b; color: #8cf1d7;
                border: 1px solid #416777; border-radius: 7px;
                min-height: 30px; padding: 6px 12px;
                text-align: left;
            }
            QPushButton#dateHelpShortcut:hover {
                border-color: #72e6d5; background: #28546a;
            }
            QPushButton#dynamicHelpClose {
                background: #19364b; color: #effaff;
                border: 1px solid #416777; border-radius: 7px;
                min-height: 32px; padding: 5px 20px;
            }
            QPushButton#dynamicHelpClose:hover {
                background: #28546a; border-color: #72e6d5;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(11)
        title = QLabel("Como usar os comandos dinâmicos")
        title.setObjectName("dynamicHelpTitle")
        root.addWidget(title)

        intro = QLabel(
            "No editor, clique em “Inserir comando dinâmico” e escolha uma "
            "opção. O código aparece no texto e só é resolvido quando você "
            "utiliza o atalho. Você também pode digitar esses códigos manualmente.")
        intro.setObjectName("dynamicHelpIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.sections = {}
        self.token_labels = []
        self.group_pages = {}
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("dynamicHelpTabs")
        self.tabs.setDocumentMode(False)
        self.tabs.setMovable(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        labels = {
            "Formulários interativos": "Formulários",
        }
        # Apenas os cinco grupos do menu em ordem alfabética.
        # Códigos de data e hora aparecem na própria aba Data e hora.
        for group_name, group_description, entries in sorted(
                DYNAMIC_HELP_SECTIONS, key=lambda section: _alphabetical_label(section[0])):
            page = self._build_group_page(group_name, group_description, entries)
            self.group_pages[group_name] = page
            self.tabs.addTab(page, labels.get(group_name, group_name))
        self.scroll_area = self.group_pages["Data e hora"]
        root.addWidget(self.tabs, 1)

        footer = QHBoxLayout()
        note = QLabel(
            "Dica: teste automações em um formulário de exemplo. "
            "No Linux, ações de teclado podem ser oferecidas apenas como texto "
            "para colagem manual.")
        note.setObjectName("dynamicHelpFooter")
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        self.close_button = QPushButton("Fechar")
        self.close_button.setObjectName("dynamicHelpClose")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button, 0, Qt.AlignBottom)
        root.addLayout(footer)

        # A largura acompanha a soma das abas, com limite na área útil
        # da tela para não cortar botões em notebooks ou monitores pequenos.
        screen = self.screen() or QGuiApplication.primaryScreen()
        tab_width = self.tabs.tabBar().sizeHint().width()
        desired_width = max(850, tab_width + 58)
        if screen is not None:
            available = screen.availableGeometry()
            desired_width = min(desired_width, max(600, available.width() - 36))
            desired_height = min(680, max(460, available.height() - 72))
        else:
            desired_height = 680
        self.setMinimumWidth(min(850, desired_width))
        self.resize(desired_width, desired_height)

    def _build_group_page(self, group_name, group_description, entries):
        """Um grupo por aba, sem contorno duplicado na junção com as abas."""
        scroll = QScrollArea(self)
        scroll.setObjectName("dynamicHelpScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("dynamicHelpContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        section = self._section(group_name, group_description, entries, content)
        self.sections[group_name] = section
        layout.addWidget(section)
        if group_name == "Data e hora":
            self.date_codes_content = self._build_date_codes_content(content)
            layout.addWidget(self.date_codes_content)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _section(self, group_name, group_description, entries, parent):
        frame = QFrame(parent)
        frame.setObjectName("dynamicHelpSection")
        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(13, 12, 13, 13)
        section_layout.setSpacing(8)

        heading = QLabel(group_name)
        heading.setObjectName("dynamicHelpSectionTitle")
        section_layout.addWidget(heading)
        overview = QLabel(group_description)
        overview.setObjectName("dynamicHelpSectionIntro")
        overview.setWordWrap(True)
        section_layout.addWidget(overview)

        for name, token, description in entries:
            entry = QFrame(frame)
            entry.setObjectName("dynamicHelpEntry")
            entry_layout = QVBoxLayout(entry)
            entry_layout.setContentsMargins(10, 8, 10, 9)
            entry_layout.setSpacing(5)
            name_label = QLabel(name)
            name_label.setObjectName("dynamicHelpEntryName")
            entry_layout.addWidget(name_label)
            code_label = QLabel(token)
            code_label.setObjectName("dynamicHelpToken")
            code_label.setTextFormat(Qt.PlainText)
            code_label.setWordWrap(True)
            code_label.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            code_label.setToolTip("Selecione o texto para copiar o código do comando.")
            self.token_labels.append(code_label)
            entry_layout.addWidget(code_label)
            help_text = QLabel(description)
            help_text.setObjectName("dynamicHelpDescription")
            help_text.setWordWrap(True)
            entry_layout.addWidget(help_text)
            section_layout.addWidget(entry)
        if group_name == "Data e hora":
            self.date_reference_button = QPushButton(
                "Consultar códigos de formatação (%a, %A, %b, %B, %H...)")
            self.date_reference_button.setObjectName("dateHelpShortcut")
            self.date_reference_button.clicked.connect(self._scroll_to_date_codes)
            section_layout.addWidget(self.date_reference_button)
        return frame

    def _scroll_to_date_codes(self):
        """Rola até a tabela no final de Data e hora, sem trocar de aba."""
        self.tabs.setCurrentWidget(self.scroll_area)
        self.scroll_area.ensureWidgetVisible(self.date_codes_heading, 0, 8)

    def _build_date_codes_content(self, parent):
        """Tabela de strftime no fim da mesma área rolável de Data e hora."""
        sample = datetime(2026, 11, 6, 14, 30, 45, 123456)
        content = QWidget(parent)
        content.setObjectName("dynamicHelpContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(13, 18, 13, 13)
        layout.setSpacing(11)

        heading = QLabel("Códigos para personalizar data e hora")
        heading.setObjectName("dateHelpTitle")
        self.date_codes_heading = heading
        layout.addWidget(heading)
        intro = QLabel(
            "Use os códigos abaixo dentro de {{data_formato:...}}. "
            "Os nomes dos dias e dos meses aparecem sempre em português do Brasil, "
            "mesmo que o Windows ou Linux esteja configurado em outro idioma. "
            "Os exemplos usam 06/11/2026, sexta-feira, às 14:30:45.")
        intro.setObjectName("dateHelpIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        sample_frame = QFrame(content)
        sample_frame.setObjectName("dateHelpPreview")
        sample_layout = QVBoxLayout(sample_frame)
        sample_layout.setContentsMargins(13, 11, 13, 11)
        sample_layout.setSpacing(5)
        sample_token = "{{data_formato:%A, %d de %B de %Y}}"
        code = QLabel(sample_token)
        code.setObjectName("dateHelpPreviewCode")
        code.setTextFormat(Qt.PlainText)
        code.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        code.setWordWrap(True)
        sample_layout.addWidget(code)
        sample_output = QLabel(format_date_ptbr(sample, "%A, %d de %B de %Y"))
        sample_output.setObjectName("dateHelpPreviewOutput")
        sample_output.setWordWrap(True)
        sample_layout.addWidget(sample_output)
        layout.addWidget(sample_frame)

        self.date_code_labels = {}
        self.date_code_examples = {}
        for group_title, rows in FORMAT_CODE_GROUPS:
            group = QFrame(content)
            group.setObjectName("dateHelpGroup")
            grid = QGridLayout(group)
            grid.setContentsMargins(12, 12, 12, 12)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            section_title = QLabel(group_title)
            section_title.setObjectName("dateHelpSectionTitle")
            grid.addWidget(section_title, 0, 0, 1, 3)
            for col, label in enumerate(("CÓDIGO", "O QUE SIGNIFICA", "EXEMPLO")):
                column = QLabel(label)
                column.setObjectName("dateHelpColumn")
                grid.addWidget(column, 1, col)
            for row_num, (specifier, description) in enumerate(rows, 2):
                code_label = QLabel(specifier)
                code_label.setObjectName("dateHelpCode")
                code_label.setTextFormat(Qt.PlainText)
                code_label.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                code_label.setToolTip("Código usado dentro de {{data_formato:...}}")
                grid.addWidget(code_label, row_num, 0, Qt.AlignTop)
                description_label = QLabel(description)
                description_label.setObjectName("dateHelpExplanation")
                description_label.setWordWrap(True)
                grid.addWidget(description_label, row_num, 1)
                rendered = format_date_ptbr(sample, specifier)
                example_label = QLabel(rendered or "(vazio sem fuso)")
                example_label.setObjectName("dateHelpExample")
                example_label.setWordWrap(True)
                grid.addWidget(example_label, row_num, 2)
                self.date_code_labels[specifier] = code_label
                self.date_code_examples[specifier] = example_label
            grid.setColumnStretch(1, 3)
            grid.setColumnStretch(2, 2)
            layout.addWidget(group)
        footnote = QLabel(
            "Atenção: %D usa o formato americano (mês/dia/ano). "
            "%U e %W contam semanas de modo diferente de %V (ISO). "
            "%z e %Z ficam vazios quando a data não possui fuso definido. "
            "O formato personalizado aceita até 48 caracteres.")
        footnote.setObjectName("dateHelpIntro")
        footnote.setWordWrap(True)
        layout.addWidget(footnote)
        return content
