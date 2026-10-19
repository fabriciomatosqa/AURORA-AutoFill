"""Interface do AURORA AutoFill v0.5.2 (PySide6)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QMimeData, QTimer, Signal, QPoint, QRectF
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QIcon, QKeySequence, QPalette,
                           QShortcut, QTextCharFormat, QPainter, QPainterPath, QLinearGradient, QPen, QPixmap)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QStackedWidget, QSystemTrayIcon,
    QTextEdit, QStatusBar, QToolButton, QVBoxLayout, QWidget,
)

from .core import Snippet, SnippetStore, application_db_path, render_snippet
from .hotkeys import GlobalHotkeyListener, type_backspace_and_paste
from .formatting import has_rich_formatting, render_rich_html


STYLESHEET = """
/* AURORA 0.5.2 — acabamento visual da identidade Aurora */
QWidget { font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; }
QMainWindow, QWidget#body, QWidget#rightPane, QWidget#editorPage, QWidget#welcomePage {
  background-color: #091426; color: #eaf4ff; }
QWidget#topbar { background-color: #06152b; }
QLabel { background: transparent; color: #eaf4ff; }
QLabel#brandPrimary { font-size: 30px; font-weight: 820; letter-spacing: 4px; color: #f7fbff; }
QLabel#brandAccent { font-size: 30px; font-weight: 760; color: #79ead8; }
QLabel#topCaption { color: #d2eafa; font-size: 11px; font-weight: 600; }
QWidget#sidebar { background: #0f1d31; border-right: 1px solid #24445f; }
QLabel#sectionTitle { color: #91e1d6; font-size: 12px; font-weight: 750; letter-spacing: .6px; }
QLabel#heading { color: #f3f9ff; font-size: 24px; font-weight: 760; }
QLabel#subheading { color: #b8cde0; font-size: 13px; }
QLabel#hint { color: #a8bfd2; font-size: 12px; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
  border: 1px solid #35506b; border-radius: 10px; background: #152941;
  color: #f5faff; padding: 8px 10px;
  selection-background-color: #257d80; selection-color: #ffffff; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
  border: 1.5px solid #67e7d5; }
QComboBox { min-height: 24px; padding-right: 28px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right;
  width: 26px; border-left: 0px solid transparent; background: transparent;
  border-top-right-radius: 9px; border-bottom-right-radius: 9px; }
QComboBox#folderPicker {
  border: 1px solid #2f7077; border-radius: 10px; background: #143345;
  color: #f0feff; padding: 7px 12px; }
QComboBox#folderPicker:hover { border-color: #59dfcf; background: #184156; }
QComboBox#folderPicker::drop-down { width: 28px; background: #1b495c; border-left: 1px solid #28586d; }
QComboBox QAbstractItemView {
  background-color: #11263c; color: #eaf7ff; border: 1px solid #3a6270;
  border-radius: 7px; outline: 0; padding: 5px;
  selection-background-color: #226878; selection-color: #ffffff; }
QComboBox QAbstractItemView::item { color: #eaf7ff; min-height: 30px; padding: 5px 8px; }
QComboBox QAbstractItemView::item:selected { color: #fff; background: #226878; }
QMenu { background-color: #11263c; color: #eaf7ff; border: 1px solid #416777; padding: 5px; }
QMenu::item { color: #eaf7ff; background: transparent; padding: 9px 17px; }
QMenu::item:selected { color: #ffffff; background: #226878; }
QMenu::separator { background: #355168; height: 1px; margin: 4px 8px; }
QListWidget { background-color: #10243a; color: #effaff; border: 1px solid #2b405a;
  border-radius: 12px; outline: 0; padding: 5px; }
QListWidget::item { color: #e7f6ff; padding: 12px 10px; border-radius: 8px; margin: 2px; }
QListWidget::item:selected { background: #2c6d7a; color: #fff; border-left: 4px solid #65e7d1; }
QListWidget::item:hover:!selected { background: #203b55; color: #fff; }
QPushButton, QToolButton {
  border-radius: 8px; padding: 9px 12px; border: 1px solid #38536b;
  background: #1b3149; color: #f0fbff; font-weight: 620; }
QPushButton:hover, QToolButton:hover { background: #294a62; border-color: #6adacc; }
QPushButton:checked { background: #255b63; border-color: #68e3d0; color: #fff; }
QPushButton#primary { background: #49d0ba; color: #09283b; border: 1px solid #49d0ba; font-weight: 760; }
QPushButton#primary:hover { background: #8af2d9; }
QPushButton#danger { color: #ffbecf; border-color: #805064; }
QPushButton#danger:hover { background: #552d47; }
QPushButton#headerButton { color: #f1fffd; border: 1px solid #69d5c8; background: rgba(11,44,61,0.82); }
QPushButton#headerButton:hover { background: rgba(20,80,90,0.95); }
QStatusBar { background: #0c1b30; color: #8cf1d7; border-top: 1px solid #28435e; }
QLabel#developerCredit { background: transparent; color: #8cacc0; font-size: 11px; padding: 0px 11px; }
QSplitter::handle { background: #243c55; width: 2px; }
QScrollArea { border: 0; background: #091426; }
QScrollBar:vertical { background: #0e2335; width: 9px; margin: 1px; border: none; }
QScrollBar::handle:vertical { background: #46667c; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #60aeb3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #0e2335; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #46667c; border-radius: 4px; }
QMessageBox, QInputDialog, QFileDialog { background: #132338; color: #eaf5ff; }
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel { color: #eaf5ff; background: transparent; }
QMessageBox QPushButton, QInputDialog QPushButton, QFileDialog QPushButton { color: #eaf5ff; background: #1c334a; }
QToolTip { background: #17354c; color: #fff; border: 1px solid #4eb9b2; }
"""


class HotkeySignals(QObject):
    triggered = Signal(str)


class AuroraBanner(QWidget):
    """Desenha o panorama no topo sem deformar sua proporção original.

    Usa a região central do cenário para destacar aurora, picos e reflexos.
    O recorte se adapta ao tamanho da janela mantendo pixels proporcionais.
    """

    def __init__(self, picture: Path, parent=None):
        super().__init__(parent)
        self._image = QPixmap(str(picture))
        self.setObjectName("topbar")

    @staticmethod
    def source_crop(source_width: int, source_height: int, view_width: int, view_height: int):
        if not source_width or not source_height or not view_width or not view_height:
            return QRectF()
        src_ratio = source_width / source_height
        dst_ratio = view_width / view_height
        if src_ratio < dst_ratio:
            # Para cobrir uma janela longa, recorta o centro vertical da arte.
            crop_height = source_width / dst_ratio
            y = max(0, min(source_height - crop_height, source_height * 0.56 - crop_height * .5))
            return QRectF(0, y, source_width, crop_height)
        crop_width = source_height * dst_ratio
        return QRectF((source_width - crop_width) / 2, 0, crop_width, source_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if not self._image.isNull():
            rect = self.source_crop(self._image.width(), self._image.height(), self.width(), self.height())
            painter.drawPixmap(QRectF(self.rect()), self._image, rect)
        else:
            painter.fillRect(self.rect(), QColor("#06152b"))
        # Gradiente sob a marca e sob o botão; não modifica os pixels da arte.
        left = QLinearGradient(0, 0, self.width() * .56, 0)
        left.setColorAt(0, QColor(2, 11, 29, 220))
        left.setColorAt(.57, QColor(3, 17, 38, 120))
        left.setColorAt(1, QColor(4, 18, 36, 0))
        painter.fillRect(self.rect(), left)
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QColor(2, 8, 28, 90))
        shade.setColorAt(.65, QColor(3, 11, 29, 0))
        shade.setColorAt(1, QColor(2, 9, 25, 95))
        painter.fillRect(self.rect(), shade)
        painter.end()


class AuroraWordmark(QWidget):
    """Assinatura tipográfica geométrica, com letras vetoriais, sem PNG borrado.

    Bahnschrift é uma família moderna presente no Windows 10/11; há fontes
    alternativas para Linux, mantendo os efeitos vetoriais da marca.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(470, 60)
        self.setMaximumHeight(60)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        super().paintEvent(event)
        from PySide6.QtGui import QFontDatabase
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        installed = set(QFontDatabase.families())
        family = next((name for name in (
            "Bahnschrift", "Bahnschrift SemiCondensed", "Segoe UI Variable Display",
            "Montserrat", "DejaVu Sans") if name in installed), "Sans Serif")

        base = QFont(family)
        base.setPixelSize(35)
        base.setWeight(QFont.Bold)
        base.setLetterSpacing(QFont.AbsoluteSpacing, 4.1)
        base.setKerning(True)
        baseline = 40
        brand = QPainterPath()
        brand.addText(0, baseline, base, "AURORA")
        # Halo sutil, sem perder a definição das formas.
        painter.setPen(QPen(QColor(63, 246, 220, 35), 2.2))
        painter.drawPath(brand)
        white = QLinearGradient(0, 5, 0, 43)
        white.setColorAt(0, QColor("#ffffff"))
        white.setColorAt(1, QColor("#d7e8ff"))
        painter.fillPath(brand, white)

        spacing = QFontMetricsF(base).horizontalAdvance("AURORA") + 18
        accent = QFont(family)
        accent.setPixelSize(31)
        accent.setWeight(QFont.DemiBold)
        accent.setLetterSpacing(QFont.AbsoluteSpacing, 1.35)
        accent_path = QPainterPath()
        accent_path.addText(spacing, baseline, accent, "AutoFill")
        color = QLinearGradient(spacing, 0, spacing + 155, 0)
        color.setColorAt(0, QColor("#8bfbeb"))
        color.setColorAt(.55, QColor("#55e0e0"))
        color.setColorAt(1, QColor("#99acff"))
        painter.fillPath(accent_path, color)

        # Traço de marca, inspirado na linha de luz da aurora.
        bar = QLinearGradient(0, 0, 410, 0)
        bar.setColorAt(0, QColor("#39cfcb"))
        bar.setColorAt(.50, QColor("#80edd4"))
        bar.setColorAt(1, QColor(102, 160, 255, 0))
        painter.fillRect(QRectF(1, 49, min(self.width() - 8, 398), 2), bar)
        painter.end()


class AuroraFolderCombo(QComboBox):
    """Exibe as pastas usando menu Qt próprio, evitando bordas nativas acinzentadas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_menu = None

    def showPopup(self):
        menu = QMenu(self)
        menu.setObjectName("folderSelectionMenu")
        menu.setMinimumWidth(max(self.width(), 210))
        menu.setStyleSheet("""
            QMenu#folderSelectionMenu {
                background-color: #112f41;
                color: #ebfaff;
                border: 1px solid #2f8590;
                border-radius: 9px;
                padding: 6px;
                font-size: 13px;
            }
            QMenu#folderSelectionMenu::item {
                background: #112f41;
                color: #e5f7ff;
                padding: 10px 16px;
                margin: 2px 3px;
                border-radius: 7px;
            }
            QMenu#folderSelectionMenu::item:selected {
                background: #287281;
                color: white;
            }
            QMenu#folderSelectionMenu::item:checked {
                color: #7df0d9;
            }
            QMenu#folderSelectionMenu::indicator {
                width: 0px; height: 0px;
            }
        """)
        for i in range(self.count()):
            action = menu.addAction(self.itemText(i))
            action.setCheckable(True)
            action.setChecked(i == self.currentIndex())
            action.triggered.connect(lambda checked=False, index=i: self.setCurrentIndex(index))
        menu.aboutToHide.connect(menu.deleteLater)
        self._folder_menu = menu
        pos = self.mapToGlobal(QPoint(0, self.height() + 3))
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            menu_height = menu.sizeHint().height()
            if pos.y() + menu_height > available.bottom():
                pos.setY(max(available.top(), self.mapToGlobal(QPoint(0, 0)).y() - menu_height - 3))
        menu.popup(pos)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#8ef7de"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 16
        y = self.height() // 2 - 1
        painter.drawLine(x - 5, y - 2, x, y + 3)
        painter.drawLine(x, y + 3, x + 5, y - 2)
        painter.end()


class AutoFillWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = SnippetStore(application_db_path())
        self.store.seed_if_empty()
        self.current_id: int | None = None
        self.dirty = False
        self._loading = False
        self._clipboard_pending = False
        self._hotkeys_enabled = True
        self._clipboard_clone: QMimeData | None = None
        self._clipboard_written = ""
        self.setWindowTitle("AURORA AutoFill v0.5.2 — Expansor de textos")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets" / "aurora_icon.png")))
        # Impede a compactação horizontal desordenada dos campos; em telas de
        # pouca altura o editor usa rolagem própria, sem sobrepor controles.
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen is not None else None
        min_height = min(740, max(620, (available.height() - 32) if available else 740))
        self.setMinimumSize(1060, min_height)
        target_w = min(1320, available.width() - 24) if available else 1320
        target_h = min(900, available.height() - 24) if available else 900
        self.resize(max(1060, target_w), max(min_height, target_h))
        self.setStyleSheet(STYLESHEET)
        self._quitting = False
        self._first_tray_hide = True
        self.tray_icon = None
        self.tray_open_action = None
        self.tray_toggle_action = None
        self.tray_exit_action = None
        self._build_ui()
        self._setup_tray()
        self.signals = HotkeySignals()
        self.signals.triggered.connect(self._expand_global)
        self.hotkeys = GlobalHotkeyListener(self.signals.triggered.emit)
        self._update_listener_shortcuts()
        started, message = self.hotkeys.start()
        self._hotkeys_enabled = started
        self.listen_button.setText("● Atalhos ativos" if started else "○ Atalhos indisponíveis")
        self.listen_button.setEnabled(started)
        self.listen_button.setToolTip("Ativar/desativar expansão em outros programas")
        self.statusBar().showMessage(message)
        self._refresh_all()
        self._show_welcome()

    def _play_confirmation(self):
        """Reproduz o clique original de forma assíncrona, sem bloquear a GUI.

        Não utiliza QtMultimedia: ambientes Linux sem PipeWire podem travar
        ao inicializar o módulo de áudio; Windows usa winsound nativo.
        """
        import sys
        import shutil
        import subprocess
        path = str(Path(__file__).resolve().parent.parent / "assets" / "command_click.wav")
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            for player in ("paplay", "pw-play", "aplay"):
                binary = shutil.which(player)
                if binary:
                    subprocess.Popen([binary, path], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                    return
            QApplication.beep()
        except Exception:
            try:
                QApplication.beep()
            except Exception:
                pass

    def _build_ui(self):
        outer = QWidget()
        outer.setObjectName("body")
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(outer)

        # O cenário é uma versão tratada da arte Aurora Utils aprovada.
        # A composição evita reproduzir a interface ou o texto "Utils".
        assets = Path(__file__).resolve().parent.parent / "assets"
        top = AuroraBanner(assets / "aurora_banner.jpg")
        top.setFixedHeight(168)
        h = QHBoxLayout(top)
        h.setContentsMargins(28, 16, 26, 16)
        h.setSpacing(14)
        brand_mark = QLabel()
        brand_mark.setPixmap(QIcon(str(assets / "aurora_icon.png")).pixmap(82, 82))
        brand_mark.setFixedSize(82, 82)
        h.addWidget(brand_mark)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(2)
        brand_box.setContentsMargins(0, 0, 0, 0)
        wordmark = AuroraWordmark()
        wordmark.setFixedWidth(485)
        brand_box.addWidget(wordmark)
        caption = QLabel("EXPANSÃO INTELIGENTE DE TEXTOS  ·  MAIS TEMPO PARA VOCÊ")
        caption.setObjectName("topCaption")
        cap_font = QFont("Segoe UI", 9)
        cap_font.setWeight(QFont.Medium)
        cap_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.25)
        caption.setFont(cap_font)
        brand_box.addWidget(caption)
        h.addLayout(brand_box)
        h.addStretch(1)
        self.listen_button = QPushButton("● Atalhos ativos")
        self.listen_button.setObjectName("headerButton")
        self.listen_button.setMinimumWidth(162)
        self.listen_button.clicked.connect(self._toggle_listener)
        h.addWidget(self.listen_button)
        layout.addWidget(top)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(265)
        s = QVBoxLayout(sidebar)
        s.setContentsMargins(17, 18, 17, 18)
        s.setSpacing(12)
        sidebar_head = QHBoxLayout()
        title = QLabel("MEUS COMANDOS")
        title.setObjectName("sectionTitle")
        sidebar_head.addWidget(title)
        sidebar_head.addStretch()
        new_btn = QPushButton("+ Novo")
        new_btn.setObjectName("primary")
        new_btn.setToolTip("Criar novo comando")
        new_btn.clicked.connect(self._new_snippet)
        sidebar_head.addWidget(new_btn)
        s.addLayout(sidebar_head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar comandos ou atalhos...")
        self.search.textChanged.connect(self._refresh_list)
        s.addWidget(self.search)
        folder_row = QHBoxLayout()
        self.filter_folder = AuroraFolderCombo()
        self.filter_folder.setObjectName("folderPicker")
        self.filter_folder.setMinimumHeight(38)
        self.filter_folder.setMinimumContentsLength(20)
        self.filter_folder.currentIndexChanged.connect(self._refresh_list)
        folder_row.addWidget(self.filter_folder, 1)
        add_folder = QPushButton("+")
        add_folder.setFixedWidth(36)
        add_folder.setToolTip("Criar pasta")
        add_folder.clicked.connect(self._add_folder)
        folder_row.addWidget(add_folder)
        s.addLayout(folder_row)
        self.snippet_list = QListWidget()
        self.snippet_list.setSpacing(1)
        self.snippet_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.snippet_list.setTextElideMode(Qt.ElideRight)
        self.snippet_list.currentItemChanged.connect(self._choose_snippet)
        s.addWidget(self.snippet_list, 1)
        backup = QHBoxLayout()
        export = QPushButton("↑ Exportar")
        export.clicked.connect(self._export)
        imported = QPushButton("↓ Importar")
        imported.clicked.connect(self._import)
        backup.addWidget(export)
        backup.addWidget(imported)
        s.addLayout(backup)
        splitter.addWidget(sidebar)

        right = QWidget()
        right.setObjectName("rightPane")
        self.right_layout = QVBoxLayout(right)
        self.right_layout.setContentsMargins(26, 21, 26, 17)
        self.right_layout.setSpacing(10)
        self.stack = QStackedWidget()
        self.right_layout.addWidget(self.stack)
        self._build_welcome_page()
        self._build_editor_page()
        splitter.addWidget(right)
        splitter.setSizes([302, 990])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(False)
        author = QLabel("Desenvolvido por Fabricio Matos  •  2026")
        author.setObjectName("developerCredit")
        self.statusBar().addPermanentWidget(author)

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._new_snippet)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("AURORA AutoFill")
        menu = QMenu(self)
        self.tray_open_action = QAction("Abrir AURORA AutoFill", self)
        self.tray_open_action.triggered.connect(self._restore_from_tray)
        menu.addAction(self.tray_open_action)
        self.tray_toggle_action = QAction("Pausar atalhos", self)
        self.tray_toggle_action.triggered.connect(self._toggle_listener)
        menu.addAction(self.tray_toggle_action)
        menu.addSeparator()
        self.tray_exit_action = QAction("Encerrar", self)
        self.tray_exit_action.triggered.connect(self._exit_application)
        menu.addAction(self.tray_exit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray_icon = tray

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._restore_from_tray()

    def _hide_to_tray(self):
        self.hide()
        if self.tray_icon:
            self.tray_icon.show()
            if self._first_tray_hide:
                self.tray_icon.showMessage(
                    "AURORA AutoFill",
                    "O programa continua ativo perto do relógio e os atalhos seguem funcionando.",
                    QSystemTrayIcon.Information,
                    3500,
                )
                self._first_tray_hide = False
        self.statusBar().showMessage("AURORA AutoFill minimizado para a bandeja do sistema.", 5000)

    def _restore_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _exit_application(self):
        self._quitting = True
        self.close()
        if self._quitting:
            QApplication.instance().quit()

    def _build_welcome_page(self):
        page = QWidget()
        page.setObjectName("welcomePage")
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 16, 4, 16)
        v.setSpacing(16)
        header = QLabel("Seus textos, na velocidade da aurora")
        header.setObjectName("heading")
        header.setWordWrap(True)
        v.addWidget(header)
        intro = QLabel("Organize seus atalhos em pastas e expanda textos em outros aplicativos. Sem conta, sem assinatura e com seus dados no computador.")
        intro.setWordWrap(True)
        intro.setObjectName("subheading")
        v.addWidget(intro)
        sample_label = QLabel("TESTE SEUS ATALHOS")
        sample_label.setObjectName("sectionTitle")
        v.addWidget(sample_label)
        sample_help = QLabel("Clique abaixo e digite /ola, /agora ou /chamado. O comando será substituído pelo texto cadastrado se a detecção global estiver ativa.")
        sample_help.setWordWrap(True)
        v.addWidget(sample_help)
        self.test_box = QPlainTextEdit()
        self.test_box.setPlaceholderText("Digite seus atalhos aqui para experimentar...")
        self.test_box.setMinimumHeight(150)
        self.test_box.setMaximumHeight(200)
        v.addWidget(self.test_box)
        tip = QLabel("💡 Variáveis disponíveis: {{data}}, {{hora}}, {{data_hora}}, {{clipboard}}, {{cursor}}")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        v.addWidget(tip)
        buttons = QHBoxLayout()
        buttons.addStretch()
        create = QPushButton("+ Criar meu primeiro comando")
        create.setObjectName("primary")
        create.clicked.connect(self._new_snippet)
        buttons.addWidget(create)
        v.addLayout(buttons)
        v.addStretch()
        self.stack.addWidget(page)

    def _build_editor_page(self):
        page = QWidget()
        page.setObjectName("editorPage")
        # A área editável preserva seu tamanho natural; a QScrollArea assume
        # a rolagem somente quando a altura da janela não é suficiente.
        page.setMinimumHeight(680)
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 8, 8)
        v.setSpacing(11)
        header = QHBoxLayout()
        self.edit_heading = QLabel("Novo comando")
        self.edit_heading.setObjectName("heading")
        header.addWidget(self.edit_heading, 1)
        home_btn = QPushButton("⌂ Início")
        home_btn.clicked.connect(self._show_welcome)
        header.addWidget(home_btn)
        v.addLayout(header)
        sub = QLabel("Configure um atalho e o texto que aparecerá quando você digitá-lo.")
        sub.setObjectName("subheading")
        v.addWidget(sub)
        name_label = QLabel("Nome do comando")
        name_label.setObjectName("sectionTitle")
        v.addWidget(name_label)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Ex.: Resposta de chamado")
        v.addWidget(self.title_input)
        fields = QHBoxLayout()
        shortcut_box = QVBoxLayout()
        shortcut_label = QLabel("Atalho")
        shortcut_label.setObjectName("sectionTitle")
        shortcut_box.addWidget(shortcut_label)
        self.shortcut_input = QLineEdit()
        self.shortcut_input.setPlaceholderText("/meuatalho")
        shortcut_box.addWidget(self.shortcut_input)
        fields.addLayout(shortcut_box, 1)
        folder_box = QVBoxLayout()
        folder_label = QLabel("Pasta")
        folder_label.setObjectName("sectionTitle")
        folder_box.addWidget(folder_label)
        self.editor_folder = AuroraFolderCombo()
        self.editor_folder.setObjectName("folderPicker")
        self.editor_folder.setMinimumHeight(38)
        self.editor_folder.setMinimumContentsLength(18)
        folder_box.addWidget(self.editor_folder)
        fields.addLayout(folder_box, 1)
        v.addLayout(fields)
        content_header = QHBoxLayout()
        content_label = QLabel("Texto / modelo")
        content_label.setObjectName("sectionTitle")
        content_header.addWidget(content_label)
        content_header.addStretch()
        v.addLayout(content_header)
        self.body_input = QTextEdit()
        self.body_input.setPlaceholderText("Escreva aqui o conteúdo que será inserido...")
        # Formatação rich-text: salva HTML mas mantém texto simples para apps básicos.
        formatting_row = QHBoxLayout()
        formatting_row.setSpacing(8)
        self.format_buttons = {}
        for title, tip, mode in [("B", "Negrito", "bold"), ("I", "Itálico", "italic"), ("U", "Sublinhado", "underline")]:
            button = QPushButton(title)
            button.setToolTip(tip)
            button.setCheckable(True)
            button.setFixedWidth(40)
            button.clicked.connect(lambda checked, m=mode: self._apply_format(m, checked))
            self.format_buttons[mode] = button
            formatting_row.addWidget(button)
        guide = QLabel("Formatação básica · depende do aplicativo de destino")
        guide.setObjectName("hint")
        formatting_row.addWidget(guide)
        formatting_row.addStretch()
        self.token_button = QToolButton()
        self.token_button.setText("+ Inserir comando dinâmico ▾")
        self.token_button.setPopupMode(QToolButton.InstantPopup)
        self.token_button.setMinimumWidth(238)
        menu = QMenu(self.token_button)
        for label, token in [
            ("Data atual", "{{data}}"), ("Hora atual", "{{hora}}"),
            ("Data e hora", "{{data_hora}}"), ("Área de transferência", "{{clipboard}}"),
            ("Posição do cursor", "{{cursor}}"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, t=token: self.body_input.insertPlainText(t))
            menu.addAction(action)
        self.token_button.setMenu(menu)
        formatting_row.addWidget(self.token_button)
        v.addLayout(formatting_row)
        self.body_input.currentCharFormatChanged.connect(self._sync_format_buttons)
        self.body_input.setMinimumHeight(178)
        v.addWidget(self.body_input, 2)
        preview_label = QLabel("PRÉ-VISUALIZAÇÃO")
        preview_label.setObjectName("sectionTitle")
        v.addWidget(preview_label)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(88)
        self.preview.setMaximumHeight(125)
        self.preview.setPlaceholderText("O resultado do modelo aparecerá aqui.")
        v.addWidget(self.preview, 1)
        tip = QLabel("{{cursor}} posiciona o ponto de digitação. Atalhos: Ctrl+N (novo) e Ctrl+S (salvar).")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        v.addWidget(tip)
        action_row = QHBoxLayout()
        self.delete_button = QPushButton("Excluir")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        action_row.addWidget(self.delete_button)
        action_row.addStretch()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self._show_welcome)
        action_row.addWidget(cancel_button)
        save_button = QPushButton("✓ Salvar comando")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self._save)
        action_row.addWidget(save_button)
        v.addLayout(action_row)
        self.editor_scroll = QScrollArea()
        self.editor_scroll.setObjectName("editorScroll")
        self.editor_scroll.setFrameShape(QFrame.NoFrame)
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_scroll.setWidget(page)
        self.stack.addWidget(self.editor_scroll)
        self.title_input.textChanged.connect(self._mark_dirty)
        self.shortcut_input.textChanged.connect(self._mark_dirty)
        self.body_input.textChanged.connect(self._mark_dirty)
        self.body_input.textChanged.connect(self._update_preview)
        self.editor_folder.currentIndexChanged.connect(self._mark_dirty)

    def _apply_format(self, mode: str, active: bool):
        fmt = QTextCharFormat()
        if mode == "bold":
            fmt.setFontWeight(QFont.Bold if active else QFont.Normal)
        elif mode == "italic":
            fmt.setFontItalic(active)
        else:
            fmt.setFontUnderline(active)
        self.body_input.mergeCurrentCharFormat(fmt)
        self.body_input.setFocus()

    def _sync_format_buttons(self, fmt: QTextCharFormat):
        for key, checked in (("bold", fmt.fontWeight() >= QFont.Bold),
                             ("italic", fmt.fontItalic()), ("underline", fmt.fontUnderline())):
            btn = self.format_buttons[key]
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)

    def _mark_dirty(self, *_):
        if not self._loading:
            self.dirty = True

    def _update_preview(self):
        text = self.body_input.toPlainText()
        result = render_snippet(text, QApplication.clipboard().text())
        self.preview.setPlainText(result.text)

    def _refresh_all(self):
        self._loading = True
        filter_id = self.filter_folder.currentData()
        editor_id = self.editor_folder.currentData()
        self.filter_folder.blockSignals(True)
        self.editor_folder.blockSignals(True)
        self.filter_folder.clear()
        self.filter_folder.addItem("Todas as pastas", None)
        self.editor_folder.clear()
        for folder_id, name in self.store.folders():
            self.filter_folder.addItem(name, folder_id)
            self.editor_folder.addItem(name, folder_id)
        idx = self.filter_folder.findData(filter_id)
        self.filter_folder.setCurrentIndex(max(0, idx))
        idx = self.editor_folder.findData(editor_id)
        self.editor_folder.setCurrentIndex(max(0, idx))
        self.filter_folder.blockSignals(False)
        self.editor_folder.blockSignals(False)
        self._loading = False
        self._refresh_list()

    def _refresh_list(self, *_):
        old_selected = self.current_id
        folder_id = self.filter_folder.currentData()
        snippets = self.store.snippets(folder_id, self.search.text().strip())
        self.snippet_list.blockSignals(True)
        self.snippet_list.clear()
        for snippet in snippets:
            item = QListWidgetItem(f"{snippet.title}  ·  {snippet.shortcut}")
            item.setData(Qt.UserRole, snippet.id)
            item.setToolTip(f"Atalho: {snippet.shortcut}\n{snippet.content[:160]}")
            self.snippet_list.addItem(item)
            if snippet.id == old_selected:
                self.snippet_list.setCurrentItem(item)
        self.snippet_list.blockSignals(False)
        self._update_listener_shortcuts()

    def _update_listener_shortcuts(self):
        if hasattr(self, "hotkeys"):
            snippets = self.store.snippets()
            self.hotkeys.update_shortcuts([s.shortcut for s in snippets])

    def _get_snippet(self, snippet_id: int | None) -> Snippet | None:
        return next((s for s in self.store.snippets() if s.id == snippet_id), None)

    def _confirm_change(self) -> bool:
        if self.stack.currentIndex() != 1 or not self.dirty:
            return True
        choice = QMessageBox.question(
            self, "Alterações não salvas", "Descartar alterações deste comando?",
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        return choice == QMessageBox.Discard

    def _choose_snippet(self, current: QListWidgetItem | None, previous: QListWidgetItem | None):
        if current is None:
            return
        if not self._confirm_change():
            self.snippet_list.blockSignals(True)
            self.snippet_list.setCurrentItem(previous)
            self.snippet_list.blockSignals(False)
            return
        snippet = self._get_snippet(current.data(Qt.UserRole))
        if snippet:
            self._load_editor(snippet)

    def _load_editor(self, snippet: Snippet | None = None):
        self._loading = True
        self.current_id = snippet.id if snippet else None
        self.title_input.setText(snippet.title if snippet else "")
        self.shortcut_input.setText(snippet.shortcut if snippet else "/")
        if snippet and snippet.rich_content:
            self.body_input.setHtml(snippet.rich_content)
        else:
            self.body_input.setPlainText(snippet.content if snippet else "")
        folder_id = snippet.folder_id if snippet else self.filter_folder.currentData()
        idx = self.editor_folder.findData(folder_id)
        self.editor_folder.setCurrentIndex(max(0, idx))
        self.edit_heading.setText("Editar comando" if snippet else "Novo comando")
        self.delete_button.setVisible(snippet is not None)
        self.dirty = False
        self._loading = False
        self.stack.setCurrentIndex(1)
        self.editor_scroll.verticalScrollBar().setValue(0)
        if snippet is None:
            self.title_input.setFocus()
        self._update_preview()

    def _new_snippet(self):
        if not self._confirm_change():
            return
        self.snippet_list.blockSignals(True)
        self.snippet_list.clearSelection()
        self.snippet_list.blockSignals(False)
        self._load_editor()

    def _show_welcome(self):
        if not self._confirm_change():
            return
        self.dirty = False
        self.current_id = None
        self.snippet_list.blockSignals(True)
        self.snippet_list.clearSelection()
        self.snippet_list.blockSignals(False)
        self.stack.setCurrentIndex(0)

    def _save(self):
        if self.stack.currentIndex() != 1:
            return
        try:
            new_id = self.store.save(
                self.editor_folder.currentData(),
                self.title_input.text(), self.shortcut_input.text(),
                self.body_input.toPlainText(), self.current_id,
                rich_content=self.body_input.toHtml())
        except ValueError as error:
            QMessageBox.warning(self, "Não foi possível salvar", str(error))
            return
        self.current_id = new_id
        self.dirty = False
        self._refresh_all()
        self._load_editor(self._get_snippet(new_id))
        self.statusBar().showMessage("Comando salvo com sucesso.", 5000)

    def _delete(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Excluir comando", "Deseja realmente excluir este comando?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.store.delete(self.current_id)
        self.dirty = False
        self.current_id = None
        self._refresh_all()
        self._show_welcome()
        self.statusBar().showMessage("Comando excluído.", 5000)

    def _add_folder(self):
        name, accepted = QInputDialog.getText(self, "Nova pasta", "Nome da pasta:")
        if not accepted:
            return
        try:
            folder_id = self.store.create_folder(name)
        except (ValueError, Exception) as exc:
            QMessageBox.warning(self, "Nova pasta", str(exc))
            return
        self._refresh_all()
        idx = self.filter_folder.findData(folder_id)
        self.filter_folder.setCurrentIndex(idx)
        self.editor_folder.setCurrentIndex(self.editor_folder.findData(folder_id))

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar comandos", "autofill-backup.json", "JSON (*.json)")
        if path:
            try:
                self.store.export_json(path)
                QMessageBox.information(self, "Backup", "Backup exportado com sucesso.")
            except OSError as exc:
                QMessageBox.warning(self, "Erro no backup", str(exc))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar comandos", "", "JSON (*.json)")
        if path:
            try:
                imported, skipped = self.store.import_json(path)
                self._refresh_all()
                QMessageBox.information(self, "Importação concluída",
                                        f"Comandos importados: {imported}\nIgnorados (duplicados ou inválidos): {skipped}")
            except (ValueError, OSError, TypeError) as exc:
                QMessageBox.warning(self, "Erro na importação", str(exc))

    def _toggle_listener(self):
        self._hotkeys_enabled = not self._hotkeys_enabled
        self.hotkeys.set_enabled(self._hotkeys_enabled)
        self.listen_button.setText("● Atalhos ativos" if self._hotkeys_enabled else "○ Atalhos pausados")
        if self.tray_toggle_action is not None:
            self.tray_toggle_action.setText("Pausar atalhos" if self._hotkeys_enabled else "Retomar atalhos")
        self.statusBar().showMessage("Expansão ativa." if self._hotkeys_enabled else "Expansão pausada.", 4000)

    @staticmethod
    def _clone_clipboard_mime() -> QMimeData:
        original = QApplication.clipboard().mimeData()
        clone = QMimeData()
        if original:
            for fmt in original.formats():
                clone.setData(fmt, original.data(fmt))
        return clone

    def _expand_global(self, shortcut: str):
        # O hook reconhece a soltura da última tecla; aguarda o widget de destino
        # terminar o processamento do evento antes de apagar/colar.
        if not self._hotkeys_enabled or self._clipboard_pending:
            return
        if self.isActiveWindow() and self.focusWidget() is not self.test_box:
            return
        self._clipboard_pending = True
        self.hotkeys.set_enabled(False)
        QTimer.singleShot(75, lambda s=shortcut: self._perform_expansion(s))

    def _perform_expansion(self, shortcut: str):
        clipboard = QApplication.clipboard()
        original_mime = None
        restore_later = False
        try:
            snippet = next((s for s in self.store.snippets() if s.shortcut == shortcut), None)
            if not snippet:
                return
            current_text = clipboard.text()
            rendered = render_snippet(snippet.content, current_text)
            if not rendered.text:
                return
            original_mime = self._clone_clipboard_mime()
            payload = QMimeData()
            payload.setText(rendered.text)
            # O Notepad lê CF_UNICODETEXT. HTML é opcional e só aparece quando
            # o modelo foi realmente formatado (Word/Outlook podem aproveitar).
            rich = bool(snippet.rich_content and has_rich_formatting(snippet.rich_content)
                        and "{{cursor}}" not in snippet.content)
            if rich:
                payload.setHtml(render_rich_html(snippet.rich_content, current_text))
            self._clipboard_written = rendered.text
            clipboard.setMimeData(payload)
            restore_later = True
            type_backspace_and_paste(len(shortcut), rendered.left_moves)
            self.statusBar().showMessage(f"Expandido: {shortcut}", 3000)
            self._play_confirmation()
        except Exception as exc:
            self.statusBar().showMessage(f"Não foi possível expandir: {exc}", 8000)
        finally:
            if restore_later and original_mime is not None:
                QTimer.singleShot(1450, lambda mime=original_mime: self._restore_clipboard(mime))
            else:
                self._clipboard_pending = False
                self.hotkeys.set_enabled(self._hotkeys_enabled)

    def _restore_clipboard(self, original: QMimeData):
        clipboard = QApplication.clipboard()
        if clipboard.text() == self._clipboard_written:
            clipboard.setMimeData(original)
        self._clipboard_pending = False
        self.hotkeys.set_enabled(self._hotkeys_enabled)

    def closeEvent(self, event):
        if not self._confirm_change():
            self._quitting = False
            event.ignore()
            return
        if self.tray_icon is not None and not self._quitting:
            event.ignore()
            self._hide_to_tray()
            return
        self.hotkeys.stop()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.store.close()
        super().closeEvent(event)