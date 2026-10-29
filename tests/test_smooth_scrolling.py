"""Regression tests for AURORA's animated mouse-wheel scrolling."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (QAbstractAnimation, QCoreApplication, QEvent,
                            QPoint, QPointF, Qt)
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QLabel,
                               QListWidget, QScrollArea, QTextEdit, QWidget)

from app.smooth_scrolling import SmoothWheelScroller, install_smooth_scrolling


def wheel(y=-120, *, x=0, pixel=None, modifiers=Qt.NoModifier):
    return QWheelEvent(
        QPointF(20, 20), QPointF(20, 20), pixel or QPoint(0, 0),
        QPoint(x, y), Qt.NoButton, modifiers, Qt.ScrollUpdate, False)


class SmoothScrollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = SmoothWheelScroller()
        self.widgets = []

    def tearDown(self):
        for widget in reversed(self.widgets):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.controller.deleteLater()
        self.app.processEvents()

    def scroll_area(self):
        area = QScrollArea()
        content = QWidget()
        content.setMinimumHeight(2400)
        area.setWidget(content)
        area.resize(280, 190)
        area.show()
        self.app.processEvents()
        self.assertGreater(area.verticalScrollBar().maximum(), 0)
        self.widgets.append(area)
        return area

    def test_mouse_wheel_has_intermediate_frames_and_reaches_target(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel()))
        anim = self.controller._animations[bar]
        self.assertEqual(anim.state(), QAbstractAnimation.Running)
        self.assertEqual(bar.value(), 0)
        QTest.qWait(45)
        self.assertGreater(bar.value(), 0)
        self.assertLess(bar.value(), self.controller._targets[bar])
        QTest.qWait(220)
        expected = self.controller.PIXELS_PER_LINE * max(
            1, min(5, self.app.wheelScrollLines()))
        self.assertEqual(bar.value(), expected)

    def test_consecutive_wheel_steps_accumulate_not_restart_at_zero(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel()))
        QTest.qWait(35)
        first_position = bar.value()
        self.assertGreater(first_position, 0)
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel()))
        QTest.qWait(220)
        delta = self.controller.PIXELS_PER_LINE * max(
            1, min(5, self.app.wheelScrollLines()))
        self.assertEqual(bar.value(), 2 * delta)
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel(120)))
        QTest.qWait(220)
        self.assertEqual(bar.value(), delta)

    def test_text_edit_and_lists_scroll_by_pixels(self):
        edit = QTextEdit()
        edit.resize(300, 180)
        edit.setPlainText("\n".join(f"Parágrafo {i}" for i in range(80)))
        edit.show()
        self.widgets.append(edit)
        self.app.processEvents()
        self.assertTrue(self.controller.eventFilter(edit.viewport(), wheel()))
        QTest.qWait(220)
        self.assertGreater(edit.verticalScrollBar().value(), 0)

        listing = QListWidget()
        listing.addItems([f"Atalho {i}" for i in range(45)])
        listing.resize(240, 170)
        listing.show()
        self.widgets.append(listing)
        self.app.processEvents()
        self.assertEqual(listing.verticalScrollMode(), QAbstractItemView.ScrollPerItem)
        self.assertTrue(self.controller.eventFilter(listing.viewport(), wheel()))
        self.assertEqual(listing.verticalScrollMode(), QAbstractItemView.ScrollPerPixel)
        QTest.qWait(220)
        self.assertGreater(listing.verticalScrollBar().value(), 0)

    def test_touchpad_precision_and_ctrl_wheel_remain_native(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        self.assertFalse(self.controller.eventFilter(
            area.viewport(), wheel(pixel=QPoint(0, -14))))
        self.assertFalse(self.controller.eventFilter(
            area.viewport(), wheel(modifiers=Qt.ControlModifier)))
        self.assertFalse(self.controller.eventFilter(
            area.viewport(), wheel(modifiers=Qt.ShiftModifier)))
        self.assertEqual(bar.value(), 0)
        self.assertNotIn(bar, self.controller._animations)

    def test_repeated_ticks_near_bottom_do_not_jump_past_animation(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum() - 20)
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel()))
        # The next tick arrives before the previous 20px animation ends.
        self.assertTrue(self.controller.eventFilter(area.viewport(), wheel()))
        self.assertLess(bar.value(), bar.maximum())
        QTest.qWait(220)
        self.assertEqual(bar.value(), bar.maximum())
        # Once at rest, the page may propagate further scroll events.
        self.assertFalse(self.controller.eventFilter(area.viewport(), wheel()))

    def test_manual_scrollbar_drag_cancels_animation(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        self.controller.eventFilter(area.viewport(), wheel())
        animation = self.controller._animations[bar]
        self.assertEqual(animation.state(), QAbstractAnimation.Running)
        bar.sliderPressed.emit()
        self.assertEqual(animation.state(), QAbstractAnimation.Stopped)
        bar.setValue(170)
        QTest.qWait(220)
        self.assertEqual(bar.value(), 170)

    def test_no_scroll_range_does_not_eat_wheel_event(self):
        area = QScrollArea()
        area.setWidget(QLabel("Pequeno"))
        area.resize(400, 250)
        area.show()
        self.widgets.append(area)
        self.app.processEvents()
        self.assertFalse(self.controller.eventFilter(area.viewport(), wheel()))

    def test_installation_is_idempotent_for_future_dialogs(self):
        old_controller = getattr(self.app, "_aurora_smooth_scrolling", None)
        a = install_smooth_scrolling(self.app)
        self.assertIs(a, install_smooth_scrolling(self.app))
        # Only discard the controller when this test installed it; the real
        # application owns its global filter for the rest of its lifetime.
        if old_controller is None:
            self.app.removeEventFilter(a)
            delattr(self.app, "_aurora_smooth_scrolling")
            a.deleteLater()


if __name__ == "__main__":
    unittest.main()
