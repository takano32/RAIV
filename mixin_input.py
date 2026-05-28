from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCursor

from bindings import modifier_value
from constants import SIDE_PANEL_HIDE_DELAY_MS, THUMBNAIL_HIDE_DELAY_MS, THUMBNAIL_RESIZE_GRIP


class InputMixin:
    # ── drag and drop ─────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls:
            event.acceptProposedAction()
            self.activateWindow()
            self.raise_()
            from pathlib import Path
            self.open_path_deferred(Path(urls[0].toLocalFile()))

    # ── keyboard ──────────────────────────────────────────────────────────

    def matching_key_action(self, event) -> str | None:
        key = event.key()
        modifiers = modifier_value(event.modifiers())
        signature = (key, modifiers)
        if signature in self.duplicate_keyboard_bindings:
            return None
        for action_id, bindings in self.config_data.key_bindings.items():
            binding = bindings.get("keyboard") if isinstance(bindings, dict) else None
            if not binding:
                continue
            if int(binding.get("key", 0)) == key and int(binding.get("modifiers", 0)) == modifiers:
                return action_id
        return None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Space:
            self.queue_page_steps(1)
        elif event.key() == Qt.Key_Backspace:
            self.queue_page_steps(-1)
        else:
            action_id = self.matching_key_action(event)
            if action_id:
                self.perform_action(action_id)
            else:
                super().keyPressEvent(event)

    # ── action dispatch ───────────────────────────────────────────────────

    def perform_action(self, action_id: str) -> None:
        actions = {
            "open_image": self.open_image_dialog,
            "open_folder": self.open_folder_dialog,
            "next_page": lambda: self.queue_page_steps(1),
            "previous_page": lambda: self.queue_page_steps(-1),
            "last_page": self.show_last_image,
            "first_page": self.show_first_image,
            "toggle_fullscreen": self.toggle_fullscreen,
            "toggle_thumbnail_panel": self.toggle_thumbnail_panel,
            "toggle_side_panel": self.toggle_side_panel,
            "toggle_compare": self.toggle_compare_mode,
            "actual_size": self.viewer.zoom_to_actual_size,
            "fit_view": self.viewer.reset_display_state,
            "rotate_right": lambda: self.viewer.rotate_display(90),
            "rotate_left": lambda: self.viewer.rotate_display(-90),
            "flip_horizontal": lambda: self.viewer.flip_display(True),
            "flip_vertical": lambda: self.viewer.flip_display(False),
        }
        action = actions.get(action_id)
        if action is not None:
            action()

    # ── event filter ──────────────────────────────────────────────────────

    def eventFilter(self, watched, event) -> bool:
        if watched is getattr(self, "viewer_host", None):
            if event.type() == QEvent.Resize:
                self.layout_viewer_host()

        thumbnail_panel = getattr(self, "thumbnail_panel", None)
        thumbnail_list = getattr(self, "thumbnail_list", None)
        thumbnail_viewport = thumbnail_list.viewport() if thumbnail_list is not None else None
        if watched in {thumbnail_panel, thumbnail_list, thumbnail_viewport}:
            if event.type() in {QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease}:
                global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else QCursor.pos()
                panel_pos = thumbnail_panel.mapFromGlobal(global_pos)
                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and panel_pos.y() <= THUMBNAIL_RESIZE_GRIP:
                    self.thumbnail_resizing = True
                    thumbnail_panel.setCursor(Qt.SizeVerCursor)
                    return True
                if event.type() == QEvent.MouseMove:
                    if self.thumbnail_resizing:
                        import time
                        host_pos = self.viewer_host.mapFromGlobal(global_pos)
                        self.thumbnail_height = self.clamped_thumbnail_height(self.viewer_host.height() - host_pos.y())
                        self.config_data.thumbnail_height = self.thumbnail_height
                        self.config_data.thumbnail_size = self.thumbnail_icon_size()
                        self.thumbnail_hide_suppressed_until = time.monotonic() + 0.45
                        self.layout_viewer_host()
                        return True
                    thumbnail_panel.setCursor(Qt.SizeVerCursor if panel_pos.y() <= THUMBNAIL_RESIZE_GRIP else Qt.ArrowCursor)
                if event.type() == QEvent.MouseButtonRelease and self.thumbnail_resizing:
                    import time
                    self.thumbnail_resizing = False
                    thumbnail_panel.unsetCursor()
                    self.thumbnail_hide_suppressed_until = time.monotonic() + 0.45
                    self.thumbnail_resize_refresh_timer.start(1)
                    self.persist_config()
                    return True
            if event.type() in {QEvent.Leave, QEvent.Hide} and not self.thumbnails_pinned():
                QTimer.singleShot(THUMBNAIL_HIDE_DELAY_MS, self.hide_thumbnail_overlay)
            elif event.type() == QEvent.MouseMove and not self.thumbnails_pinned():
                self.show_thumbnail_overlay()

        side_panel = getattr(self, "side_panel", None)
        if watched is side_panel:
            if self.side_panel_overlay and not self.pin_button.isChecked():
                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and event.position().x() <= 18:
                    self.overlay_resizing = True
                    side_panel.setCursor(Qt.SizeHorCursor)
                    return True
                if event.type() == QEvent.MouseMove:
                    if self.overlay_resizing:
                        local = self.mapFromGlobal(event.globalPosition().toPoint())
                        right = side_panel.geometry().right()
                        self.side_panel_width = self.clamped_side_panel_width(right - local.x() + 1)
                        self.config_data.side_panel_width = self.side_panel_width
                        self.position_overlay_side_panel()
                        return True
                    side_panel.setCursor(Qt.SizeHorCursor if event.position().x() <= 18 else Qt.ArrowCursor)
                if event.type() == QEvent.MouseButtonRelease and self.overlay_resizing:
                    self.overlay_resizing = False
                    side_panel.unsetCursor()
                    self.persist_config()
                    return True
                if event.type() in {QEvent.Leave, QEvent.Hide}:
                    QTimer.singleShot(SIDE_PANEL_HIDE_DELAY_MS, self.hide_overlay_side_panel_if_needed)

        elif watched is self.viewer and event.type() == QEvent.MouseMove:
            if self.thumbnails_enabled() and not self.thumbnails_pinned():
                trigger_margin = min(self.viewer.height(), self.thumbnail_panel_height())
                if event.position().y() >= self.viewer.height() - trigger_margin:
                    self.show_thumbnail_overlay()
                elif self.thumbnail_overlay_visible and not self.is_cursor_over_thumbnail_panel():
                    self.hide_thumbnail_overlay()
            if not self.pin_button.isChecked():
                trigger_width = min(self.clamped_side_panel_width(), max(1, self.viewer.width() // 2))
                x = event.position().x()
                if x >= self.viewer.width() - trigger_width:
                    self.show_side_panel()
                elif self.side_panel_overlay and self.side_panel.isVisible() and self.should_hide_overlay_panel():
                    self.side_panel.hide()
                    self.persist_config()
            if self.is_app_fullscreen() and self.fullscreen_cursor_hidden:
                self._show_fullscreen_cursor()
                QTimer.singleShot(1200, self._apply_fullscreen_cursor)

        return super().eventFilter(watched, event)
