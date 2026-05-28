from __future__ import annotations

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from constants import (
    THUMBNAIL_HIDE_DELAY_MS,
    THUMBNAIL_HIDE_GRACE_SEC,
    THUMBNAIL_HIDE_MARGIN,
    THUMBNAIL_MAX_HEIGHT,
    THUMBNAIL_MIN_HEIGHT,
    THUMBNAIL_RESIZE_GRIP,
)


class ThumbnailMixin:
    # ── panel construction ────────────────────────────────────────────────

    def build_thumbnail_panel(self) -> QWidget:
        panel = QWidget(self.viewer_host)
        panel.setObjectName("thumbnailPanel")
        panel.setAutoFillBackground(True)
        panel.setStyleSheet("#thumbnailPanel { background: palette(window); border-top: 1px solid palette(mid); }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 4, 6, 4)
        self.thumbnail_list = QListWidget(panel)
        self.thumbnail_list.setViewMode(QListView.IconMode)
        self.thumbnail_list.setFlow(QListView.LeftToRight)
        self.thumbnail_list.setWrapping(False)
        self.thumbnail_list.setMovement(QListView.Static)
        self.thumbnail_list.setResizeMode(QListView.Adjust)
        self.thumbnail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.thumbnail_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumbnail_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.thumbnail_list.setStyleSheet(
            "QListWidget::item:selected { border: 3px solid #2f80ff; background: rgba(47, 128, 255, 70); }"
            "QListWidget::item { margin: 2px; padding: 2px; }"
        )
        self.thumbnail_list.itemClicked.connect(self.on_thumbnail_clicked)
        layout.addWidget(self.thumbnail_list)
        return panel

    # ── metrics ───────────────────────────────────────────────────────────

    def thumbnail_panel_height(self) -> int:
        return self.clamped_thumbnail_height()

    def clamped_thumbnail_height(self, height: int | None = None) -> int:
        value = int(self.thumbnail_height if height is None else height)
        return max(THUMBNAIL_MIN_HEIGHT, min(THUMBNAIL_MAX_HEIGHT, value))

    def thumbnail_icon_size(self, height: int | None = None) -> int:
        return max(48, min(256, self.clamped_thumbnail_height(height) - 48))

    def thumbnails_enabled(self) -> bool:
        check = getattr(self, "thumbnail_enabled_check", None)
        return bool(check.isChecked() if check is not None else self.config_data.thumbnail_enabled)

    def thumbnails_pinned(self) -> bool:
        check = getattr(self, "thumbnail_pinned_check", None)
        return bool(check.isChecked() if check is not None else self.config_data.thumbnail_pinned)

    # ── layout ────────────────────────────────────────────────────────────

    def layout_viewer_host(self) -> None:
        if not hasattr(self, "viewer_host"):
            return
        rect = self.viewer_host.rect()
        if rect.isNull():
            return
        enabled = self.thumbnails_enabled()
        pinned = enabled and self.thumbnails_pinned()
        strip_height = self.thumbnail_panel_height() if enabled else 0
        if pinned:
            viewer_height = max(1, rect.height() - strip_height)
            self.viewer.setGeometry(0, 0, rect.width(), viewer_height)
            self.thumbnail_panel.setGeometry(0, viewer_height, rect.width(), strip_height)
            self.thumbnail_panel.show()
            self.thumbnail_overlay_visible = False
        else:
            self.viewer.setGeometry(rect)
            self.thumbnail_panel.setGeometry(0, max(0, rect.height() - strip_height), rect.width(), strip_height)
            self.thumbnail_panel.setVisible(enabled and self.thumbnail_overlay_visible)
            if self.thumbnail_panel.isVisible():
                self.thumbnail_panel.raise_()
        self.update_thumbnail_metrics()
        self.thumbnail_height = strip_height if enabled else self.thumbnail_height

    # ── overlay show/hide ─────────────────────────────────────────────────

    def show_thumbnail_overlay(self) -> None:
        if not self.thumbnails_enabled() or self.thumbnails_pinned():
            return
        if not self.thumbnail_overlay_visible:
            self.thumbnail_overlay_visible = True
            self.layout_viewer_host()
        self.thumbnail_panel.raise_()

    def hide_thumbnail_overlay(self) -> None:
        if self.thumbnails_pinned() or not self.thumbnail_overlay_visible:
            return
        if self.thumbnail_resizing or time.monotonic() < self.thumbnail_hide_suppressed_until:
            return
        if self.is_cursor_over_thumbnail_panel():
            return
        self.thumbnail_overlay_visible = False
        self.layout_viewer_host()

    def is_cursor_over_thumbnail_panel(self) -> bool:
        if not hasattr(self, "thumbnail_panel") or not self.thumbnail_panel.isVisible():
            return False
        from PySide6.QtGui import QCursor
        local = self.thumbnail_panel.mapFromGlobal(QCursor.pos())
        return self.thumbnail_panel.rect().adjusted(0, -THUMBNAIL_HIDE_MARGIN, 0, THUMBNAIL_HIDE_MARGIN).contains(local)

    # ── metrics update ────────────────────────────────────────────────────

    def update_thumbnail_metrics(self) -> None:
        if not hasattr(self, "thumbnail_list"):
            return
        size = self.thumbnail_icon_size()
        size_changed = size != getattr(self, "thumbnail_render_size", size)
        self.thumbnail_render_size = size
        self.config_data.thumbnail_size = size
        self.thumbnail_list.setIconSize(QSize(size, size))
        self.thumbnail_list.setGridSize(QSize(size + 28, size + 34))
        self.thumbnail_list.setFixedHeight(max(THUMBNAIL_MIN_HEIGHT - 8, self.thumbnail_panel_height() - 8))
        self.thumbnail_list.setLayoutDirection(
            Qt.RightToLeft if self.invert_page_position_check.isChecked() else Qt.LeftToRight
        )
        if size_changed and self.thumbnail_items and self.thumbnails_enabled():
            self.thumbnail_resize_refresh_timer.start(120 if self.thumbnail_resizing else 1)

    def refresh_thumbnail_icons_for_size(self) -> None:
        if not self.thumbnails_enabled() or not self.thumbnail_items:
            return
        self.thumbnail_generation += 1
        self.clear_thumbnail_queue()
        self.thumbnail_ready_indexes.clear()
        for item in self.thumbnail_items:
            if item is not None:
                item.setIcon(QIcon())
        self.schedule_thumbnail_prefetch()

    def clear_thumbnail_queue(self) -> None:
        with self.thumbnail_queue.mutex:
            self.thumbnail_queue.queue.clear()
        self.thumbnail_pending.clear()

    # ── rebuild / prefetch ────────────────────────────────────────────────

    def rebuild_thumbnail_items(self) -> None:
        if not hasattr(self, "thumbnail_list"):
            return
        self.thumbnail_generation += 1
        self.thumbnail_rebuild_timer.stop()
        self.clear_thumbnail_queue()
        self.thumbnail_ready_indexes.clear()
        self.thumbnail_list.clear()
        self.thumbnail_items = []
        if not self.thumbnails_enabled() or not self.image_paths:
            self.layout_viewer_host()
            return
        self.update_thumbnail_metrics()
        self.thumbnail_items = [None] * len(self.image_paths)
        self.thumbnail_rebuild_index = 0
        self.continue_thumbnail_rebuild()
        self.schedule_thumbnail_prefetch()
        self.layout_viewer_host()

    def continue_thumbnail_rebuild(self) -> None:
        if not self.thumbnails_enabled() or not self.image_paths:
            return
        started = time.perf_counter()
        batch = 0
        while self.thumbnail_rebuild_index < len(self.image_paths) and batch < 160:
            index = self.thumbnail_rebuild_index
            path = self.image_paths[index]
            item = QListWidgetItem(str(index + 1))
            item.setData(Qt.UserRole, index)
            item.setToolTip(self.display_name(path))
            self.thumbnail_list.addItem(item)
            self.thumbnail_items[index] = item
            self.thumbnail_rebuild_index += 1
            batch += 1
        self.update_thumbnail_selection(scroll=False, schedule=False)
        self.record_profile("サムネイル項目生成(UI)", (time.perf_counter() - started) * 1000)
        if self.thumbnail_rebuild_index < len(self.image_paths):
            self.thumbnail_rebuild_timer.start(1)

    def schedule_thumbnail_prefetch(self) -> None:
        if not self.thumbnails_enabled() or not self.image_paths:
            return
        self.thumbnail_generation += 1
        self.clear_thumbnail_queue()
        current = max(0, self.current_index)
        limit = min(len(self.image_paths), max(80, self.viewer_prefetch_spin.value() * 2 + 20))
        ordered: list[int] = []
        for distance in range(len(self.image_paths)):
            candidates = [current] if distance == 0 else [current + distance, current - distance]
            for index in candidates:
                if 0 <= index < len(self.image_paths):
                    ordered.append(index)
                    if len(ordered) >= limit:
                        break
            if len(ordered) >= limit:
                break
        for index in ordered:
            if index in self.thumbnail_ready_indexes:
                continue
            with self.thumbnail_lock:
                self.thumbnail_sequence += 1
                sequence = self.thumbnail_sequence
            self.thumbnail_pending.add(index)
            self.thumbnail_queue.put((
                abs(index - current), sequence, self.thumbnail_generation,
                index, str(self.image_paths[index]),
            ))

    # ── worker ────────────────────────────────────────────────────────────

    def _thumbnail_worker_loop(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        while True:
            _priority, _seq, generation, index, path_text = self.thumbnail_queue.get()
            if getattr(self, "closing", False):
                return
            if generation != self.thumbnail_generation:
                continue
            import time as _time
            started = _time.perf_counter()
            image = QImage(path_text)
            size = int(self.config_data.thumbnail_size)
            if not image.isNull():
                image = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.signals.profile_event.emit("サムネイル生成", (_time.perf_counter() - started) * 1000)
            self.signals.thumbnail_done.emit(generation, index, image)

    # ── slots ─────────────────────────────────────────────────────────────

    def on_thumbnail_done(self, generation: int, index: int, image) -> None:
        self.thumbnail_pending.discard(index)
        if generation != self.thumbnail_generation or index < 0 or index >= len(self.thumbnail_items):
            return
        item = self.thumbnail_items[index]
        if item is None:
            return
        if not image.isNull():
            started = time.perf_counter()
            item.setIcon(QIcon(QPixmap.fromImage(image)))
            self.record_profile("サムネイル反映(UI)", (time.perf_counter() - started) * 1000)
        self.thumbnail_ready_indexes.add(index)

    def on_thumbnail_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.UserRole)
        if not isinstance(index, int) or index < 0 or index >= len(self.image_paths) or index == self.current_index:
            return
        scroll_bar = self.thumbnail_list.horizontalScrollBar()
        scroll_value = scroll_bar.value()
        self.last_navigation_step = 1 if index > self.current_index else -1
        self.current_index = index
        self.display_current_image(preserve_view=self.preserve_view_check.isChecked(), navigation=True, scroll_thumbnail=False)
        scroll_bar.setValue(scroll_value)

    def update_thumbnail_selection(self, scroll: bool = True, schedule: bool = True) -> None:
        if not hasattr(self, "thumbnail_list") or self.current_index < 0 or self.current_index >= len(self.thumbnail_items):
            return
        item = self.thumbnail_items[self.current_index]
        if item is None:
            return
        scroll_bar = self.thumbnail_list.horizontalScrollBar()
        scroll_value = scroll_bar.value() if not scroll else None
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.setCurrentItem(item)
        self.thumbnail_list.blockSignals(False)
        if scroll:
            self.thumbnail_list.scrollToItem(item, QAbstractItemView.EnsureVisible)
        elif scroll_value is not None:
            scroll_bar.setValue(scroll_value)
            QTimer.singleShot(0, lambda bar=scroll_bar, v=scroll_value: bar.setValue(v))
        if schedule and self.thumbnails_enabled():
            self.schedule_thumbnail_prefetch()

    def on_thumbnail_settings_changed(self) -> None:
        enabled = self.thumbnail_enabled_check.isChecked()
        self.thumbnail_pinned_check.setEnabled(enabled)
        self.config_data.thumbnail_enabled = enabled
        self.config_data.thumbnail_pinned = self.thumbnail_pinned_check.isChecked()
        self.thumbnail_height = self.clamped_thumbnail_height()
        self.config_data.thumbnail_size = self.thumbnail_icon_size()
        self.update_thumbnail_metrics()
        if enabled:
            self.rebuild_thumbnail_items()
        else:
            self.thumbnail_generation += 1
            self.thumbnail_rebuild_timer.stop()
            self.clear_thumbnail_queue()
            self.thumbnail_list.clear()
            self.thumbnail_items.clear()
            self.thumbnail_ready_indexes.clear()
        self.layout_viewer_host()
        self.persist_config()
