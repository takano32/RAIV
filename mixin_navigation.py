from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from archive import collect_images, is_image
from constants import APP_NAME, ARCHIVE_EXTENSIONS, PREFETCH_DEBOUNCE_MS


class NavigationMixin:
    # ── path helpers ──────────────────────────────────────────────────────

    def normalized_path(self, path: Path) -> Path:
        return path if path.is_absolute() else path.resolve()

    def normalized_path_text(self, path: Path) -> str:
        return str(self.normalized_path(path))

    def refresh_image_path_sets(self) -> None:
        self.image_path_set = {self.normalized_path(p) for p in self.image_paths}
        self.image_path_string_set = {str(p) for p in self.image_path_set}

    # ── open ──────────────────────────────────────────────────────────────

    def open_path(self, path: Path) -> None:
        path = path.resolve()
        if path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS:
            self.open_archive(path)
            return
        self.leave_archive_mode()
        if path.is_dir():
            images = collect_images(path)
            index = 0
        elif path.is_file() and is_image(path):
            images = [path]
            index = 0
        else:
            QMessageBox.information(self, APP_NAME, self.tr_ui("画像ファイル、画像フォルダ、またはアーカイブを指定してください。"))
            return
        if not images:
            QMessageBox.information(self, APP_NAME, self.tr_ui("対応画像がありません。"))
            return
        self.set_image_list(images, index)
        self.config_data.last_dir = str(images[index].parent)
        self.persist_config()
        if path.is_file() and is_image(path):
            self.folder_list_loading = True
            self.deferred_page_steps = 0
            self.collect_folder_images_async(path.parent, path)

    def open_path_deferred(self, path: Path) -> None:
        path = path.resolve()
        if path.is_file() and is_image(path):
            self.leave_archive_mode()
            self.set_image_list([path], 0, defer_work=True)
            self.folder_list_loading = True
            self.deferred_page_steps = 0
            self.config_data.last_dir = str(path.parent)
            QTimer.singleShot(0, lambda p=path: self.collect_folder_images_async(p.parent, p))
            QTimer.singleShot(0, self.persist_config)
            return
        QTimer.singleShot(0, lambda p=path: self.open_path(p))

    def set_image_list(self, images: list[Path], index: int, defer_work: bool = False) -> None:
        self.image_paths = images
        self.refresh_image_path_sets()
        self.current_index = index
        self.pending_page_steps = 0
        self.folder_list_loading = False
        self.deferred_page_steps = 0
        self.original_cache.clear()
        self.processed_cache.clear()
        self.viewer.pixmap_cache.clear()
        self.viewer.clear_pixmap_prefetch_state()
        self.prefetching_original_paths.clear()
        self.prefetching_processed_keys.clear()
        self.prefetch_viewer_plan = []
        self.prefetch_engine_plan = []
        self.prefetch_engine_done_paths.clear()
        self.prefetch_generation += 1
        self.update_prefetch_progress_bars()
        self.rebuild_thumbnail_items()
        if defer_work:
            self.display_current_image(defer_work=True)
        else:
            self.display_current_image()

    def collect_folder_images_async(self, folder: Path, selected_path: Path) -> None:
        def worker() -> None:
            started = time.perf_counter()
            images = collect_images(folder)
            self.signals.profile_event.emit("フォルダ画像列挙", (time.perf_counter() - started) * 1000)
            self.signals.folder_images_ready.emit(images, selected_path.resolve())

        threading.Thread(target=worker, daemon=True).start()

    def on_folder_images_ready(self, images: list[Path], selected_path: Path) -> None:
        if not images:
            self.folder_list_loading = False
            return
        try:
            selected_index = images.index(selected_path)
        except ValueError:
            self.folder_list_loading = False
            return
        if not self.image_paths or self.normalized_path(self.image_paths[self.current_index]) != selected_path:
            self.folder_list_loading = False
            return
        self.image_paths = images
        self.refresh_image_path_sets()
        self.current_index = selected_index
        self.folder_list_loading = False
        state = "Displaying" if self.ui_language() == "en" else "表示中"
        self.status_label.setText(f"{self.current_index + 1}/{len(self.image_paths)} {state}: {self.display_name(selected_path)}")
        self.update_page_position_slider()
        self.update_window_title()
        self.rebuild_thumbnail_items()
        self.schedule_prefetch()
        if self.deferred_page_steps:
            steps = self.deferred_page_steps
            self.deferred_page_steps = 0
            QTimer.singleShot(0, lambda s=steps: self.queue_page_steps(s))

    # ── display ───────────────────────────────────────────────────────────

    def display_current_image(
        self,
        defer_work: bool = False,
        preserve_view: bool = False,
        navigation: bool = False,
        scroll_thumbnail: bool = True,
    ) -> None:
        if not self.image_paths or self.current_index < 0:
            return
        profile_start = time.perf_counter()
        path = self.image_paths[self.current_index]
        source = self.load_original(path)
        cache_key = self.processing_key(path)
        processed = self.processed_cache.get(cache_key)
        skipped = False
        if processed is None:
            existing = self.existing_processed_path(path)
            if existing is not None:
                processed = QImage(str(existing))
                if not processed.isNull():
                    self.processed_cache[cache_key] = processed
        if processed is None or processed.isNull():
            if self.should_skip_realcugan(path):
                skipped = True
                state = "対象外"
            else:
                self.enqueue_realcugan(path, front=True)
                state = f"{self.engine_label()}待ち"
            processed = None
        else:
            state = "処理済み"
        if navigation:
            self.viewer.begin_interactive_resample_delay()
        self.viewer.set_images(source, processed, preserve_view=preserve_view)
        self.viewer.pixmap_prefetch_done_keys.add(self.pixmap_progress_key("original", path))
        if processed is not None and not processed.isNull():
            self.viewer.pixmap_prefetch_done_keys.add(self.pixmap_progress_key("processed", path))
        self.status_label.setText(f"{self.current_index + 1}/{len(self.image_paths)} {self.state_text(state)}: {self.display_name(path)}")
        self.update_page_position_slider()
        self.update_window_title(source=source, processed=processed, skipped=skipped)
        self.update_thumbnail_selection(scroll=scroll_thumbnail)
        self.request_borderless_fullscreen_enforce()
        self.request_schedule_prefetch(0 if defer_work else PREFETCH_DEBOUNCE_MS)
        self.record_profile("表示切替", (time.perf_counter() - profile_start) * 1000)

    def load_original(self, path: Path) -> QImage:
        path = self.normalized_path(path)
        cached = self.original_cache.get(path)
        if cached is not None:
            self.original_cache.move_to_end(path)
            return cached
        started = time.perf_counter()
        image = QImage(str(path))
        self.record_profile("元画像読込(UI)", (time.perf_counter() - started) * 1000)
        self.original_cache[path] = image
        while len(self.original_cache) > max(6, self.config_data.viewer_prefetch_count * 2 + 3):
            self.original_cache.popitem(last=False)
        return image

    def update_window_title(self, source: QImage | None = None, processed: QImage | None = None, skipped: bool | None = None) -> None:
        if not self.image_paths:
            self.setWindowTitle(APP_NAME)
            return
        path = self.image_paths[self.current_index]
        if source is None:
            source = self.load_original(path)
        if processed is None:
            processed = self.processed_cache.get(self.processing_key(path))
        is_skipped = skipped if skipped is not None else self.should_skip_realcugan(path)
        if processed and not processed.isNull():
            after = f"{processed.width()}x{processed.height()}"
        elif is_skipped:
            after = "Skipped" if self.ui_language() == "en" else "拡大処理対象外"
        else:
            after = "Processing" if self.ui_language() == "en" else "処理中"
        self.setWindowTitle(
            f"{self.display_name(path)} ({self.current_index + 1} / {len(self.image_paths)}) "
            f"[{source.width()}x{source.height()}] -> [{after}] - {APP_NAME}"
        )

    # ── page navigation ───────────────────────────────────────────────────

    def queue_page_steps(self, steps: int) -> None:
        if not self.image_paths or steps == 0:
            return
        if self.folder_list_loading and len(self.image_paths) <= 1:
            self.deferred_page_steps = max(-999, min(999, self.deferred_page_steps + steps))
            return
        self.pending_page_steps = steps
        if not self.page_scroll_timer.isActive():
            self._drain_page_steps()

    def _drain_page_steps(self) -> None:
        if self.pending_page_steps == 0:
            self.page_scroll_timer.stop()
            return
        step = 1 if self.pending_page_steps > 0 else -1
        if self.show_relative_image(step):
            self.pending_page_steps -= step
            if self.pending_page_steps:
                self.page_scroll_timer.start(max(0, self.page_interval_spin.value()))
        else:
            self.pending_page_steps = 0

    def show_relative_image(self, step: int) -> bool:
        next_index = self.current_index + step
        if next_index < 0 or next_index >= len(self.image_paths):
            if not self.wrap_page_check.isChecked():
                return False
            next_index %= len(self.image_paths)
        self.last_navigation_step = 1 if step > 0 else -1
        self.current_index = next_index
        self.display_current_image(preserve_view=self.preserve_view_check.isChecked(), navigation=True)
        return True

    def show_first_image(self) -> None:
        if self.image_paths:
            self.current_index = 0
            self.last_navigation_step = -1
            self.display_current_image(preserve_view=self.preserve_view_check.isChecked(), navigation=True)

    def show_last_image(self) -> None:
        if self.image_paths:
            self.current_index = len(self.image_paths) - 1
            self.last_navigation_step = 1
            self.display_current_image(preserve_view=self.preserve_view_check.isChecked(), navigation=True)

    # ── page position slider ──────────────────────────────────────────────

    def update_page_position_slider(self) -> None:
        slider = getattr(self, "page_position_slider", None)
        if slider is None:
            return
        label = getattr(self, "page_position_count_label", None)
        slider.blockSignals(True)
        if self.image_paths and self.current_index >= 0:
            slider.setEnabled(True)
            total = len(self.image_paths)
            if slider.minimum() != 1 or slider.maximum() != total:
                slider.setRange(1, total)
            value = self.current_index + 1
            if slider.value() != value:
                slider.setValue(value)
            if label is not None:
                label.setText(f"{value}/{total}")
        else:
            if slider.value() != 0:
                slider.setValue(0)
            if slider.minimum() != 0 or slider.maximum() != 0:
                slider.setRange(0, 0)
            slider.setEnabled(False)
            if label is not None:
                label.setText("0/0")
        slider.blockSignals(False)

    def on_page_position_slider_changed(self, value: int) -> None:
        if not self.image_paths or value <= 0:
            return
        index = max(0, min(len(self.image_paths) - 1, value - 1))
        if index == self.current_index:
            return
        self.last_navigation_step = 1 if index > self.current_index else -1
        self.current_index = index
        self.display_current_image(preserve_view=self.preserve_view_check.isChecked(), navigation=True)

    def on_page_position_slider_direction_changed(self) -> None:
        self.page_position_slider.setInvertedAppearance(self.invert_page_position_check.isChecked())
        self.update_thumbnail_metrics()
        self.persist_config()
