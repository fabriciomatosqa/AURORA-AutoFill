"""Ações de produtividade desacopladas da janela principal.

Nenhuma edição automática é enviada se o alvo Windows mudou depois do
diálogo, nem se o sistema não consegue confirmar o foco do aplicativo.
"""
from __future__ import annotations

import ctypes
import sys
from html import escape
from time import monotonic
from PySide6.QtCore import QTimer, QRect
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox, QToolTip

from .core import render_snippet
from .smart_templates import fields_in, fill_fields, has_steps, action_steps
from .productivity_widgets import FieldsDialog, QuickSearchDialog, UsageStatisticsDialog
from .formatting import render_rich_html, has_rich_formatting
from .clipboard_content import expansion_mime
from .hotkeys import paste_clipboard, replace_shortcut
from .windows_context import capture_focus, capture_edit, ContextUnavailable
from .wayland_input import is_wayland_session


def same_windows_focus(context, *, control=True):
    if sys.platform != "win32" or not getattr(context, "window", None):
        return False
    current = capture_focus()
    return (current.window == context.window and
            (not control or not context.control or current.control == context.control))


def restore_target(context):
    if sys.platform != "win32" or not getattr(context, "window", None):
        return False
    if same_windows_focus(context):
        return True
    try:
        ctypes.windll.user32.SetForegroundWindow(context.window)
        return same_windows_focus(context)
    except (OSError, AttributeError, ValueError):
        return False


def safe_clipboard_text(raw: str) -> str:
    return raw.replace("{{tab}}", "\t").replace("{{enter}}", "\n").replace(
        "{{espera:250}}", "")


