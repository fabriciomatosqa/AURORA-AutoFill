"""Aurora appearance: recolor UI styles only, never saved rich text/HTML."""
from __future__ import annotations

import re
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES = ("light", "dark", "system")
# Keep the approved dark styles intact. Related colors share light palette roles;
# geometry and selectors continue to live in their original components.
_LIGHT_GROUPS = {
    "#f4f8fc": "#091426 #06152b #0c1b30 #0e2335",
    "#ffffff": "#152941 #10243a #11263c #112f41 #132338 #0c1d31 #0d2238",
    "#eaf2f8": "#0f1d31 #102338 #19364b #18394d #204558 #143345 #1b495c #1b3149 #17354c #1c334a #132d43 #17354b #1b3a51 #1c3b52",
    "#dceef3": "#28546a #184156 #203b55 #294a62 #245568 #28536a",
    "#e9eff4": "#162a3e #1a3042 #304d60",
    "#d9e6f2": "#24445f #31536b #365a71 #427084 #355d74 #385a70 #35506b #28586d #3a6270 #416777 #355168 #2b405a #38536b #2b4358 #28435e #243c55 #3b5365 #264459 #3b657c #41677a #3d7084",
    "#16324f": "#eaf4ff #f7fbff #effaff #f3f9ff #f5faff #f0feff #eaf7ff #ffffff #fff #e7f6ff #f0fbff #eaf5ff #ebfaff #e5f7ff #f2fcff #ecf8ff #eff8ff #eefaff",
    "#4f6b86": "#d2eafa #b8cde0 #a8bfd2 #8cacc0 #d4eafb #d4e9f7",
    "#657d91": "#7995ab #4b687b #58788f #46667c",
    "#00788a": "#79ead8 #91e1d6 #67e7d5 #59dfcf #65e7d1 #6adacc #68e3d0 #8cf1d7 #60aeb3 #4eb9b2 #2f8590 #7df0d9 #8ef7de #72e6d5 #a0f5e5 #479f9e #4c9baf #7cebd9 #2f7077 #81e9d9",
    "#00798a": "#2c6870 #257d80 #226878 #2c6d7a #255763 #255b63 #287281 #2e817c",
    "#8b2944": "#ffc0c8 #ffbecf #805064",
    "#fce9ed": "#552d47",
    "#8ce4d5": "#49d0ba #63dfc9 #55d6c0 #65e2ca",
    "#b0f0e4": "#8af2d9 #99f4e2 #a2f6e8",
    "#09283b": "#09283b #092437",
}
LIGHT_COLORS = {color: target for target, colors in _LIGHT_GROUPS.items() for color in colors.split()}
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
LIGHT_OVERRIDES = """
QListWidget::item:selected, QMenu::item:selected,
QComboBox QAbstractItemView::item:selected,
QPushButton:checked, QToolButton:checked { color: #ffffff; }
QFrame#fontToolbar QPushButton#fontTool:checked,
QFrame#fontToolbar QToolButton#fontTool:checked { color: #ffffff; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { selection-color: #ffffff; }
QToolTip { color: #16324f; }
QPushButton#headerButton { color: #f1fffd; }
"""


def current_theme() -> str:
    app = QApplication.instance()
    return (app.property("auroraTheme") or "dark") if app else "dark"


def ui_color(dark_color: str) -> QColor:
    return QColor(LIGHT_COLORS.get(dark_color.lower(), dark_color)
                  if current_theme() == "light" else dark_color)


def ui_style(dark_style: str) -> str:
    if current_theme() != "light":
        return dark_style
    converted = HEX.sub(lambda match: LIGHT_COLORS.get(match[0].lower(), match[0]), dark_style)
    return converted + LIGHT_OVERRIDES if "{" in dark_style else converted


def set_ui_style(widget, dark_style: str) -> None:
    widget._aurora_dark_style = dark_style
    widget.setStyleSheet(ui_style(dark_style))


def resolved_theme(preference: str, scheme) -> str:
    if preference in ("light", "dark"):
        return preference
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


class ThemeController(QObject):
    changed = Signal(str)

    def __init__(self, preference: str, parent=None):
        super().__init__(parent)
        self.preference = preference if preference in THEMES else "dark"
        QApplication.styleHints().colorSchemeChanged.connect(self.system_changed)
        self.apply()

    def set_preference(self, preference: str) -> None:
        self.preference = preference if preference in THEMES else "dark"
        self.apply()

    def system_changed(self, scheme) -> None:
        if self.preference == "system":
            self.apply(scheme)

    def apply(self, scheme=None) -> None:
        app = QApplication.instance()
        theme = resolved_theme(self.preference, QApplication.styleHints().colorScheme()
                               if scheme is None else scheme)
        app.setProperty("auroraTheme", theme)
        light = theme == "light"
        palette = QPalette()
        roles = {
            QPalette.Window: "#f4f8fc" if light else "#091426",
            QPalette.Base: "#ffffff" if light else "#152941",
            QPalette.AlternateBase: "#eaf2f8" if light else "#102338",
            QPalette.Button: "#eaf2f8" if light else "#1b3149",
            QPalette.Text: "#16324f" if light else "#f5faff",
            QPalette.WindowText: "#16324f" if light else "#eaf4ff",
            QPalette.ButtonText: "#16324f" if light else "#effaff",
            QPalette.PlaceholderText: "#4f6b86" if light else "#a8bfd2",
            QPalette.Highlight: "#00798a" if light else "#257d80",
            QPalette.HighlightedText: "#ffffff",
            QPalette.ToolTipBase: "#eaf2f8" if light else "#17354c",
            QPalette.ToolTipText: "#16324f" if light else "#ffffff",
        }
        for role, color in roles.items():
            palette.setColor(role, QColor(color))
        for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
            palette.setColor(QPalette.Disabled, role, QColor("#657d91" if light else "#7995ab"))
        app.setPalette(palette)
        # Includes independent popup/tool windows and already open color dialogs.
        # Only explicitly registered UI styles are changed; QTextDocument is untouched.
        from .icons import apply_icon
        for widget in app.allWidgets():
            if hasattr(widget, "_aurora_dark_style"):
                widget.setStyleSheet(ui_style(widget._aurora_dark_style))
            if hasattr(widget, "_aurora_icon"):
                name, color = widget._aurora_icon
                apply_icon(widget, name, color=color)
            widget.update()
        self.changed.emit(theme)
