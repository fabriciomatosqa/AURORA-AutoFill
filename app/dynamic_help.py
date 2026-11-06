"""Guia visual somente leitura dos comandos dinâmicos disponíveis no editor.

Os exemplos correspondem ao menu do AURORA e não executam nenhum comando.
A janela não altera o banco, o conteúdo editado ou a área de transferência.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .themes import set_ui_style


# Mantenha estes exemplos sincronizados com o menu em AutoFillWindow._build_editor_page.
# Cada registro contém: nome visível, token inserido pelo menu e explicação.
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
          "Formata a data com códigos aceitos pelo AURORA. Por exemplo: "
          "%d = dia, %m = mês, %Y = ano, %H = hora, %M = minuto. "
          "Apenas parte dos códigos strftime do Python é suportada."),
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
        self.resize(760, 665)
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
                background: #091426; border: 0;
            }
            QWidget#dynamicHelpContent {
                background: #091426;
            }
            QFrame#dynamicHelpSection {
                background: #0c2035; border: 1px solid #28546a;
                border-radius: 11px;
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

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("dynamicHelpScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sections = {}
        self.token_labels = []
        content = QWidget()
        content.setObjectName("dynamicHelpContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 1, 5, 1)
        content_layout.setSpacing(11)
        for group_name, group_description, entries in DYNAMIC_HELP_SECTIONS:
            section = self._section(group_name, group_description, entries, content)
            self.sections[group_name] = section
            content_layout.addWidget(section)
        content_layout.addStretch(1)
        self.scroll_area.setWidget(content)
        root.addWidget(self.scroll_area, 1)

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
        return frame
