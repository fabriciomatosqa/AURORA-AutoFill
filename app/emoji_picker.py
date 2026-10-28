"""Seletor de emojis para o editor de snippets do AURORA AutoFill.

Somente caracteres Unicode são inseridos. A escolha não depende da área de
transferência, não altera fontes salvas e não requer serviços online.
"""
from __future__ import annotations

import unicodedata

from PySide6.QtCore import QPoint, Qt, QSize
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from .themes import current_theme
from .emoji_art import emoji_icon

# Descrições concisas em português; aliases em inglês facilitam a busca.
_DATA = (
    ("Carinhas", "😀", """
😀|rosto sorridente|grin happy
😃|sorriso aberto|smile
😄|sorriso feliz|happy
😁|sorrindo com dentes|grin
😆|rindo|laugh
😅|sorriso suando|sweat
🤣|rolando de rir|rofl
😂|lágrimas de alegria|joy
🙂|sorriso leve|slightly smiling
🙃|rosto invertido|upside down
😉|piscadinha|wink
😊|sorriso tímido|blush
😇|anjinho|angel
🥰|apaixonado|love
😍|olhos apaixonados|heart eyes
🤩|deslumbrado|star eyes
😘|beijo|kiss
😗|mandando beijo|kiss
😚|beijo de olhos fechados|kiss
😋|delícia|yum
😛|língua para fora|tongue
😜|piscadinha com língua|wink tongue
🤪|rosto maluco|zany
😝|língua e olhos fechados|tongue
🤑|dinheiro nos olhos|money
🤗|abraço|hug
🤭|risada escondida|giggle
🫢|surpresa com mão na boca|gasp
🤫|silêncio|shush
🤔|pensando|thinking
🫡|saudação|salute
🤐|boca de zíper|zipper
😐|neutro|neutral
😑|sem expressão|expressionless
😶|sem palavras|speechless
🙄|revirando os olhos|rolling eyes
😏|sorriso de canto|smirk
😴|dormindo|sleep
🥱|bocejando|yawn
😔|triste|sad
😢|chorando|cry
😭|chorando muito|sob
😤|frustrado|frustrated
😡|bravo|angry
🤬|xingando|swear
😱|gritando|scream
😨|assustado|fear
😰|nervoso|nervous
😳|envergonhado|flushed
🥺|olhos de pedido|pleading
😎|óculos escuros|cool
🤓|nerd|nerd
🥳|festa|party
🤠|caubói|cowboy
🥶|congelando|cold
🥵|com calor|hot
🤒|doente|sick
😷|máscara|mask
🤢|enjoo|nauseated
🤮|vomitando|vomit
💀|caveira|skull
👻|fantasma|ghost
🤖|robô|robot
"""),
    ("Pessoas", "👋", """
👋|aceno|wave
🤚|mão levantada|raised hand
🖐️|mão aberta|hand
✋|pare|stop hand
👌|perfeito|ok hand
🤌|dedos unidos|pinched
🤏|pouquinho|pinching
✌️|vitória|peace
🤞|dedos cruzados|crossed fingers
🫰|coração com dedos|finger heart
🤟|te amo|love you
🤘|rock|rock
🤙|me liga|call me
👈|apontar esquerda|left
👉|apontar direita|right
👆|apontar acima|up
👇|apontar abaixo|down
☝️|atenção|point up
👍|positivo|thumbs up like
👎|negativo|thumbs down dislike
✊|punho|fist
👊|soquinho|fist bump
👏|palmas|clap
🙌|celebração|raise hands
👐|mãos abertas|open hands
🤲|mãos em concha|palms up
🙏|agradecimento oração|pray thanks
🤝|aperto de mãos|handshake
💪|força|strong
🫶|mãos coração|heart hands
👀|olhos|eyes
🧠|cérebro|brain
👩|mulher|woman
👨|homem|man
👶|bebê|baby
👩‍💻|programadora|woman coder
👨‍💻|programador|man coder
👩‍⚕️|profissional de saúde|doctor nurse
👨‍⚕️|médico|doctor
"""),
    ("Animais", "🐶", """
🐶|cachorro|dog
🐱|gato|cat
🐭|rato|mouse
🐹|hamster|hamster
🐰|coelho|rabbit
🦊|raposa|fox
🐻|urso|bear
🐼|panda|panda
🐨|coala|koala
🐯|tigre|tiger
🦁|leão|lion
🐮|vaca|cow
🐷|porco|pig
🐸|sapo|frog
🐵|macaco|monkey
🐔|galinha|chicken
🐧|pinguim|penguin
🐦|pássaro|bird
🦉|coruja|owl
🦋|borboleta|butterfly
🐝|abelha|bee
🐢|tartaruga|turtle
🐍|cobra|snake
🐙|polvo|octopus
🐬|golfinho|dolphin
🐳|baleia|whale
🦈|tubarão|shark
🐟|peixe|fish
🐘|elefante|elephant
🦒|girafa|giraffe
🐴|cavalo|horse
🐕|cão|dog
🐈|felino|cat
🐾|pegadas|paw prints
🌷|tulipa|tulip
🌻|girassol|sunflower
🌹|rosa|rose
🌺|flor|flower
🌳|árvore|tree
🍀|trevo|clover
"""),
    ("Comidas", "🍎", """
🍎|maçã|apple
🍌|banana|banana
🍊|laranja|orange
🍋|limão|lemon
🍉|melancia|watermelon
🍇|uvas|grapes
🍓|morango|strawberry
🍒|cereja|cherry
🍍|abacaxi|pineapple
🥝|kiwi|kiwi
🥑|abacate|avocado
🥦|brócolis|broccoli
🥕|cenoura|carrot
🌽|milho|corn
🍞|pão|bread
🧀|queijo|cheese
🥚|ovo|egg
🍔|hambúrguer|burger
🍟|batata frita|fries
🍕|pizza|pizza
🌭|cachorro quente|hot dog
🌮|taco|taco
🍝|macarrão|pasta
🍣|sushi|sushi
🍱|marmita|bento
🍜|lamen|ramen noodles
🍩|rosquinha|donut
🍪|biscoito|cookie
🎂|bolo aniversário|birthday cake
🍰|fatia de bolo|cake
🍫|chocolate|chocolate
🍬|doce|candy
🍦|sorvete|ice cream
☕|café|coffee
🍵|chá|tea
🥤|refrigerante|drink
🍺|cerveja|beer
🍷|vinho|wine
"""),
    ("Atividades", "⚽", """
⚽|futebol|soccer football
🏀|basquete|basketball
🏈|futebol americano|football
⚾|beisebol|baseball
🎾|tênis|tennis
🏐|vôlei|volleyball
🏓|pingue pongue|table tennis
🏸|badminton|badminton
🥊|boxe|boxing
🏋️|academia|weightlifting
🚴|bicicleta|cycling
🏃|corrida|running
🏊|natação|swimming
🎮|videogame|gamepad
🎲|dado|dice
🎯|alvo|target
🎨|pintura|art
🎭|teatro|theater
🎵|música|music note
🎶|notas musicais|music
🎸|guitarra|guitar
🎹|piano|piano
🥁|bateria|drum
🎤|microfone|microphone
🎧|fone de ouvido|headphones
🎬|cinema|movie
📷|câmera|camera
🎁|presente|gift
🎉|confete|party
🎊|celebração|celebration
🏆|troféu|trophy
🥇|medalha ouro|gold
"""),
    ("Viagens", "🚗", """
🚗|carro|car
🚕|táxi|taxi
🚌|ônibus|bus
🚎|transporte público|trolleybus
🚓|polícia|police
🚑|ambulância|ambulance
🚒|bombeiros|fire
🚚|caminhão|truck
🏍️|motocicleta|motorcycle
🚲|bicicleta|bike
✈️|avião|airplane
🚀|foguete|rocket
🚁|helicóptero|helicopter
🚆|trem|train
🚇|metrô|metro
🚢|navio|ship
⛵|veleiro|sailboat
🛵|moto|scooter
🏠|casa|house
🏡|lar|home
🏢|escritório|office
🏥|hospital|hospital
🏫|escola|school
🏖️|praia|beach
⛰️|montanha|mountain
🌋|vulcão|volcano
🌅|nascer do sol|sunrise
🌇|pôr do sol|sunset
🌃|cidade à noite|night city
🌎|planeta terra|earth
🌙|lua|moon
☀️|sol|sun
⭐|estrela|star
🌈|arco íris|rainbow
🔥|fogo|fire
❄️|neve|snow
☁️|nuvem|cloud
🌧️|chuva|rain
"""),
    ("Objetos", "💡", """
💡|ideia lâmpada|idea lightbulb
📱|celular|mobile phone
💻|notebook|laptop
🖥️|computador|desktop computer
⌨️|teclado|keyboard
🖱️|mouse|mouse
🖨️|impressora|printer
📞|telefone|phone
📧|email|mail
✉️|carta|letter
📩|mensagem|message
📎|clipe|paperclip
📁|pasta|folder
📂|pasta aberta|open folder
📄|documento|page
📋|prancheta|clipboard
📝|anotação|memo
📚|livros|books
📖|livro|book
📅|calendário|calendar
📆|agenda|date
🕒|relógio|clock
⏰|despertador|alarm
🔔|sino|bell
🔕|silencioso|silent
🔒|cadeado fechado|lock
🔓|cadeado aberto|unlock
🔑|chave|key
🔍|lupa|search
⚙️|engrenagem|settings
🛠️|ferramentas|tools
🔧|chave inglesa|wrench
💰|dinheiro|money
💳|cartão|credit card
🛒|carrinho de compras|cart
🧾|recibo|receipt
🧪|experimento|lab
💊|remédio|medicine
📌|alfinete|pin
"""),
    ("Símbolos", "❤️", """
❤️|coração vermelho|red heart love
🧡|coração laranja|orange heart
💛|coração amarelo|yellow heart
💚|coração verde|green heart
💙|coração azul|blue heart
💜|coração roxo|purple heart
🖤|coração preto|black heart
🤍|coração branco|white heart
💖|coração brilhante|sparkling heart
💔|coração partido|broken heart
💯|cem pontos|hundred
✅|concluído correto|check done
☑️|caixa marcada|checkbox
✔️|marca de verificação|check mark
❌|erro|error cross
❎|xis|cross
⚠️|atenção aviso|warning
🚫|proibido|forbidden
⛔|entrada proibida|no entry
❓|pergunta|question
❗|exclamação|exclamation
‼️|atenção dupla|exclamation
💬|conversa|speech
💭|pensamento|thought
🔴|círculo vermelho|red circle
🟠|círculo laranja|orange circle
🟡|círculo amarelo|yellow circle
🟢|círculo verde|green circle
🔵|círculo azul|blue circle
🟣|círculo roxo|purple circle
🟤|círculo marrom|brown circle
⚪|círculo branco|white circle
⚫|círculo preto|black circle
➡️|seta direita|right arrow
⬅️|seta esquerda|left arrow
⬆️|seta acima|up arrow
⬇️|seta abaixo|down arrow
🔄|atualizar|refresh
➕|mais|plus
➖|menos|minus
➗|dividir|divide
✖️|multiplicar|multiply
♻️|reciclagem|recycle
✨|brilho|sparkles
⚡|raio|lightning
🎗️|laço|ribbon
"""),
)


