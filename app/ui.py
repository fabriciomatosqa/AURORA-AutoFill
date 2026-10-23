"""Interface desktop do AURORA AutoFill (PySide6)."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import sys
import sqlite3

from PySide6.QtCore import QObject, Qt, QMimeData, QTimer, Signal, QPoint, QRectF, QRect, QSize, QTextBoundaryFinder
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QIcon, QKeySequence, QPalette,
                           QShortcut, QTextCharFormat, QTextCursor, QPainter, QPainterPath, QLinearGradient, QPen, QPixmap)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFileDialog,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QStackedWidget, QSystemTrayIcon,
    QTextEdit, QStatusBar, QToolButton, QVBoxLayout, QWidget,
)

from .core import (Snippet, SnippetStore, application_db_path,
                   render_snippet, validate_shortcut)
from .hotkeys import (GlobalHotkeyListener, replace_shortcut, paste_clipboard,
                      select_previous_characters, copy_selected_text, collapse_selection_to_end)
from .expansion import ClipboardLease, EditSnapshot, ExpansionCandidate, ExpansionOperation, utf16_slice, prefix_offset
from .windows_context import ContextUnavailable, FocusMonitor, capture_focus, capture_edit, set_caret, select_text_range
from .verified_fallback import supports_verified_copy, copied_shortcut_matches, is_teams_target
from .accessibility_context import warm_accessibility
from time import monotonic
from .formatting import has_rich_formatting, render_rich_html
from .features import AuroraFeaturesMixin
from .version import APP_VERSION
from .icons import apply_icon
from .font_catalog import AuroraFontCombo
from .color_dialog import AuroraColorDialog
from .color_button import AuroraColorButton
from .branding import brand_webp_bytes
from .inline_images import AuroraImageEditor, contains_inline_images, plain_text_fallback, validate_inline_html, image_sources, read_image_file
from .clipboard_content import (clone_mime, expansion_mime, image_mime,
                                ordered_clipboard_parts, clipboard_part_mime,
                                prepare_mixed_content)


def cursor_steps(text: str) -> int:
    """Conta caracteres visuais, tratando CRLF como uma quebra de linha."""
    finder = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text.replace("\r\n", "\n"))
    count = 0
    while finder.toNextBoundary() != -1:
        count += 1
    return count


def windows_clipboard_sequence():
    import sys
    if sys.platform == "win32":
        import ctypes
        return ctypes.windll.user32.GetClipboardSequenceNumber()
    return None


def foreground_window():
    import sys
    if sys.platform == "win32":
        import ctypes
        api = ctypes.windll.user32.GetForegroundWindow
        api.restype = ctypes.c_void_p
        return api()
    return None


STYLESHEET = """
/* AURORA — acabamento visual da identidade Aurora Boreal */
QWidget { font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; }
QMainWindow, QWidget#body, QWidget#rightPane, QWidget#editorPage, QWidget#welcomePage,
QStackedWidget {
  background-color: #091426; color: #eaf4ff; }
QWidget#topbar { background-color: #06152b; }
QLabel { background: transparent; color: #eaf4ff; }
QLabel#brandPrimary { font-size: 30px; font-weight: 820; letter-spacing: 4px; color: #f7fbff; }
QLabel#brandAccent { font-size: 30px; font-weight: 760; color: #79ead8; }
QLabel#topCaption { color: #d2eafa; font-size: 11px; font-weight: 600; }
QWidget#sidebar { background: #0f1d31; border-right: 1px solid #24445f; }
QLabel#sectionTitle { color: #91e1d6; font-size: 12px; font-weight: 750; letter-spacing: .6px; }
QLabel#shortcutConflict { color: #ffc0c8; font-size: 12px; font-weight: 600; }
QLabel#autosaveStatus { color: #79ead8; font-size: 12px; font-weight: 640; }
/* Barra tipográfica compacta, com dois alinhamentos como no Word. */
QFrame#fontToolbar {
  background: #102338; border: 1px solid #31536b; border-radius: 9px;
}
QFrame#fontToolbar QPushButton#fontTool,
QFrame#fontToolbar QToolButton#fontTool {
  min-width: 0px; max-height: 25px; min-height: 25px;
  border-radius: 5px; padding: 0px 4px; font-weight: 680;
  background: #19364b; border: 1px solid #365a71; color: #effaff;
}
QFrame#fontToolbar QPushButton#fontTool:checked,
QFrame#fontToolbar QToolButton#fontTool:checked {
  border-color: #79ead8; background: #2c6870; color: #ffffff;
}
QFrame#fontToolbar QPushButton#fontTool:hover,
QFrame#fontToolbar QToolButton#fontTool:hover {
  border-color: #79ead8; background: #28546a;
}
QFrame#fontToolbar QComboBox#fontFamily,
QFrame#fontToolbar QSpinBox#fontSize {
  min-height: 27px; max-height: 27px; padding: 0px 5px;
  background: #18394d; border: 1px solid #427084;
  border-radius: 5px; color: #effaff;
}
QFrame#fontToolbar QComboBox#fontFamily {
  padding-left: 7px; padding-right: 24px;
}
QFrame#fontToolbar QComboBox#fontFamily::drop-down {
  subcontrol-origin: padding; subcontrol-position: top right;
  width: 23px; border-left: 1px solid #355d74;
  background: #204558; border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}