class ProductivityMixin:
    def _show_linux_setup(self):
        from .linux_setup_ui import LinuxSetupDialog
        LinuxSetupDialog(self).exec()

    def _show_statistics(self):
        dlg = UsageStatisticsDialog(self.store, self)
        dlg.exec()

    def _open_global_search(self):
        if getattr(self, "_quitting", False) or getattr(self, "_quick_picker_open", False):
            return
        QToolTip.hideText()
        self._quick_picker_open = True
        context = capture_focus()
        try:
            dlg = QuickSearchDialog(self.store, self)
            if dlg.exec() != dlg.Accepted or dlg.selected_snippet is None:
                return
            self._launch_smart_snippet(dlg.selected_snippet, context, from_shortcut=None)
        finally:
            self._quick_picker_open = False

    def _hide_suggestion_popup(self):
        if hasattr(self, "_slash_popup"):
            self._slash_popup.dismiss()
        self._slash_prefix = ""
        self._slash_context = None
        if hasattr(self, "hotkeys"):
            self.hotkeys.set_suggestion_visible("", None)

    def _check_suggestions_focus(self):
        if not getattr(self, "_slash_prefix", ""):
            return
        if (getattr(self, "_quitting", False) or
                not self._slash_popup.isVisible() or
                capture_focus() != self._slash_context or
                not getattr(self, "_hotkeys_enabled", False)):
            self._hide_suggestion_popup()

    def _show_suggestions(self, state):
        # Signal is queued: every payload contains the original focus. An old
        # slash typed in a previous window must never reopen the menu.
        if not isinstance(state, tuple) or len(state) != 2:
            return
        prefix, context = state
        if (not prefix or sys.platform != "win32" or
                not self.preferences.get("suggest_shortcuts", False) or
                getattr(self, "_quitting", False) or
                not getattr(self, "_hotkeys_enabled", False) or
                not getattr(context, "window", None) or
                not getattr(context, "control", None) or
                capture_focus() != context or
                (self.isActiveWindow() and self.focusWidget() is not self.test_box)):
            self._hide_suggestion_popup()
            return
        lowered = prefix.casefold()
        matches = [(shortcut, title) for shortcut, title in self._suggestion_catalog
                   if shortcut.casefold().startswith(lowered)][:80]
        if not matches:
            self._hide_suggestion_popup()
            return
        self._slash_popup.present(prefix, matches)
        self._slash_prefix, self._slash_context = prefix, context
        self.hotkeys.set_suggestion_visible(prefix, context)

    def _navigate_suggestions(self, event):
        if not isinstance(event, tuple) or len(event) != 3:
            return
        action, prefix, context = event
        if (prefix != self._slash_prefix or context != self._slash_context or
                capture_focus() != context or
                not self._slash_popup.isVisible()):
            self._hide_suggestion_popup()
            return
        if action == "up":
            self._slash_popup.navigate(-1)
        elif action == "down":
            self._slash_popup.navigate(1)
        elif action == "escape":
            self.hotkeys.dismiss_suggestions(prefix, context)
            self._hide_suggestion_popup()
        elif action in ("tab", "enter"):
            shortcut = self._slash_popup.current_shortcut()
            if not shortcut:
                return
            candidate = self.hotkeys.choose_suggestion(prefix, shortcut, context)
            self._hide_suggestion_popup()
            if candidate is not None:
                self._expand_global(candidate)

    def _launch_smart_snippet(self, snippet, context, *, from_shortcut):
        fields = fields_in(snippet.content)
        answers = {}
        if fields:
            dialog = FieldsDialog(snippet.content, self)
            if dialog.exec() != dialog.Accepted:
                if from_shortcut:
                    self.statusBar().showMessage("Formulário cancelado. Atalho preservado.", 5000)
                return
            answers = dialog.values()
        source_clipboard = QApplication.clipboard().text()
        try:
            raw = fill_fields(snippet.content, answers)
            rendered = render_snippet(raw, source_clipboard)
            rich = ""
            if (not has_steps(raw) and snippet.rich_content
                    and has_rich_formatting(snippet.rich_content)):
                source_html = fill_fields(snippet.rich_content, answers, html=True)
                rich = render_rich_html(source_html, source_clipboard)
            if rich and ("{{campo:" in rich or "{{escolha:" in rich):
                # Qt pode dividir um token entre spans ao aplicar formatação.
                # Nessa situação preferir o texto preenchido, nunca colar um
                # token bruto no documento final.
                rich = ""
            if has_steps(raw):
                stages = action_steps(raw)
                prompt = ("Este comando irá enviar texto, Tab/Enter e pequenas esperas "
                          "para o aplicativo anterior. Confirme somente se os campos "
                          "estiverem corretos e NÃO forem sensíveis.\n\n"
                          "No Windows será executado apenas se o foco anterior "
                          "puder ser confirmado. Em outros sistemas será copiado "
                          "como texto simples para colagem manual.")
                if QMessageBox.question(
                    self, "Confirmar automação em etapas", prompt,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes:
                    return
                # Resolve variáveis em cada trecho sem perder a sequência.
                stages = tuple(
                    (step.kind, render_snippet(step.value, source_clipboard).text
                     if step.kind == "text" else step.value)
                    for step in stages)
                if sys.platform != "win32":
                    flattened = "".join(str(v) if kind == "text" else
                                        "\t" if kind == "tab" else "\n" if kind == "enter" else ""
                                        for kind, v in stages)
                    QApplication.clipboard().setText(flattened)
                    self.statusBar().showMessage("Automação exige destino verificável; texto copiado para colar.", 8500)
                    return
                self._perform_staged_command(snippet, stages, context, from_shortcut)
                return
            if not rendered.text:
                return
            payload = expansion_mime(rendered.text, rich)
            # O fallback manual jamais apaga o atalho digitado na ausência de
            # verificação do campo de destino.
            QApplication.clipboard().setMimeData(payload)
            if sys.platform == "win32" and context.window and context.window != int(self.winId()):
                QTimer.singleShot(
                    160,
                    lambda c=context, text=rendered.text, item=snippet, src=from_shortcut:
                    self._safe_paste_selected(c, text, item, src))
            else:
                self.statusBar().showMessage(
                    "Comando preparado na área de transferência. Cole com Ctrl+V.", 8500)
        except (ValueError, OSError, ContextUnavailable) as error:
            QMessageBox.warning(self, "Comando não inserido", str(error))

    def _safe_paste_selected(self, context, text, snippet, shortcut):
        if QApplication.clipboard().text() != text:
            self.statusBar().showMessage("Clipboard mudou; nenhuma colagem automática.", 7500)
            return
        if not restore_target(context):
            self.statusBar().showMessage("Destino alterado: conteúdo copiado, cole com Ctrl+V.", 8500)
            return
        try:
            if shortcut:
                snapshot = capture_edit(context, accessibility=True)
                if snapshot is None or snapshot.shortcut_range(shortcut) is None:
                    raise ValueError("Atalho não verificável após o formulário. Copie com Ctrl+V.")
                replace_shortcut(len(shortcut))
            else:
                paste_clipboard()
            self.statusBar().showMessage(
                "Colagem acionada; confirme o resultado no aplicativo de destino.", 7000)
            # Não contar como sucesso confirmado sem retorno do aplicativo.
        except (OSError, ValueError, ContextUnavailable) as error:
            self.statusBar().showMessage(f"Nenhuma substituição automática: {error}", 9000)

    def _perform_staged_command(self, snippet, stages, context, shortcut):
        if not stages or stages[0][0] != "text" or not stages[0][1]:
            self.statusBar().showMessage(
                "Automação precisa começar por texto; nada foi enviado.", 7500)
            return
        self._stage_state = {
            "context": context, "steps": list(stages), "index": 0, "shortcut": shortcut,
            "snippet": snippet.id, "started": monotonic(), "expected_focus": True,
        }
        QTimer.singleShot(180, self._next_stage)

    def _next_stage(self):
        state = getattr(self, "_stage_state", None)
        if state is None:
            return
        if getattr(self, "_quitting", False):
            self._abort_steps("Aplicativo encerrado.")
            return
        context = state["context"]
        if state["index"] == 0:
            if not restore_target(context):
                self._abort_steps("O foco de destino mudou; nenhuma etapa enviada.")
                return
            if state["shortcut"]:
                try:
                    snapshot = capture_edit(context, accessibility=True)
                    if snapshot is None or snapshot.shortcut_range(state["shortcut"]) is None:
                        self._abort_steps("Atalho não verificável; nenhuma etapa enviada.")
                        return
                except (ContextUnavailable, OSError, ValueError):
                    self._abort_steps("Não foi possível confirmar o campo; comando preservado.")
                    return
        elif not same_windows_focus(context, control=False):
            self._abort_steps("O aplicativo mudou durante a automação.")
            return
        if state["index"] >= len(state["steps"]):
            self.statusBar().showMessage("Etapas enviadas. Confira os campos antes de salvar.", 8000)
            self._stage_state = None
            return
        kind, value = state["steps"][state["index"]]
        state["index"] += 1
        try:
            if kind == "wait":
                QTimer.singleShot(int(value), self._next_stage)
                return
            if kind == "text":
                QApplication.clipboard().setText(value)
                if state["index"] == 1 and state["shortcut"]:
                    replace_shortcut(len(state["shortcut"]))
                else:
                    paste_clipboard()
            elif kind in ("tab", "enter"):
                from pynput.keyboard import Controller, Key
                Controller().tap(Key.tab if kind == "tab" else Key.enter)
            else:
                raise ValueError("Etapa não permitida.")
        except (OSError, ValueError, RuntimeError) as error:
            self._abort_steps(str(error))
            return
        QTimer.singleShot(160, self._next_stage)

    def _abort_steps(self, reason):
        self._stage_state = None
        self.statusBar().showMessage(f"Automação interrompida: {reason}", 9000)