def _normal(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def emoji_categories():
    return tuple((name, symbol, tuple(
        (emoji, description, _normal(description + " " + synonyms))
        for line in listing.strip().splitlines()
        for emoji, description, synonyms in (line.split("|", 2),)
    )) for name, symbol, listing in _DATA)


CATEGORIES = emoji_categories()
RECENT: list[str] = []
DEFAULT_RECENT = ("🙂", "👍", "❤️", "😂", "😊", "😍", "🎉", "✅",
                  "🙏", "🥰", "😎", "🔥", "⚡", "💡", "👏", "👋")
MAX_RECENT = 40


class EmojiPicker(QFrame):
    """Popup ancorado ao botão; busca PT/EN e inserção preservando o cursor."""

    def __init__(self, editor, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("emojiPicker")
        self.setFixedWidth(350)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.editor = editor
        self._saved_cursor = QTextCursor(editor.textCursor())
        self.category = "Recentes"
        self.visible_emojis: list[str] = []
        self.category_buttons: dict[str, QToolButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)

        self.tabs = QHBoxLayout()
        self.tabs.setSpacing(2)
        all_categories = (("Recentes", "🕘"),) + tuple(
            (name, symbol) for name, symbol, _ in CATEGORIES)
        for name, symbol in all_categories:
            button = QToolButton(self)
            button.setObjectName("emojiCategory")
            button.setIcon(emoji_icon(symbol))
            button.setIconSize(QSize(25,25))
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.setFixedSize(33, 32)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _, selected=name: self.set_category(selected))
            self.tabs.addWidget(button)
            self.category_buttons[name] = button

        self.search = QLineEdit(self)
        self.search.setObjectName("emojiSearch")
        self.search.setPlaceholderText("Buscar emoji...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.insert_first)
        layout.addWidget(self.search)

        self.heading = QLabel("Usados recentemente", self)
        self.heading.setObjectName("emojiHeading")
        layout.addWidget(self.heading)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("emojiScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(257)
        self.content = QWidget(self.scroll)
        self.content.setObjectName('emojiGrid')
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(1, 1, 1, 1)
        self.grid.setHorizontalSpacing(2)
        self.grid.setVerticalSpacing(2)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        layout.addLayout(self.tabs)
        self.set_category("Recentes")
        self._apply_style()

    def _apply_style(self):
        light = current_theme() == "light"
        background = "#ffffff" if light else "#14263c"
        field = "#f4f8fc" if light else "#102137"
        foreground = "#16324f" if light else "#eaf4ff"
        muted = "#4f6b86" if light else "#a8bfd2"
        border = "#cbdce9" if light else "#34536b"
        hover = "#e5f3f7" if light else "#284b62"
        selected = "#d9f3f0" if light else "#20536a"
        self.setStyleSheet(f"""
            QFrame#emojiPicker {{
                background: {background}; color: {foreground};
                border: 1px solid {border}; border-radius: 12px;
            }}
            QLineEdit#emojiSearch {{
                color: {foreground}; background: {field};
                border: 1px solid {border}; border-radius: 7px;
                padding: 6px 9px; min-height: 26px;
            }}
            QLineEdit#emojiSearch:focus {{ border-color: #24b7c2; }}
            QLabel#emojiHeading {{ color: {muted}; font-weight: 600; }}
            QScrollArea#emojiScroll {{ border: none; background: {background}; }}
            QWidget#emojiGrid {{ background: {background}; }}
            QToolButton#emojiCategory, QToolButton#emojiItem {{
                border: none; border-radius: 6px; background: transparent;
                color: {foreground}; padding: 0px;
            }}
            QToolButton#emojiCategory:hover, QToolButton#emojiItem:hover {{
                background: {hover};
            }}
            QToolButton#emojiCategory:checked {{ background: {selected}; }}
        """)

    def set_category(self, category: str):
        if category not in self.category_buttons:
            return
        self.category = category
        self.category_buttons[category].setChecked(True)
        if self.search.text():
            self.search.clear()
        else:
            self.refresh()

    def _entries(self):
        term = _normal(self.search.text().strip())
        if term:
            return [(emoji, title) for _, _, entries in CATEGORIES
                    for emoji, title, searchable in entries
                    if term in searchable]
        if self.category == "Recentes":
            recent = RECENT or list(DEFAULT_RECENT)
            labels = {emoji: title for _, _, entries in CATEGORIES
                      for emoji, title, _ in entries}
            return [(emoji, labels.get(emoji, "Emoji")) for emoji in recent]
        for name, _, entries in CATEGORIES:
            if name == self.category:
                return [(emoji, title) for emoji, title, _ in entries]
        return []

    def refresh(self, *_):
        while self.grid.count():
            item = self.grid.takeAt(0)
            child = item.widget()
            if child:
                child.hide()
                child.deleteLater()
        query = self.search.text().strip()
        self.heading.setText("Resultados da busca" if query else
                             "Usados recentemente" if self.category == "Recentes" else self.category)
        entries = self._entries()
        self.visible_emojis = [emoji for emoji, _ in entries]
        if not entries:
            message = QLabel("Nenhum emoji encontrado.", self.content)
            message.setObjectName("emojiHeading")
            self.grid.addWidget(message, 0, 0, 1, 8)
        else:
            for index, (emoji, label) in enumerate(entries):
                button = QToolButton(self.content)
                button.setObjectName("emojiItem")
                button.setIcon(emoji_icon(emoji))
                button.setIconSize(QSize(30,30))
                button.setToolTip(label)
                button.setAccessibleName(label)
                button.setFixedSize(38, 36)
                button.setFocusPolicy(Qt.NoFocus)
                button.clicked.connect(lambda _, chosen=emoji: self.insert_emoji(chosen))
                self.grid.addWidget(button, index // 8, index % 8)
        self.scroll.verticalScrollBar().setValue(0)

    def insert_first(self):
        if self.visible_emojis:
            self.insert_emoji(self.visible_emojis[0])

    def insert_emoji(self, emoji: str):
        if not emoji or emoji not in {item for _, _, entries in CATEGORIES
                                     for item, _, _ in entries}:
            return
        # Reutiliza o cursor capturado ANTES do popup roubar o foco.
        cursor = QTextCursor(self._saved_cursor)
        cursor.beginEditBlock()
        cursor.insertText(emoji)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        if emoji in RECENT:
            RECENT.remove(emoji)
        RECENT.insert(0, emoji)
        del RECENT[MAX_RECENT:]
        self.close()
        self.editor.setFocus(Qt.OtherFocusReason)

    def show_at(self, button):
        self._saved_cursor = QTextCursor(self.editor.textCursor())
        self._apply_style()
        self.search.clear()
        self.set_category("Recentes")
        self.adjustSize()
        anchor = button.mapToGlobal(QPoint(0, button.height() + 4))
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is not None:
            rect = screen.availableGeometry()
            x = min(max(anchor.x(), rect.left()), max(rect.left(), rect.right() - self.width()))
            y = anchor.y()
            if y + self.sizeHint().height() > rect.bottom():
                y = button.mapToGlobal(QPoint(0, 0)).y() - self.sizeHint().height() - 4
            anchor = QPoint(x, max(rect.top(), y))
        self.move(anchor)
        self.show()
        self.search.setFocus(Qt.PopupFocusReason)
