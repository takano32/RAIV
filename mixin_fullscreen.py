from __future__ import annotations

import os

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from constants import BORDERLESS_FULLSCREEN_OVERSCAN


class FullscreenMixin:
    def is_app_fullscreen(self) -> bool:
        return self.borderless_fullscreen

    def toggle_fullscreen(self) -> None:
        if self.is_app_fullscreen():
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _exit_fullscreen(self) -> None:
        self._show_fullscreen_cursor()
        self.borderless_fullscreen = False
        self.fullscreen_enforce_pending = False
        self.setWindowState(Qt.WindowNoState)
        self.setWindowFlags(self.before_fullscreen_flags)
        if self.before_fullscreen_geometry.isValid():
            self.setGeometry(self.before_fullscreen_geometry)
        self.setStyleSheet("")
        self.show()
        restore_state = self.before_fullscreen_state & ~Qt.WindowFullScreen
        if restore_state != Qt.WindowNoState:
            self.setWindowState(restore_state)
        if self.pin_button.isChecked():
            self.attach_side_panel_to_splitter(visible=True)
        else:
            self.detach_side_panel_for_overlay(visible=False)

    def _enter_fullscreen(self) -> None:
        self.before_fullscreen_geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.before_fullscreen_flags = self.windowFlags()
        self.before_fullscreen_state = self.windowState() & ~Qt.WindowFullScreen
        pinned = self.pin_button.isChecked()
        self.side_panel_visible_before_fullscreen = self.side_panel.isVisible() or pinned
        if pinned:
            self.attach_side_panel_to_splitter(visible=True)
        else:
            self.detach_side_panel_for_overlay(visible=False)
            self.side_panel.hide()
            self.side_panel.setParent(None)
        self.borderless_fullscreen = True
        self.setWindowState(Qt.WindowNoState)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setStyleSheet("QMainWindow { background: #000000; }")
        target = self.borderless_fullscreen_geometry()
        if target.isValid():
            self.setGeometry(target)
        self.show()
        if pinned:
            self.attach_side_panel_to_splitter(visible=True)
        else:
            self.side_panel.setParent(self)
            self.side_panel.installEventFilter(self)
            self.side_panel_overlay = True
            self.position_overlay_side_panel()
        self.raise_()
        self.request_borderless_fullscreen_enforce()
        self._apply_fullscreen_cursor()

    def borderless_fullscreen_geometry(self) -> QRect:
        screen = self.screen() or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return QRect()
        geometry = QRect(screen.geometry())
        if os.name == "nt":
            geometry.adjust(-BORDERLESS_FULLSCREEN_OVERSCAN, -BORDERLESS_FULLSCREEN_OVERSCAN,
                            BORDERLESS_FULLSCREEN_OVERSCAN, BORDERLESS_FULLSCREEN_OVERSCAN)
        return geometry

    def request_borderless_fullscreen_enforce(self) -> None:
        if not self.is_app_fullscreen() or self.fullscreen_enforce_pending:
            return
        self.fullscreen_enforce_pending = True
        QTimer.singleShot(0, self.enforce_borderless_fullscreen)

    def enforce_borderless_fullscreen(self) -> None:
        self.fullscreen_enforce_pending = False
        if not self.is_app_fullscreen():
            return
        state = self.windowState()
        if state & Qt.WindowFullScreen:
            self.setWindowState(state & ~Qt.WindowFullScreen)
        desired_flags = Qt.Window | Qt.FramelessWindowHint
        changed_flags = self.windowFlags() != desired_flags
        if changed_flags:
            self.setWindowFlags(desired_flags)
        target = self.borderless_fullscreen_geometry()
        if target.isValid() and self.geometry() != target:
            self.setGeometry(target)
        if changed_flags or not self.isVisible():
            self.show()
        if self.side_panel_overlay:
            self.position_overlay_side_panel()

    def _apply_fullscreen_cursor(self) -> None:
        if self.is_app_fullscreen() and self.hide_cursor_fullscreen_check.isChecked() and not self.fullscreen_cursor_hidden:
            QApplication.setOverrideCursor(QCursor(Qt.BlankCursor))
            self.fullscreen_cursor_hidden = True

    def _show_fullscreen_cursor(self) -> None:
        if self.fullscreen_cursor_hidden:
            QApplication.restoreOverrideCursor()
            self.fullscreen_cursor_hidden = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.layout_viewer_host()
        if self.side_panel_overlay:
            self.position_overlay_side_panel()
        elif hasattr(self, "splitter"):
            self._apply_splitter_panel_width()
        self.request_borderless_fullscreen_enforce()