QFrame#fontToolbar QComboBox#fontFamily::down-arrow { image: none; }
QFrame#fontToolbar QComboBox#fontFamily QLineEdit {
  background: transparent; color: #effaff; border: none;
  min-height: 18px; padding: 0px;
}
QFrame#fontToolbar QComboBox#fontFamily:focus,
QFrame#fontToolbar QSpinBox#fontSize:focus { border-color: #79ead8; }
QFrame#fontToolbar QFrame#fontDivider {
  color: #385a70; background: #385a70;
  max-width: 1px; min-width: 1px;
}
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
QPushButton:pressed, QToolButton:pressed { background: #255763; border-color: #79ead8; }
QPushButton:disabled, QToolButton:disabled {
  color: #7995ab; background: #162a3e; border-color: #2b4358; }
QPushButton:focus, QToolButton:focus { border-color: #79ead8; }
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
    triggered = Signal(object)


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


class AuroraMenu(QMenu):
    """Rounded popup with an explicitly transparent window outside its corners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setStyleSheet("""
            QMenu { background: #112f41; color: #ebfaff; border: 1px solid #2f8590;
                border-radius: 10px; padding: 6px; font-size: 13px; }
            QMenu::item { background: transparent; color: #e5f7ff;
                padding: 10px 16px; margin: 2px 3px; border-radius: 7px; }
            QMenu::item:selected { background: #287281; color: white; }
            QMenu::item:checked { color: #7df0d9; }
            QMenu::separator { background: #355168; height: 1px; margin: 4px 8px; }
        """)


class AuroraFolderCombo(QComboBox):
    """Exibe as pastas usando menu Qt próprio, evitando bordas nativas acinzentadas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_menu = None

    def showPopup(self):
        menu = AuroraMenu(self)
        menu.setObjectName("folderSelectionMenu")
        menu.setMinimumWidth(max(self.width(), 210))
        menu.setStyleSheet(menu.styleSheet() + "QMenu::indicator { width: 0px; height: 0px; }")
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


class AuroraMenuButton(QToolButton):
    """Menu trigger with the same rounded surface and arrow lane as folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tokenPicker")
        self.setMinimumHeight(40)
        self.setStyleSheet("QToolButton#tokenPicker { font-weight: 400; }")
        self.setPopupMode(QToolButton.InstantPopup)

    def sizeHint(self):
        size = super().sizeHint()
        width = self.fontMetrics().horizontalAdvance(self.text()) + 76
        return size.expandedTo(QSize(width, 40))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = QPainterPath()
        path.addRoundedRect(bounds, 10, 10)
        active = self.underMouse() or self.isDown() or bool(self.menu() and self.menu().isVisible())
        painter.fillPath(path, QColor("#184156" if active else "#143345"))
        painter.save()
        painter.setClipPath(path)
        arrow_left = self.width() - 29
        painter.fillRect(QRectF(arrow_left, 0, 29, self.height()), QColor("#1b495c"))
        painter.setPen(QColor("#28586d"))
        painter.drawLine(arrow_left, 0, arrow_left, self.height())
        painter.restore()
        border = "#67e7d5" if self.hasFocus() else "#59dfcf" if active else "#2f7077"
        painter.setPen(QPen(QColor(border), 1))
        painter.drawPath(path)
        center_y = self.height() // 2
        self.icon().paint(painter, QRect(12, center_y - 9, 18, 18))
        text_rect = QRect(36, 0, max(0, arrow_left - 44), self.height())
        painter.setPen(QColor("#f0feff" if self.isEnabled() else "#7995ab"))
        painter.setFont(self.font())
        label = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)
        painter.setPen(QPen(QColor("#8ef7de"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 15
        painter.drawLine(x - 5, center_y - 3, x, center_y + 2)
        painter.drawLine(x, center_y + 2, x + 5, center_y - 3)
        painter.end()


class ReorderableSnippetList(QListWidget):
    """Permite arrastar e soltar comandos e avisa quando a ordem foi alterada."""
    reordered = Signal()

    def dropEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        super().dropEvent(event)
        if event.isAccepted():
            self.reordered.emit()


class AutoFillWindow(AuroraFeaturesMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = SnippetStore(application_db_path())
        self.store.seed_if_empty()
        self._initialize_features()
        self.current_id: int | None = None
        self.dirty = False
        self._loading = False
        self._clipboard_pending = False
        self._clipboard_revision = 0
        QApplication.clipboard().dataChanged.connect(self._clipboard_changed)
        self._hotkeys_enabled = True
        self._clipboard_clone: QMimeData | None = None
        self._clipboard_written = ""
        self._clipboard_lease = None
        self._active_candidate = None
        self._expansion_operation = None
        self._queued_candidate = None
        self.setWindowTitle(f"AURORA AutoFill V{APP_VERSION} — Expansor de textos")
        assets = Path(__file__).resolve().parent.parent / "assets"
        self._aurora_logo = QPixmap()
        try:
            if not self._aurora_logo.loadFromData(brand_webp_bytes(assets), "WEBP"):
                raise ValueError("Qt não conseguiu carregar a nova imagem.")
        except (ValueError, OSError) as exc:
            self._aurora_logo = QPixmap(str(assets / "aurora_icon.png"))
            if self._aurora_logo.isNull():
                raise RuntimeError("Ícone AURORA ausente ou inválido.") from exc
        self.setWindowIcon(QIcon(self._aurora_logo))
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
        self._focus_monitor = FocusMonitor(self.hotkeys.invalidate) if started else None
        # Inicialização em segundo plano: evita o cold-start do PowerShell/UIA
        # justamente quando o usuário digita o primeiro atalho no navegador.
        if started:
            warm_accessibility()
        self.listen_button.setText("Atalhos ativos" if started else "Atalhos indisponíveis")
        apply_icon(self.listen_button, "bolt" if started else "pause")
        self.listen_button.setEnabled(started)
        self.listen_button.setToolTip("Ativar/desativar expansão em outros programas")
        self.statusBar().showMessage(message)
        self._refresh_all()
        self._show_welcome()
        # Consulta no primeiro ciclo Qt; a rede executa em QThread.
        QTimer.singleShot(0, self._initial_release_check)

    def _play_confirmation(self):
        """Som suave com liga/desliga e volume independente do Windows."""
        self._play_feedback()

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
        brand_mark.setPixmap(self._aurora_logo.scaled(108, 108, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand_mark.setFixedSize(108, 108)
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
        self.listen_button = apply_icon(QPushButton("Atalhos ativos"), "bolt")
        self.listen_button.setObjectName("headerButton")
        self.listen_button.setMinimumWidth(162)
        self.listen_button.clicked.connect(self._toggle_listener)
        h.addWidget(self.listen_button)
        settings_button = apply_icon(QPushButton(), "settings", label="Configurações e atualizações")
        settings_button.setObjectName("headerButton")
        settings_button.setToolTip("Configurações e atualizações")
        settings_button.setFixedWidth(42)
        settings_button.clicked.connect(self._show_settings)
        h.addWidget(settings_button)
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
        new_btn = apply_icon(QPushButton("Novo"), "plus", color="#09283b")
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
        add_folder = apply_icon(QPushButton(), "plus", label="Criar pasta")
        add_folder.setFixedWidth(36)
        add_folder.setToolTip("Criar pasta")
        add_folder.clicked.connect(self._add_folder)
        folder_row.addWidget(add_folder)
        self.remove_folder_button = apply_icon(QPushButton(), "minus", color="#ffbecf", label="Excluir pasta")
        self.remove_folder_button.setObjectName("danger")
        self.remove_folder_button.setFixedWidth(36)
        self.remove_folder_button.setToolTip("Excluir a pasta selecionada (sem apagar comandos)")
        self.remove_folder_button.clicked.connect(self._delete_folder)
        folder_row.addWidget(self.remove_folder_button)
        s.addLayout(folder_row)
        self.snippet_list = ReorderableSnippetList()
        self.snippet_list.setSpacing(1)
        self.snippet_list.setDefaultDropAction(Qt.MoveAction)
        self.snippet_list.reordered.connect(self._reorder_snippets)
        self.snippet_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.snippet_list.setTextElideMode(Qt.ElideRight)
        self.snippet_list.currentItemChanged.connect(self._choose_snippet)
        s.addWidget(self.snippet_list, 1)
        backup = QHBoxLayout()
        export = apply_icon(QPushButton("Exportar"), "export")
        export.clicked.connect(self._export)
        imported = apply_icon(QPushButton("Importar"), "import")
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
        self._build_features_page()
        splitter.addWidget(right)
        splitter.setSizes([302, 990])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setStatusBar(QStatusBar())
        self.statusBar().setSizeGripEnabled(False)
        self._setup_undo_ui()
        author = QLabel(f"Desenvolvido por Fabricio Matos  •  V{APP_VERSION}")
        author.setObjectName("developerCredit")
        self.statusBar().addPermanentWidget(author)

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._new_snippet)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("AURORA AutoFill")
        menu = AuroraMenu(self)
        self.tray_open_action = QAction("Abrir AURORA AutoFill", self)
        self.tray_open_action.triggered.connect(self._restore_from_tray)
        menu.addAction(self.tray_open_action)
        tray_settings = QAction("Configurações", self)
        tray_settings.triggered.connect(lambda: (self._restore_from_tray(), self._show_settings()))
        menu.addAction(tray_settings)
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
        sample_help = QLabel("Clique abaixo e experimente /bemvindo, /tutorial ou /datahora. Quem já utiliza o AURORA pode testar seus próprios atalhos.")
        sample_help.setWordWrap(True)
        v.addWidget(sample_help)
        self.test_box = AuroraImageEditor()
        self.test_box.imageRejected.connect(
            lambda message: self.statusBar().showMessage(message, 8000))
        self.test_box.setPlaceholderText("Digite seus atalhos aqui para experimentar...")
        self.test_box.setMinimumHeight(150)
        self.test_box.setMaximumHeight(200)
        v.addWidget(self.test_box)
        compatibility = QLabel("Este teste aceita texto e imagens. A compatibilidade em outros aplicativos pode variar.")
        compatibility.setObjectName("hint")
        compatibility.setWordWrap(True)
        v.addWidget(compatibility)
        tip = QLabel("💡 Variáveis disponíveis: {{data}}, {{hora}}, {{data_hora}}, {{clipboard}}, {{cursor}}")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        v.addWidget(tip)
        buttons = QHBoxLayout()
        buttons.addStretch()
        create = apply_icon(QPushButton("Criar meu primeiro comando"), "plus", color="#09283b")
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
        home_btn = apply_icon(QPushButton("Início"), "home")
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
        self.shortcut_input.setPlaceholderText("/chamado")
        shortcut_box.addWidget(self.shortcut_input)
        # Aviso em tempo real: explica o comando/pasta conflitante antes de
        # tentar salvar. Não bloqueia a digitação nem abre pop-ups a cada tecla.
        self.shortcut_feedback = QLabel("")
        self.shortcut_feedback.setObjectName("shortcutConflict")
        self.shortcut_feedback.setWordWrap(True)
        self.shortcut_feedback.hide()
        shortcut_box.addWidget(self.shortcut_feedback)
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
        content_label = QLabel("FONTE")
        content_label.setObjectName("sectionTitle")
        content_header.addWidget(content_label)
        content_header.addStretch()
        self.autosave_status = QLabel("Salvamento automático ativado")
        self.autosave_status.setObjectName("autosaveStatus")
        content_header.addWidget(self.autosave_status)
        v.addLayout(content_header)
        self.body_input = AuroraImageEditor()
        self.body_input.setPlaceholderText("Escreva e formate o conteúdo do comando...")
        self.body_input.imageRejected.connect(
            lambda message: QMessageBox.warning(self, "Imagem não inserida", message))
        # Barra própria Aurora, com todas as famílias instaladas no computador.
        # O QTextEdit continua sendo a origem do HTML e das imagens independentes.
        # Todos os comandos tipográficos em um único painel de 2 linhas,
        # com botões de 27px e espaçamento pequeno.
        self.font_toolbar = QFrame()
        self.font_toolbar.setObjectName("fontToolbar")
        toolbar_layout = QVBoxLayout(self.font_toolbar)
        toolbar_layout.setContentsMargins(7, 6, 7, 6)
        toolbar_layout.setSpacing(3)
        # Ordem inspirada no Word: fonte/tamanho no topo, estilos logo
        # abaixo e cores/caixa/tamanho na última linha. Sem espaços vazios
        # entre ferramentas da mesma família.
        family_row = QHBoxLayout()
        family_row.setSpacing(4)
        self.font_family = AuroraFontCombo()
        self.font_family.setFixedWidth(214)
        self.font_family.setFixedHeight(29)
        self.font_family.setToolTip("Fontes instaladas no Windows. Clique na seta ou pesquise pelo nome.")
        self.font_family.activated.connect(
            lambda _: self._commit_font_family())
        self.font_family.lineEdit().editingFinished.connect(self._commit_font_family)
        family_row.addWidget(self.font_family)

        self.font_size = QSpinBox()
        self.font_size.setObjectName("fontSize")
        self.font_size.setRange(6, 96)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(11)
        self.font_size.setFixedWidth(67)
        self.font_size.setFixedHeight(29)
        self.font_size.setToolTip("Tamanho da fonte, em pontos")
        self.font_size.valueChanged.connect(self._apply_font_size)
        family_row.addWidget(self.font_size)
        family_row.addStretch()
        toolbar_layout.addLayout(family_row)

        formatting_row = QHBoxLayout()
        formatting_row.setSpacing(4)
        self.format_buttons = {}
        for title, tip, mode in (
            ("B", "Negrito", "bold"), ("I", "Itálico", "italic"),
            ("U", "Sublinhado", "underline"), ("S̶", "Tachado", "strike"),
            ("x₂", "Subscrito", "subscript"), ("x²", "Sobrescrito", "superscript")
        ):
            button = QPushButton(title)
            button.setObjectName("fontTool")
            button.setToolTip(tip)
            button.setCheckable(True)
            button.setFixedSize(29, 27)
            button.clicked.connect(lambda checked, m=mode: self._apply_format(m, checked))
            self.format_buttons[mode] = button
            formatting_row.addWidget(button)
        clear_button = QPushButton("Limpar")
        clear_button.setFixedSize(62, 27)
        clear_button.setObjectName("fontTool")
        clear_button.setToolTip("Limpar formatação do trecho selecionado")
        clear_button.clicked.connect(self._clear_text_format)
        formatting_row.addWidget(clear_button)
        formatting_row.addStretch()
        toolbar_layout.addLayout(formatting_row)

        color_row = QHBoxLayout()
        color_row.setSpacing(4)
        # As amostras inferiores mostram a última cor escolhida, tal como no
        # Word, inclusive quando o cursor vai para outro trecho da mensagem.
        self.text_color_button = AuroraColorButton("A", QColor("#142b40"))
        self.text_color_button.setToolTip("Cor do texto — a barra mostra a cor escolhida")
        self.text_color_button.clicked.connect(lambda: self._choose_font_color(False))
        color_row.addWidget(self.text_color_button)
        self.highlight_button = AuroraColorButton("✎", QColor("#fff59d"))
        self.highlight_button.setToolTip("Cor do realce — a barra mostra a cor escolhida")
        self.highlight_button.clicked.connect(lambda: self._choose_font_color(True))
        color_row.addWidget(self.highlight_button)
        case_button = QToolButton()
        case_button.setText("Aa ▾")
        case_button.setFixedSize(48, 27)
        case_button.setToolTip("Maiúsculas, minúsculas e iniciais maiúsculas")
        case_button.setObjectName("fontTool")
        case_button.setPopupMode(QToolButton.InstantPopup)
        case_menu = AuroraMenu(case_button)
        for label, mode in (("MAIÚSCULAS", "upper"),
                            ("minúsculas", "lower"),
                            ("Iniciais Maiúsculas", "title"),
                            ("Alternar caixa", "swapcase")):
            action = case_menu.addAction(label)
            action.triggered.connect(lambda checked=False, m=mode: self._transform_case(m))
        case_button.setMenu(case_menu)
        color_row.addWidget(case_button)
        for text, tip, delta in (("A+", "Aumentar tamanho", 1),
                                 ("A−", "Diminuir tamanho", -1)):
            button = QPushButton(text)
            button.setObjectName("fontTool")
            button.setFixedSize(30, 27)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, amount=delta: self._step_font_size(amount))
            color_row.addWidget(button)
        color_row.addStretch()
        toolbar_layout.addLayout(color_row)
        v.addWidget(self.font_toolbar)
        image_tools_row = QHBoxLayout()
        image_tools_row.setSpacing(8)
        self.insert_image_button = apply_icon(QPushButton("Inserir imagem"), "image",
                                              label="Inserir imagem no comando")
        self.insert_image_button.setToolTip(
            "Insira PNG ou JPG entre parágrafos, ou cole um print com Ctrl+V.")
        self.insert_image_button.clicked.connect(self._insert_image_file)
        image_tools_row.addWidget(self.insert_image_button)
        self.token_button = AuroraMenuButton()
        self.token_button.setText("Inserir comando dinâmico")
        apply_icon(self.token_button, "plus")
        self.token_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.token_button.setPopupMode(QToolButton.InstantPopup)
        self.token_button.setMinimumWidth(238)
        menu = AuroraMenu(self.token_button)
        menu.setObjectName("dynamicTokenMenu")
        for label, token in [
            ("Data atual", "{{data}}"), ("Hora atual", "{{hora}}"),
            ("Data e hora", "{{data_hora}}"), ("Área de transferência", "{{clipboard}}"),
            ("Posição do cursor", "{{cursor}}"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, t=token: self.body_input.insertPlainText(t))
            menu.addAction(action)
        self.token_button.setMenu(menu)
        image_tools_row.addWidget(self.token_button)
        image_tools_row.addStretch()
        v.addLayout(image_tools_row)
        self.body_input.currentCharFormatChanged.connect(self._sync_format_buttons)
        self.body_input.setMinimumHeight(190)
        v.addWidget(self.body_input, 3)
        copy_row = QHBoxLayout()
        self.copy_content_button = AuroraMenuButton()
        self.copy_content_button.setText("Copiar para outro aplicativo")
        self.copy_content_button.setPopupMode(QToolButton.InstantPopup)
        self.copy_content_menu = AuroraMenu(self.copy_content_button)
        self.copy_content_menu.aboutToShow.connect(self._prepare_copy_menu)
        self.copy_content_button.setMenu(self.copy_content_menu)
        copy_row.addWidget(self.copy_content_button)
        copy_hint = QLabel("Teams: use Copiar mensagem como imagem única e cole com Ctrl+V.\n"
                          "Se o destino não aceitar, tente Copiar imagem individual. Verifique o anexo antes de enviar.")
        copy_hint.setObjectName("hint")
        copy_hint.setWordWrap(True)
        copy_row.addWidget(copy_hint, 1)
        v.addLayout(copy_row)
        preview_label = QLabel("PRÉ-VISUALIZAÇÃO")
        preview_label.setObjectName("sectionTitle")
        v.addWidget(preview_label)
        self.preview = AuroraImageEditor()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(145)
        self.preview.setPlaceholderText("O resultado do modelo aparecerá aqui.")
        v.addWidget(self.preview, 2)
        tip = QLabel("{{cursor}} posiciona o ponto de digitação. Atalhos: Ctrl+N (novo) e Ctrl+S (salvar).")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        v.addWidget(tip)
        action_row = QHBoxLayout()
        self.delete_button = apply_icon(QPushButton("Excluir"), "trash", color="#ffbecf")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self._delete)
        action_row.addWidget(self.delete_button)
        action_row.addStretch()
        cancel_button = QPushButton("Cancelar")
        cancel_button.clicked.connect(self._show_welcome)
        action_row.addWidget(cancel_button)
        self.save_button = apply_icon(QPushButton("Salvar agora (opcional)"), "save", color="#09283b")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._save)
        action_row.addWidget(self.save_button)
        v.addLayout(action_row)
        self.editor_scroll = QScrollArea()
        self.editor_scroll.setObjectName("editorScroll")
        self.editor_scroll.setFrameShape(QFrame.NoFrame)
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_scroll.setWidget(page)
        self.stack.addWidget(self.editor_scroll)
        self.title_input.textChanged.connect(lambda *_: self._autosave_edit("title"))
        self.shortcut_input.textChanged.connect(self._update_shortcut_feedback)
        self.shortcut_input.textChanged.connect(lambda *_: self._autosave_edit("shortcut"))
        self.body_input.textChanged.connect(lambda: self._autosave_edit("content"))
        self.body_input.textChanged.connect(self._update_preview)
        self.editor_folder.currentIndexChanged.connect(
            lambda *_: self._autosave_edit("folder_id"))

    def _prepare_copy_menu(self):
        self.copy_content_menu.clear()
        html = self.body_input.toHtml()
        sources = image_sources(html)
        complete = self.copy_content_menu.addAction("Copiar todo o texto (sem imagens)")
        complete.triggered.connect(lambda: self._copy_content_part(None))
        if sources:
            self.copy_content_menu.addSeparator()
            heading = self.copy_content_menu.addAction(
                "Para Teams: copie e cole cada parte na ordem")
            heading.setEnabled(False)
            next_part = self.copy_content_menu.addAction(
                "Copiar próxima parte (texto ou imagem)")
            next_part.triggered.connect(
                lambda: self._copy_content_part(("next", None)))
            self.copy_content_menu.addSeparator()
            try:
                parts = ordered_clipboard_parts(html)
            except ValueError:
                parts = ()
            images = text_parts = 0
            for index, part in enumerate(parts):
                if part.kind == "image":
                    images += 1
                    title = f"{index + 1}. Copiar imagem {images}"
                else:
                    text_parts += 1
                    title = f"{index + 1}. Copiar trecho de texto {text_parts}"
                action = self.copy_content_menu.addAction(title)
                action.triggered.connect(
                    lambda checked=False, position=index:
                    self._copy_content_part(("part", position)))

    def _copy_content_part(self, index):
        try:
            if self._expansion_operation is not None:
                raise ValueError("Aguarde a expansão terminar antes de copiar.")
            html = self.body_input.toHtml()
            if isinstance(index, tuple):
                kind, position = index
                parts = ordered_clipboard_parts(
                    html, self._clipboard_source_text(), datetime.now())
                if not parts:
                    raise ValueError("Não há conteúdo para copiar.")
                current_document = getattr(self, "_copy_sequence_html", None)
                if current_document != html:
                    self._copy_sequence_html = html
                    self._copy_sequence_index = 0
                if kind == "next":
                    position = self._copy_sequence_index
                    if position >= len(parts):
                        position = 0
                if not isinstance(position, int) or not 0 <= position < len(parts):
                    raise ValueError("Parte solicitada não existe neste comando.")
                part = parts[position]
                payload = clipboard_part_mime(part)
                self._copy_sequence_index = position + 1
                description = "Imagem" if part.kind == "image" else "Texto editável"
                message = (f"Parte {position + 1}/{len(parts)} — {description} copiado. "
                           "Cole no Teams com Ctrl+V e depois copie a próxima parte. "
                           "Confirme a imagem antes de enviar.")
            elif index is None:
                text = self.body_input.toPlainText().replace("\ufffc", "")
                payload = QMimeData()
                payload.setText(render_snippet(text, self._clipboard_source_text()).text)
                message = ("Texto editável copiado, sem as imagens. "
                           "Para preservar a ordem, use as partes no menu.")
            else:
                payload = image_mime(image_sources(html)[index])
                message = (f"Imagem {index + 1} copiada como PNG/bitmap. "
                           "Cole no Teams com Ctrl+V e confira o anexo.")
            # Explicit user copy must outlive automatic clipboard restoration.
            self._clipboard_lease = None
            self._clipboard_pending = False
            QApplication.clipboard().setMimeData(payload)
            self.statusBar().showMessage(message, 10000)
        except (ValueError, IndexError, TypeError) as exc:
            self.statusBar().showMessage(str(exc), 8000)

    def _insert_image_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Inserir foto ou print", "",
            "Imagens (*.png *.jpg *.jpeg *.webp *.bmp);;Todos os arquivos (*)")
        if not path:
            return
        try:
            image = read_image_file(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Imagem inválida",
                                str(exc))
            return
        if self.body_input.insert_image(image):
            self.body_input.setFocus()
            self.statusBar().showMessage(
                "Imagem incorporada e salva automaticamente quando o comando estiver válido.", 5000)

    def _merge_text_format(self, fmt: QTextCharFormat):
        """Formata somente a seleção; sem seleção define o estilo das próximas letras."""
        self.body_input.mergeCurrentCharFormat(fmt)
        self.body_input.setFocus()
        self._autosave_edit("content")

    def _apply_format(self, mode: str, active: bool):
        fmt = QTextCharFormat()
        if mode == "bold":
            fmt.setFontWeight(QFont.Bold if active else QFont.Normal)
        elif mode == "italic":
            fmt.setFontItalic(active)
        elif mode == "underline":
            fmt.setFontUnderline(active)
        elif mode == "strike":
            fmt.setFontStrikeOut(active)
        elif mode in {"superscript", "subscript"}:
            target = (QTextCharFormat.AlignSuperScript if mode == "superscript"
                      else QTextCharFormat.AlignSubScript)
            fmt.setVerticalAlignment(target if active else QTextCharFormat.AlignNormal)
        self._merge_text_format(fmt)

    def _commit_font_family(self):
        """Aplicar só uma família existente, escolhida ou digitada no filtro."""
        value = self.font_family.currentText().strip()
        index = self.font_family.findText(value, Qt.MatchFixedString)
        if index < 0:
            self.statusBar().showMessage(
                "Selecione uma fonte instalada na lista.", 3000)
            return
        self._apply_font_family(self.font_family.itemText(index))

    def _apply_font_family(self, family: str):
        if self._loading or not family:
            return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family])
        self._merge_text_format(fmt)

    def _apply_font_size(self, size: int):
        if self._loading:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self._merge_text_format(fmt)

    def _step_font_size(self, delta: int):
        fmt = self.body_input.currentCharFormat()
        original = fmt.fontPointSize()
        if original <= 0:
            original = self.body_input.font().pointSizeF()
        if original <= 0:
            original = 11
        self._apply_font_size(max(6, min(96, round(original) + delta)))

    def _choose_font_color(self, highlight: bool):
        fmt = self.body_input.currentCharFormat()
        previous = (fmt.background() if highlight else fmt.foreground()).color()
        if not previous.isValid():
            previous = QColor("#fff59d" if highlight else "#142b40")
        color = AuroraColorDialog.get_color(
            previous, self, "Cor do realce" if highlight else "Cor do texto")
        if not color.isValid():
            return
        change = QTextCharFormat()
        if highlight:
            change.setBackground(color)
        else:
            change.setForeground(color)
        self._merge_text_format(change)
        # Reflete a escolha somente após uma cor válida ter sido aplicada.
        (self.highlight_button if highlight else self.text_color_button).set_marker_color(color)

    def _clear_text_format(self):
        cursor = self.body_input.textCursor()
        clean = QTextCharFormat()
        # setCharFormat aplica a formatação à seleção (merge de objeto vazio
        # não remove propriedades antigas); sem seleção, às futuras letras.
        if cursor.hasSelection():
            cursor.setCharFormat(clean)
        else:
            self.body_input.setCurrentCharFormat(clean)
        self.body_input.setFocus()
        self._autosave_edit("content")

    def _transform_case(self, mode: str):
        cursor = self.body_input.textCursor()
        if not cursor.hasSelection():
            self.statusBar().showMessage("Selecione as letras para mudar maiúsculas/minúsculas.", 3000)
            return
        content = cursor.selectedText()
        conversion = {
            "upper": str.upper, "lower": str.lower,
            "title": str.title, "swapcase": str.swapcase,
        }[mode]
        cursor.insertText(conversion(content).replace("\u2029", "\n"), cursor.charFormat())
        self.body_input.setTextCursor(cursor)
        self.body_input.setFocus()
        self._autosave_edit("content")

    def _sync_format_buttons(self, fmt: QTextCharFormat):
        alignment = fmt.verticalAlignment()
        values = (
            ("bold", fmt.fontWeight() >= QFont.Bold),
            ("italic", fmt.fontItalic()),
            ("underline", fmt.fontUnderline()),
            ("strike", fmt.fontStrikeOut()),
            ("subscript", alignment == QTextCharFormat.AlignSubScript),
            ("superscript", alignment == QTextCharFormat.AlignSuperScript),
        )
        for key, checked in values:
            btn = self.format_buttons[key]
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)
        # fontFamily() é obsoleto no Qt 6 e pode acessar estado nulo do
        # QTextCharFormat em runners Qt offscreen. Usar fontFamilies().
        families = fmt.fontFamilies()
        if families:
            self.font_family.blockSignals(True)
            selected = str(families[0])
            index = self.font_family.findText(selected, Qt.MatchFixedString)
            if index >= 0:
                self.font_family.setCurrentIndex(index)
            else:
                # Preserva fontes legadas de documentos de outro computador.
                self.font_family.setEditText(selected)
            self.font_family.blockSignals(False)
        size = fmt.fontPointSize()
        if size > 0:
            self.font_size.blockSignals(True)
            self.font_size.setValue(max(6, min(96, round(size))))
            self.font_size.blockSignals(False)

    def _set_save_status(self, message: str, *, error: bool = False):
        self.autosave_status.setText(message)
        self.autosave_status.setStyleSheet(
            "color: #ffc0c8;" if error else "color: #79ead8;")

    def _update_current_list_item(self):
        """Atualiza a navegação sem recriar o editor, seleção ou cursor."""
        current = self.current_id
        if current is None:
            return
        for index in range(self.snippet_list.count()):
            item = self.snippet_list.item(index)
            if item.data(Qt.UserRole) == current:
                item.setText(f"{self.title_input.text().strip()}  ·  {self.shortcut_input.text().strip()}")
                item.setToolTip(
                    f"Atalho: {self.shortcut_input.text().strip()}\n"
                    f"{plain_text_fallback(self.body_input.toPlainText())[:160]}")
                break

    def _autosave_edit(self, field: str):
        """Cada alteração válida é persistida antes da próxima edição.

        Atalhos inválidos nunca sobrescrevem o último comando íntegro.
        A mudança de título/atalho não reserializa HTML e imagens.
        """
        if self._loading:
            return
        self.dirty = True
        try:
            folder = self.editor_folder.currentData()
            if folder is None:
                raise ValueError("Selecione uma pasta.")
            if self.current_id is None:
                text = plain_text_fallback(self.body_input.toPlainText())
                # Campos obrigatórios ainda incompletos são um rascunho
                # em memória; a criação ocorre no primeiro estado válido.
                new_id = self.store.save(
                    folder, self.title_input.text(), self.shortcut_input.text(),
                    text, rich_content=self._validated_editor_html())
                self.current_id = new_id
                self.edit_heading.setText("Editar comando")
                self.delete_button.setVisible(True)
                self._refresh_list()
            else:
                if field == "title":
                    data = {"title": self.title_input.text()}
                elif field == "shortcut":
                    data = {"shortcut": self.shortcut_input.text()}
                elif field == "folder_id":
                    data = {"folder_id": folder}
                elif field == "content":
                    data = {
                        "content": plain_text_fallback(self.body_input.toPlainText()),
                        "rich_content": self._validated_editor_html(),
                    }
                else:
                    return
                self.store.update_snippet_fields(self.current_id, **data)
                if field == "shortcut":
                    self._update_listener_shortcuts()
                self._update_current_list_item()
        except (ValueError, sqlite3.Error, OSError) as error:
            self._set_save_status(f"Ainda não salvo: {error}", error=True)
            return
        self.dirty = False
        self._set_save_status("✓ Alterações salvas automaticamente")

    def _mark_dirty(self, *_):
        if not self._loading:
            self.dirty = True

    def _update_preview(self):
        text = plain_text_fallback(self.body_input.toPlainText())
        current_clipboard = QApplication.clipboard().text()
        result = render_snippet(text, current_clipboard)
        rich_html = self.body_input.toHtml()
        if contains_inline_images(rich_html) or has_rich_formatting(rich_html):
            self.preview.setHtml(render_rich_html(rich_html, current_clipboard))
        else:
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
        can_sort = not self.search.text().strip()
        self.snippet_list.setDragDropMode(
            QAbstractItemView.InternalMove if can_sort else QAbstractItemView.NoDragDrop)
        self.snippet_list.setToolTip(
            "Arraste comandos para alterar a ordem" if can_sort
            else "Limpe a busca para ordenar comandos")
        self.remove_folder_button.setEnabled(folder_id is not None)
        self._update_listener_shortcuts()

    def _reorder_snippets(self):
        if self.search.text().strip():
            self._refresh_list()
            return
        ordered_ids = [self.snippet_list.item(index).data(Qt.UserRole)
                       for index in range(self.snippet_list.count())]
        try:
            self.store.reorder_snippets(self.filter_folder.currentData(), ordered_ids)
        except ValueError as exc:
            QMessageBox.warning(self, "Não foi possível ordenar", str(exc))
            self._refresh_list()
            return
        self._refresh_list()
        self.statusBar().showMessage("Ordem dos comandos atualizada.", 4000)

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
            self, "Rascunho incompleto",
            "Existem alterações ainda inválidas que não puderam ser salvas automaticamente. Descartá-las?",
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
        self._update_shortcut_feedback()
        self._set_save_status(
            "✓ Alterações salvas automaticamente" if snippet
            else "Novo comando: será salvo quando título, atalho e conteúdo estiverem completos.")
        self._sync_format_buttons(self.body_input.currentCharFormat())
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

    def _update_shortcut_feedback(self, *_):
        """Indica o conflito assim que digitado; desativa Salvar antes do clique."""
        shortcut = self.shortcut_input.text().strip()
        message = ""
        if shortcut not in {"", "/"}:
            try:
                validate_shortcut(shortcut)
            except ValueError as exc:
                message = str(exc)
            else:
                conflict = self.store.shortcut_conflict(shortcut, excluding_id=self.current_id)
                if conflict is not None:
                    message = (
                        f"Conflito: {shortcut} é igual ou se sobrepõe a "
                        f"{conflict.shortcut} — «{conflict.title}» "
                        f"(pasta «{conflict.folder}»). Escolha outro atalho."
                    )
        self.shortcut_feedback.setText(message)
        self.shortcut_feedback.setVisible(bool(message))
        self.shortcut_input.setToolTip(message or "Atalho único, sem prefixos sobrepostos.")
        self.save_button.setEnabled(bool(shortcut) and shortcut != "/" and not message)

    def _validated_editor_html(self) -> str:
        html = self.body_input.toHtml()
        validate_inline_html(html)
        return html

    def _save(self):
        if self.stack.currentIndex() != 1:
            return
        try:
            new_id = self.store.save(
                self.editor_folder.currentData(),
                self.title_input.text(), self.shortcut_input.text(),
                plain_text_fallback(self.body_input.toPlainText()), self.current_id,
                rich_content=self._validated_editor_html())
        except (ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Não foi possível salvar", str(error))
            return
        was_new = self.current_id is None
        self.current_id = new_id
        self.dirty = False
        if was_new:
            self.edit_heading.setText("Editar comando")
            self.delete_button.setVisible(True)
        self._refresh_list()
        self._set_save_status("✓ Alterações salvas automaticamente")
        self.statusBar().showMessage("Comando salvo com sucesso.", 3500)
        self._play_confirmation()

    def _delete(self):
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Excluir comando", "Deseja realmente excluir este comando?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            snapshot = self.store.delete_with_undo(self.current_id)
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível excluir", str(exc))
            return
        self.dirty = False
        self.current_id = None
        self._refresh_all()
        self._show_welcome()
        self._offer_undo("snippet", snapshot, "Comando excluído")

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

    def _delete_folder(self):
        folder_id = self.filter_folder.currentData()
        if folder_id is None or not self._confirm_change():
            return
        folders = dict(self.store.folders())
        name = folders.get(folder_id)
        if name is None:
            self._refresh_all()
            return
        count = len(self.store.snippets(folder_id))
        others = [(fid, label) for fid, label in folders.items() if fid != folder_id]
        destination = (next((label for _, label in others if label.casefold() == "meus atalhos"),
                            others[0][1]) if others
                       else ("Sem pasta" if name.casefold() == "meus atalhos" else "Meus atalhos"))
        detail = (f"Os {count} comandos serão movidos para a pasta '{destination}'." if count
                  else "A pasta está vazia.")
        confirmation = QMessageBox.question(
            self, "Excluir pasta",
            f"Excluir a pasta '{name}'?\n\n{detail}\nNenhum comando será apagado.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirmation != QMessageBox.Yes:
            return
        try:
            moved, target, snapshot = self.store.delete_folder_with_undo(folder_id)
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível excluir a pasta", str(exc))
            return
        self.dirty = False
        self._refresh_all()
        self._show_welcome()
        self.statusBar().showMessage(
            f"Pasta excluída. {moved} comando(s) preservado(s) em '{target}'.", 6000)
        self._offer_undo("folder", snapshot, "Pasta excluída")

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
            except (ValueError, OSError, TypeError, sqlite3.Error) as exc:
                QMessageBox.warning(self, "Erro na importação", str(exc))

    def _toggle_listener(self):
        self._hotkeys_enabled = not self._hotkeys_enabled
        self.hotkeys.set_enabled(self._hotkeys_enabled)
        self.listen_button.setText("Atalhos ativos" if self._hotkeys_enabled else "Atalhos pausados")
        apply_icon(self.listen_button, "bolt" if self._hotkeys_enabled else "pause")
        if self.tray_toggle_action is not None:
            self.tray_toggle_action.setText("Pausar atalhos" if self._hotkeys_enabled else "Retomar atalhos")
        self.statusBar().showMessage("Expansão ativa." if self._hotkeys_enabled else "Expansão pausada.", 4000)

    @staticmethod
    def _clone_clipboard_mime() -> QMimeData:
        return clone_mime(QApplication.clipboard().mimeData())

    def _clipboard_changed(self):
        self._clipboard_revision += 1

    def _clipboard_sequence(self):
        native = windows_clipboard_sequence()
        return native if native is not None else self._clipboard_revision

    def _expand_global(self, candidate: ExpansionCandidate):
        if not self._hotkeys_enabled or self._quitting or not self.hotkeys.is_current(candidate):
            return
        if self.isActiveWindow() and self.focusWidget() is not self.test_box:
            return
        if sys.platform == "win32" and not (candidate.context.window and candidate.context.control):
            return
        operation = self._expansion_operation
        lease = self._clipboard_lease
        if (operation and operation.stage in {"selected", "verifying", "sent", "moving"}
                or lease and not lease.consumed and self._owns_clipboard(lease)):
            self._queued_candidate = candidate
            return
        if capture_focus() != candidate.context or not self.hotkeys.claim(candidate):
            return
        self._active_candidate = candidate
        # Aciona imediatamente ao terminar o atalho, sem atraso mínimo.
        # A segurança permanece no verificador de foco/texto/seleção; campos
        # web assíncronos são tentados novamente somente quando necessário.
        QTimer.singleShot(0, lambda c=candidate: self._perform_expansion(c))

    def _candidate_valid(self, candidate):
        operation = self._expansion_operation
        already_sent = (operation is not None and operation.candidate is candidate
                        and operation.stage in {"selected", "verifying", "sent", "moving"})
        # Never expire a sent paste mid-confirmation. Still reject a changed
        # keyboard revision or actual focus change to protect the destination.
        return (self._active_candidate is candidate and self._hotkeys_enabled and not self._quitting
                and self.hotkeys.is_current(candidate, require_fresh=not already_sent)
                and capture_focus() == candidate.context)

    def _edit_snapshot(self, *, accessibility=False):
        context = capture_focus()
        if self.isActiveWindow() and self.focusWidget() is self.test_box:
            cursor = self.test_box.textCursor()
            return EditSnapshot(context, self.test_box.toPlainText(), cursor.selectionStart(), cursor.selectionEnd())
        return capture_edit(context, accessibility=True) if accessibility else capture_edit(context)

    def _owns_clipboard(self, lease):
        mime = QApplication.clipboard().mimeData()
        return bool(mime and mime.text() == lease.text
                    and bytes(mime.data("application/x-aurora-expansion")) == lease.token
                    and self._clipboard_sequence() == lease.sequence)

    def _set_caret(self, snapshot, offset):
        if self.isActiveWindow() and self.focusWidget() is self.test_box:
            if self._edit_snapshot() != snapshot:
                raise ContextUnavailable("O campo mudou antes de posicionar o cursor.")
            cursor = self.test_box.textCursor()
            cursor.setPosition(offset)
            self.test_box.setTextCursor(cursor)
        else:
            set_caret(snapshot, offset)

    def _clipboard_source_text(self):
        lease = self._clipboard_lease
        if lease and lease.consumed and self._owns_clipboard(lease):
            return lease.original.text()
        return QApplication.clipboard().text()

    def _perform_expansion(self, candidate: ExpansionCandidate):
        if self._active_candidate is not candidate:
            return
        operation = None
        try:
            if not self._candidate_valid(candidate):
                raise ValueError("A digitação ou o destino mudou; expansão cancelada.")
            shortcut = candidate.shortcut
            copy_fallback = (sys.platform == "win32"
                             and supports_verified_copy(candidate.context)
                             and not (self.isActiveWindow() and self.focusWidget() is self.test_box))
            keyboard_verify = False
            snippet = self.store.snippet_by_shortcut(shortcut)
            if not snippet:
                self._finish_expansion(None)
                return
            try:
                before = self._edit_snapshot()
            except ContextUnavailable:
                if monotonic() - candidate.created < (0.15 if copy_fallback else 0.85):
                    QTimer.singleShot(10, lambda c=candidate: self._perform_expansion(c))
                    return
                if not copy_fallback:
                    raise
                before = None
                keyboard_verify = True
            if before is not None and before.shortcut_range(shortcut) is None:
                if monotonic() - candidate.created < 0.85:
                    QTimer.singleShot(10, lambda c=candidate: self._perform_expansion(c))
                    return
                if copy_fallback:
                    # Alguns editores (Teams/WebView) entregam texto atual e
                    # caret obsoleto. Sem confiar nesse intervalo, confirmar
                    # somente o atalho exato por seleção+Ctrl+C.
                    before = None
                    keyboard_verify = True
                else:
                    raise ValueError("O atalho não está no intervalo esperado; expansão cancelada.")
            if before is None and not keyboard_verify and sys.platform == "win32" and not (
                    self.isActiveWindow() and self.focusWidget() is self.test_box):
                # Campos WebView e controles personalizados podem não expor
                # texto por Win32. Jamais selecionar caracteres às cegas:
                # requeremos o texto e o cursor reais via UI Automation.
                # UIA logo após keyup; tenta novamente apenas se o editor
                # ainda não confirmar texto/cursor, sem pausar à força.
                try:
                    before = self._edit_snapshot(accessibility=True)
                except ContextUnavailable:
                    if monotonic() - candidate.created < (0.15 if copy_fallback else 0.85):
                        QTimer.singleShot(20, lambda c=candidate: self._perform_expansion(c))
                        return
                    if not copy_fallback:
                        raise
                    before = None
                    keyboard_verify = True
                if before is None and copy_fallback:
                    keyboard_verify = True
                elif before is None:
                    raise ValueError(
                        "O editor não oferece seleção verificável. "
                        "Atalho preservado; use Copiar para outro aplicativo.")
                if before is not None and before.shortcut_range(shortcut) is None:
                    if monotonic() - candidate.created < 0.35:
                        QTimer.singleShot(20, lambda c=candidate: self._perform_expansion(c))
                        return
                    if copy_fallback:
                        # UIA pode ler o texto mas indicar posição atrasada.
                        # A via alternativa só cola após Ctrl+C provar que a
                        # seleção contém exatamente o atalho digitado.
                        before = None
                        keyboard_verify = True
                    else:
                        raise ValueError(
                            "O atalho não está imediatamente antes do cursor; "
                            "não foi feita nenhuma substituição.")
            current_text = self._clipboard_source_text()
            now = datetime.now()
            rendered = render_snippet(snippet.content, current_text, now)
            if not rendered.text:
                self._finish_expansion(None)
                return
            # NUL não pode ser transportado integralmente por CF_UNICODETEXT.
            if "\x00" in rendered.text:
                raise ValueError("O texto contém um caractere NUL e não pode ser colado.")
            rendered.text.encode("utf-16-le")  # Rejeita pares substitutos inválidos antes de editar.
            # O Notepad lê CF_UNICODETEXT. HTML é opcional e só aparece quando
            # o modelo foi realmente formatado (Word/Outlook podem aproveitar).
            rich = bool(snippet.rich_content and has_rich_formatting(snippet.rich_content)
                        and "{{cursor}}" not in snippet.content)
            if keyboard_verify and rendered.left_moves:
                # Sem leitura do documento, {{cursor}} não pode ser colocado
                # com precisão após a colagem.
                raise ValueError("Este comando usa {{cursor}} e exige acessibilidade do editor.")
            suffix = rendered.text[-rendered.left_moves:] if rendered.left_moves else ""
            if rendered.left_moves and before is None:
                try:
                    before = self._edit_snapshot(accessibility=True)
                except ContextUnavailable:
                    if monotonic() - candidate.created < 0.85:
                        QTimer.singleShot(10, lambda c=candidate: self._perform_expansion(c))
                        return
                    raise
                if before is None:
                    raise ValueError("Este campo não permite confirmar o posicionamento do cursor.")
                if before.shortcut_range(shortcut) is None:
                    raise ValueError("O atalho não está no intervalo acessível esperado; expansão cancelada.")
            operation = ExpansionOperation(candidate, before, rendered.text, cursor_steps(suffix),
                                           rendered.text[:-rendered.left_moves] if rendered.left_moves else rendered.text,
                                           render_rich_html(snippet.rich_content, current_text, now) if rich else "")
            operation.keyboard_verify = keyboard_verify
            # O Teams aceita conteúdo HTML, mas não deve receber RTF Office
            # como formato concorrente. Sem alteração para Word/outros apps.
            operation.teams_web_html = bool(operation.rich_html and is_teams_target(candidate.context))
            self._expansion_operation = operation
            if image_sources(snippet.rich_content):
                mixed = prepare_mixed_content(snippet.rich_content, current_text, now)
                operation.text, operation.rich_html = mixed.text, mixed.html
                operation.document_text = mixed.document_text
                operation.cursor_prefix = mixed.cursor_prefix
                operation.document_cursor_prefix = mixed.document_cursor_prefix
                operation.left_moves = mixed.left_moves
                operation.image_count, operation.image_only = mixed.image_count, mixed.image_only
                if "\x00" in operation.text:
                    raise ValueError("O texto contém um caractere NUL e não pode ser colado.")
                operation.text.encode("utf-16-le")
                if before is None and not keyboard_verify:
                    before = self._edit_snapshot(accessibility=True)
                    if before is None or before.shortcut_range(shortcut) is None:
                        raise ValueError("Não é possível verificar o atalho neste campo. Use o menu Copiar para outro aplicativo.")
                    operation.before = before
            if not self._candidate_valid(candidate):
                raise ValueError("O contexto mudou antes da seleção.")
            self._submit_expansion(operation)
        except Exception as exc:
            self._finish_expansion(operation, f"Não foi possível expandir: {exc}")

    def _submit_expansion(self, operation):
        if self._expansion_operation is not operation:
            return
        try:
            if not self._candidate_valid(operation.candidate):
                raise ValueError("Atividade ou foco mudou; colagem cancelada.")
            if operation.keyboard_verify:
                self._begin_keyboard_verification(operation, select_keyboard=True)
                return
            clipboard = QApplication.clipboard()
            backup_sequence = self._clipboard_sequence()
            previous = self._clipboard_lease
            original = (previous.original if previous and previous.consumed and self._owns_clipboard(previous)
                        else self._clone_clipboard_mime())
            from uuid import uuid4
            token = uuid4().hex.encode("ascii")
            payload = expansion_mime(operation.text, operation.rich_html,
                                     image_only=operation.image_only,
                                     web_html_only=operation.teams_web_html)
            payload.setData("application/x-aurora-expansion", token)
            if self._clipboard_sequence() != backup_sequence:
                raise ValueError("O clipboard mudou durante a preparação; colagem cancelada.")
            clipboard.setMimeData(payload)
            lease = ClipboardLease(operation.candidate.identifier, original, payload.text(), token,
                                   self._clipboard_sequence())
            operation.lease = self._clipboard_lease = lease
            self._clipboard_pending = True
            if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(lease):
                raise ValueError("Contexto ou clipboard mudou antes da colagem.")
            # Quando o destino é UIA, select_text_range() verifica de forma
            # atômica texto, identidade, cursor e seleção antes de enviar Ctrl+V.
            # Evitar um snapshot UIA idêntico antes dessa seleção: em navegadores
            # ele causa mais um round-trip caro ao processo de acessibilidade.
            verified_selection = (not (self.isActiveWindow() and self.focusWidget() is self.test_box)
                                  and operation.before is not None
                                  and bool(operation.before.identity or operation.image_count))
            if operation.before is not None and not verified_selection:
                snapshot = self._edit_snapshot(accessibility=bool(operation.before.identity))
                if (snapshot is None or snapshot.context != operation.candidate.context
                        or snapshot.identity != operation.before.identity
                        or snapshot.text != operation.before.text
                        or (snapshot.start, snapshot.end) != (operation.before.start, operation.before.end)
                        or snapshot.shortcut_range(operation.candidate.shortcut) is None):
                    raise ValueError("O intervalo mudou antes da colagem.")
            # Recheck after clipboard and native queries, immediately before dispatch.
            if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(lease):
                raise ValueError("Contexto ou clipboard mudou antes do envio.")
            if self.isActiveWindow() and self.focusWidget() is self.test_box:
                # Own editor: replace the verified range through Qt. This also
                # avoids a race between simulated selection and browser paste.
                begin, end = operation.before.shortcut_range(operation.candidate.shortcut)
                cursor = self.test_box.textCursor()
                cursor.setPosition(begin)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                self.test_box.setTextCursor(cursor)
                operation.stage = "sent"
                self.test_box.insertFromMimeData(payload)
            elif verified_selection:
                # WebView editors process keyboard selections asynchronously.
                # Select and verify the exact shortcut through UI Automation
                # before sending paste, rather than racing Shift+Left with Ctrl+V.
                begin, end = operation.before.shortcut_range(operation.candidate.shortcut)
                operation.stage = "selected"
                select_text_range(operation.before, begin, end)
                if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(lease):
                    raise ValueError("Contexto ou clipboard mudou após selecionar o atalho.")
                # O TextPatternRange.Select do Teams pode concluir antes de a
                # seleção aparecer no GetSelection. Só uma solicitação é enviada:
                # até 700 ms para confirmar, SEM selecionar ou colar de novo.
                operation.deadline = monotonic() + 0.7
                QTimer.singleShot(0, lambda op=operation: self._paste_verified_selection(op))
                return
            else:
                if sys.platform == "win32" and operation.before is None:
                    raise ValueError("Não há intervalo de texto verificável para substituir.")
                operation.stage = "sent"
                replace_shortcut(cursor_steps(operation.candidate.shortcut))
            self._expansion_sent(operation)
        except Exception as exc:
            self._finish_expansion(operation, f"Não foi possível expandir: {exc}")

    def _begin_keyboard_verification(self, operation, *, select_keyboard: bool):
        """Seleciona sem apagar e valida Ctrl+C antes de permitir Ctrl+V."""
        if (self._expansion_operation is not operation
                or not self._candidate_valid(operation.candidate)
                or not supports_verified_copy(operation.candidate.context)):
            raise ValueError("O destino mudou ou não permite a confirmação por cópia.")
        clipboard = QApplication.clipboard()
        prior = operation.lease
        original = prior.original if prior is not None else self._clone_clipboard_mime()
        from uuid import uuid4
        operation.verify_original = original
        operation.verify_marker = "AURORA-VERIFY-" + uuid4().hex
        operation.verify_select_keyboard = select_keyboard
        operation.stage = "verifying"
        clipboard.setText(operation.verify_marker)
        operation.verify_sequence = self._clipboard_sequence()
        operation.deadline = monotonic() + 0.45
        if select_keyboard:
            select_previous_characters(cursor_steps(operation.candidate.shortcut))
        copy_selected_text()
        QTimer.singleShot(10, lambda op=operation: self._confirm_keyboard_verification(op))

    def _confirm_keyboard_verification(self, operation):
        if self._expansion_operation is not operation or operation.stage != "verifying":
            return
        try:
            if not self._candidate_valid(operation.candidate):
                raise ValueError("Foco ou digitação mudou durante a confirmação do atalho.")
            clipboard = QApplication.clipboard()
            sequence = self._clipboard_sequence()
            selected = clipboard.text()
            changed = sequence != operation.verify_sequence
            if changed and copied_shortcut_matches(selected, operation.candidate.shortcut):
                from uuid import uuid4
                token = uuid4().hex.encode("ascii")
                payload = expansion_mime(operation.text, operation.rich_html,
                                     image_only=operation.image_only,
                                     web_html_only=operation.teams_web_html)
                payload.setData("application/x-aurora-expansion", token)
                clipboard.setMimeData(payload)
                lease = ClipboardLease(
                    operation.candidate.identifier, operation.verify_original,
                    payload.text(), token, self._clipboard_sequence())
                operation.lease = self._clipboard_lease = lease
                self._clipboard_pending = True
                operation.verify_original = None
                if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(lease):
                    raise ValueError("Foco ou clipboard mudou antes da colagem.")
                operation.stage = "sent"
                paste_clipboard()
                self._expansion_sent(operation)
                return
            if changed and selected != operation.verify_marker:
                raise ValueError("A seleção copiada não corresponde ao atalho; colagem cancelada.")
            if monotonic() < operation.deadline:
                QTimer.singleShot(20, lambda op=operation: self._confirm_keyboard_verification(op))
                return
            raise ValueError("O aplicativo não confirmou a cópia exata do atalho; nenhum texto foi substituído.")
        except Exception as exc:
            self._finish_expansion(operation, f"Não foi possível expandir: {exc}")

    def _restore_keyboard_probe(self, operation):
        """Restaura a área de transferência apenas se ainda for nossa cópia."""
        original = operation.verify_original
        if original is None:
            return
        try:
            clipboard = QApplication.clipboard()
            sequence = self._clipboard_sequence()
            old = operation.verify_sequence
            # Um único Ctrl+C pode produzir no máximo duas revisões ao
            # disponibilizar formatos diferentes. Não sobrescrever cópia nova.
            copied = (sequence is not None and old is not None
                      and 0 < sequence - old <= 2)
            marker = (sequence == old and clipboard.text() == operation.verify_marker)
            if marker or (copied and self._candidate_valid(operation.candidate)):
                clipboard.setMimeData(original)
            if self._candidate_valid(operation.candidate):
                collapse_selection_to_end()
        except (OSError, ValueError, RuntimeError):
            pass
        finally:
            operation.verify_original = None
            if self._clipboard_lease is operation.lease and operation.lease is not None:
                self._clipboard_lease = None
                self._clipboard_pending = False

    def _paste_verified_selection(self, operation):
        """Confirma que o Teams ainda seleciona somente o atalho antes do Ctrl+V."""
        if self._expansion_operation is not operation or operation.stage != "selected":
            return
        try:
            if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(operation.lease):
                raise ValueError("Foco, digitação ou clipboard alterado após selecionar o atalho.")
            before = operation.before
            begin, end = before.shortcut_range(operation.candidate.shortcut)
            selected = self._edit_snapshot(accessibility=bool(before.identity))
            if (selected is None or selected.context != before.context
                    or selected.identity != before.identity
                    or selected.text != before.text):
                raise ValueError("O editor alterou o campo ou seu conteúdo antes da colagem.")
            if (selected.start, selected.end) != (begin, end):
                # WebView ainda pode estar exibindo o caret original mesmo após
                # Select() ter retornado. Somente este estado *inalterado* admite
                # mais uma consulta. Outra seleção, texto ou identidade aborta.
                if ((selected.start, selected.end) == (before.start, before.end)
                        and monotonic() < operation.deadline):
                    QTimer.singleShot(10, lambda op=operation: self._paste_verified_selection(op))
                    return
                if supports_verified_copy(operation.candidate.context):
                    self._begin_keyboard_verification(operation, select_keyboard=False)
                    return
                raise ValueError(
                    "O editor não confirmou a seleção do atalho; nenhum texto foi colado.")
            if not self._candidate_valid(operation.candidate) or not self._owns_clipboard(operation.lease):
                raise ValueError("O contexto mudou durante a verificação da seleção.")
            operation.stage = "sent"
            paste_clipboard()
            self._expansion_sent(operation)
        except ContextUnavailable as exc:
            # Consulta momentaneamente indisponível: repetir apenas a leitura.
            # Nunca reenviar seleção nem Ctrl+V enquanto não houver prova.
            if (monotonic() < operation.deadline
                    and self._candidate_valid(operation.candidate)
                    and self._owns_clipboard(operation.lease)):
                QTimer.singleShot(10, lambda op=operation: self._paste_verified_selection(op))
            elif (self._candidate_valid(operation.candidate)
                  and supports_verified_copy(operation.candidate.context)):
                try:
                    self._begin_keyboard_verification(operation, select_keyboard=False)
                except Exception as error:
                    self._finish_expansion(operation, f"Não foi possível expandir: {error}")
            else:
                self._finish_expansion(operation, f"Não foi possível expandir: {exc}")
        except Exception as exc:
            self._finish_expansion(operation, f"Não foi possível expandir: {exc}")

    def _expansion_sent(self, operation):
        # O som informa somente que Ctrl+V foi enviado, não comprova
        # aceitação ou upload no editor externo.
        if (operation.image_count or operation.before is None
                or operation.before.identity):
            operation.feedback_played = True
            self._play_confirmation()
        operation.deadline = monotonic() + 1.5
        QTimer.singleShot(10, lambda op=operation: self._confirm_expansion(op))

    @staticmethod
    def _normal_text(text):
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _confirm_expansion(self, operation):
        if self._expansion_operation is not operation:
            return
        try:
            if not self._candidate_valid(operation.candidate):
                raise ValueError("Contexto alterado após envio; resultado não confirmado.")
            before = operation.before
            if before is None:
                self._finish_expansion(operation, "Expansão enviada; este campo não permite confirmar o resultado.")
                return
            snapshot = self._edit_snapshot(accessibility=bool(before.identity))
            if snapshot is not None and snapshot.identity != before.identity:
                raise ValueError("O campo de edição mudou; resultado não confirmado.")
            begin, end = before.shortcut_range(operation.candidate.shortcut)
            expected = self._normal_text(before.replace(begin, end, operation.text))
            prefix = self._normal_text(utf16_slice(before.text, 0, begin) + operation.text)
            if operation.image_count and snapshot is not None:
                rich_expected = self._normal_text(before.replace(begin, end, operation.document_text))
                if self._normal_text(snapshot.text) == rich_expected:
                    expected = rich_expected
                    prefix = self._normal_text(utf16_slice(before.text, 0, begin) + operation.document_text)
                    # The test editor can confirm image resources. External
                    # accessibility text alone cannot prove a rendered image.
                    operation.images_confirmed = (self.isActiveWindow() and self.focusWidget() is self.test_box)
                    operation.text = operation.document_text
                    operation.cursor_prefix = operation.document_cursor_prefix
            if (snapshot is None or self._normal_text(snapshot.text) != expected or snapshot.start != snapshot.end
                    or self._normal_text(utf16_slice(snapshot.text, 0, snapshot.start)) != prefix):
                if monotonic() < operation.deadline:
                    QTimer.singleShot(10, lambda op=operation: self._confirm_expansion(op))
                    return
                raise ValueError("Colagem não confirmada; nenhum reenvio será feito.")
            operation.lease.consumed = True
            if operation.left_moves:
                caret_prefix = utf16_slice(before.text, 0, begin) + operation.cursor_prefix
                self._set_caret(snapshot, prefix_offset(snapshot.text, caret_prefix))
                operation.stage = "moving"
                operation.deadline = monotonic() + 0.75
                QTimer.singleShot(10, lambda op=operation: self._confirm_cursor(op))
            else:
                self._expansion_succeeded(operation)
        except Exception as exc:
            if (isinstance(exc, ContextUnavailable) and monotonic() < operation.deadline
                    and self._candidate_valid(operation.candidate)):
                QTimer.singleShot(10, lambda op=operation: self._confirm_expansion(op))
            else:
                self._finish_expansion(operation, f"Não foi possível expandir: {exc}")

    def _confirm_cursor(self, operation):
        if self._expansion_operation is not operation:
            return
        try:
            self._check_cursor(operation)
        except Exception as exc:
            if (isinstance(exc, ContextUnavailable) and monotonic() < operation.deadline
                    and self._candidate_valid(operation.candidate)):
                QTimer.singleShot(10, lambda op=operation: self._confirm_cursor(op))
            else:
                self._finish_expansion(operation, f"Texto inserido; cursor não confirmado: {exc}")

    def _check_cursor(self, operation):
        if not self._candidate_valid(operation.candidate):
            self._finish_expansion(operation, "Texto inserido; contexto mudou antes de confirmar o cursor.")
            return
        snapshot = self._edit_snapshot(accessibility=bool(operation.before.identity))
        begin, end = operation.before.shortcut_range(operation.candidate.shortcut)
        prefix = self._normal_text(utf16_slice(operation.before.text, 0, begin) + operation.cursor_prefix)
        if (snapshot is not None and snapshot.start == snapshot.end
                and snapshot.identity == operation.before.identity
                and self._normal_text(snapshot.text) == self._normal_text(operation.before.replace(begin, end, operation.text))
                and self._normal_text(utf16_slice(snapshot.text, 0, snapshot.start)) == prefix):
            self._expansion_succeeded(operation)
        elif monotonic() < operation.deadline:
            QTimer.singleShot(10, lambda op=operation: self._confirm_cursor(op))
        else:
            self._finish_expansion(operation, "Texto inserido; posição do cursor não confirmada.")

    def _expansion_succeeded(self, operation):
        operation.stage = "confirmed"
        message = f"Expandido: {operation.candidate.shortcut}"
        if operation.image_count and not operation.images_confirmed:
            message += " · Imagens não verificadas no destino. Se necessário, use Copiar para outro aplicativo no editor."
        self.statusBar().showMessage(message, 10000 if operation.image_count else 3000)
        if not operation.feedback_played:
            operation.feedback_played = True
            self._play_confirmation()
        self._finish_expansion(operation)

    def _clear_failed_selection(self, operation):
        """Desfaz somente a seleção residual de um atalho cuja colagem falhou.

        O Teams/Chromium pode aceitar a seleção UIA e rejeitar Ctrl+V.
        Não apagar nem digitar nada, e nunca mover um cursor que o usuário
        tenha alterado depois da tentativa.
        """
        if (operation is None or operation.before is None
                or operation.stage not in {"selected", "sent"}
                or not operation.before.identity
                or not self._candidate_valid(operation.candidate)):
            return
        try:
            begin_end = operation.before.shortcut_range(operation.candidate.shortcut)
            if begin_end is None:
                return
            begin, end = begin_end
            current = self._edit_snapshot(accessibility=True)
            if (current is not None and current.context == operation.before.context
                    and current.identity == operation.before.identity
                    and current.text == operation.before.text
                    and (current.start, current.end) == (begin, end)):
                self._set_caret(current, end)
        except (ContextUnavailable, ValueError, OSError):
            # Falha no provedor de acessibilidade: não arriscar outra edição.
            pass

    def _finish_expansion(self, operation, message=""):
        if operation is not None and self._expansion_operation is not operation:
            return
        if operation is not None and operation.verify_original is not None:
            self._restore_keyboard_probe(operation)
        if message:
            self._clear_failed_selection(operation)
            self.statusBar().showMessage(message, 8000)
        if operation and operation.lease:
            lease = operation.lease
            sent = operation.stage in {"sent", "moving", "confirmed"}
            delay = 1450 if sent and (operation.image_count or not lease.consumed) else 0
            QTimer.singleShot(delay, lambda saved=lease: self._restore_clipboard(saved))
        self._active_candidate = None
        self._expansion_operation = None
        self._resume_queued_expansion()

    def _resume_queued_expansion(self):
        lease = self._clipboard_lease
        if lease and not lease.consumed and self._owns_clipboard(lease):
            return
        candidate, self._queued_candidate = self._queued_candidate, None
        if candidate is not None:
            QTimer.singleShot(0, lambda c=candidate: self._expand_global(c))

    def _restore_clipboard(self, lease: ClipboardLease):
        if self._clipboard_lease is not lease:
            return
        if self._owns_clipboard(lease):
            QApplication.clipboard().setMimeData(lease.original)
        self._clipboard_lease = None
        self._clipboard_pending = False
        if not self._quitting:
            self._resume_queued_expansion()

    def closeEvent(self, event):
        if not self._confirm_change():
            self._quitting = False
            event.ignore()
            return
        if self.tray_icon is not None and not self._quitting:
            event.ignore()
            self._hide_to_tray()
            return
        if not self._prepare_updates_shutdown():
            event.ignore()
            return
        self.hotkeys.stop()
        if self._focus_monitor is not None:
            self._focus_monitor.stop()
        if self._clipboard_lease is not None:
            self._restore_clipboard(self._clipboard_lease)
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.store.close()
        super().closeEvent(event)
