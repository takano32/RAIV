from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from constants import SIDE_PANEL_HIDE_DELAY_MS, SIDE_PANEL_HIDE_GRACE_SEC, SIDE_PANEL_HIDE_MARGIN


class SidePanelMixin:
    def hide_side_panel(self) -> None:
        self.side_panel.hide()
        self.persist_config()

    def show_side_panel(self) -> None:
        if self.pin_button.isChecked():
            return
        if not self.side_panel.isVisible():
            self.overlay_hide_suppressed_until = time.monotonic() + SIDE_PANEL_HIDE_GRACE_SEC
            self.detach_side_panel_for_overlay(visible=True)
            self.side_panel.show()
            self.position_overlay_side_panel()
            self.side_panel.raise_()
            self.request_borderless_fullscreen_enforce()
            self.persist_config()

    def toggle_side_panel(self) -> None:
        self.pin_button.setChecked(not self.pin_button.isChecked())

    def is_cursor_over_side_panel(self) -> bool:
        if not self.side_panel.isVisible():
            return False
        local = self.side_panel.mapFromGlobal(QCursor.pos())
        return self.side_panel.rect().contains(local)

    def should_hide_overlay_panel(self) -> bool:
        if self.overlay_resizing or self.overlay_modal_guard or self.pin_button.isChecked() or not self.side_panel_overlay:
            return False
        if QApplication.activePopupWidget() is not None:
            return False
        if time.monotonic() < self.overlay_hide_suppressed_until:
            return False
        local = self.side_panel.mapFromGlobal(QCursor.pos())
        rect = self.side_panel.rect()
        if not rect.adjusted(-SIDE_PANEL_HIDE_MARGIN, 0, SIDE_PANEL_HIDE_MARGIN, 0).contains(local):
            return True
        if not rect.contains(local):
            return False
        return local.x() > SIDE_PANEL_HIDE_MARGIN

    def hide_overlay_side_panel_if_needed(self) -> None:
        if self.should_hide_overlay_panel():
            self.side_panel.hide()
            self.persist_config()

    def clamped_side_panel_width(self, width: int | None = None) -> int:
        total = max(1, self.splitter.width() if hasattr(self, "splitter") else self.width())
        maximum = max(1, total // 2)
        minimum = min(max(240, self.side_panel.minimumWidth()), maximum)
        value = int(self.side_panel_width if width is None else width)
        return max(minimum, min(value, maximum))

    def current_side_panel_width(self) -> int:
        if self.side_panel_overlay:
            return int(self.side_panel_width)
        sizes = self.splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self.side_panel_width = self.clamped_side_panel_width(sizes[1])
            return self.side_panel_width
        return self.clamped_side_panel_width()

    def _apply_splitter_panel_width(self) -> None:
        total = self.splitter.width() or sum(self.splitter.sizes()) or self.width()
        if total <= 0:
            return
        panel_width = self.clamped_side_panel_width()
        self.adjusting_splitter = True
        self.splitter.setSizes([max(1, total - panel_width), panel_width])
        self.adjusting_splitter = False

    def attach_side_panel_to_splitter(self, visible: bool = True) -> None:
        if self.side_panel_overlay:
            self.side_panel.hide()
            self.side_panel.setParent(None)
            self.splitter.addWidget(self.side_panel)
            self.side_panel.installEventFilter(self)
            self.side_panel_overlay = False
        self.side_panel.setVisible(visible)
        if visible:
            self._apply_splitter_panel_width()
            QTimer.singleShot(0, self._apply_splitter_panel_width)

    def detach_side_panel_for_overlay(self, visible: bool = False) -> None:
        if not self.side_panel_overlay:
            if not getattr(self, "initializing", False):
                self.side_panel_width = self.current_side_panel_width()
            self.config_data.side_panel_width = self.side_panel_width
            self.side_panel.hide()
            self.side_panel.setParent(self)
            self.side_panel.installEventFilter(self)
            self.side_panel_overlay = True
            self.adjusting_splitter = True
            self.splitter.setSizes([max(1, self.splitter.width()), 0])
            self.adjusting_splitter = False
        self.position_overlay_side_panel()
        self.side_panel.setVisible(visible)

    def position_overlay_side_panel(self) -> None:
        if not self.side_panel_overlay:
            return
        central = self.centralWidget().geometry()
        width = min(self.clamped_side_panel_width(), max(1, central.width() // 2))
        self.side_panel.setGeometry(central.right() - width + 1, central.top(), width, central.height())

    def on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self.adjusting_splitter or self.side_panel_overlay:
            return
        sizes = self.splitter.sizes()
        if len(sizes) < 2:
            return
        total = sum(sizes)
        max_panel = max(self.side_panel.minimumWidth(), total // 2)
        panel = min(sizes[1], max_panel)
        panel = max(self.side_panel.minimumWidth(), panel)
        if panel != sizes[1]:
            self.adjusting_splitter = True
            self.splitter.setSizes([max(1, total - panel), panel])
            self.adjusting_splitter = False
        self.side_panel_width = panel
        self.config_data.side_panel_width = panel
        self.persist_config()

    def on_side_panel_pin_changed(self, pinned: bool) -> None:
        self.pin_button.setText(self.tr_ui("固定中" if pinned else "自動表示"))
        if pinned:
            self.attach_side_panel_to_splitter(visible=True)
        else:
            keep_visible = self.is_cursor_over_side_panel()
            self.overlay_hide_suppressed_until = time.monotonic() + SIDE_PANEL_HIDE_GRACE_SEC
            self.detach_side_panel_for_overlay(visible=keep_visible)
            if self.side_panel.isVisible():
                self.side_panel.raise_()
        self.persist_config()
