from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QProgressBar

from constants import ENGINE_REALCUGAN, ENGINE_REALESRGAN, PREFETCH_DEBOUNCE_MS


class PrefetchMixin:
    # ── progress bars ─────────────────────────────────────────────────────

    def set_progress_bar(self, bar: QProgressBar, value: int, total: int, label: str) -> None:
        if not self.show_log_panel or getattr(self, "closing", False):
            return
        total = max(0, int(total))
        value = max(0, min(int(value), total))
        if total <= 0:
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setFormat("0/0")
        else:
            bar.setRange(0, total)
            bar.setValue(value)
            bar.setFormat(f"{value}/{total}")

    def update_prefetch_progress_bars(self, viewer_plan: list[Path] | None = None, engine_plan: list[Path] | None = None) -> None:
        if not self.show_log_panel:
            return
        engine_plan = engine_plan if engine_plan is not None else self.prefetch_engine_plan

        original_done = len(self.original_cache)
        original_pending = sum(1 for p in self.prefetching_original_paths if p not in self.original_cache)
        self.set_progress_bar(self.original_prefetch_bar, original_done, original_done + original_pending, "拡大前メモリ読込")

        engine_total = len(engine_plan)
        engine_done = sum(1 for p in engine_plan if self.normalized_path(p) in self.prefetch_engine_done_paths)
        self.set_progress_bar(self.upscale_progress_bar, engine_done, engine_total, "拡大画像生成")

        processed_done = len(self.processed_cache)
        processed_pending = sum(1 for key in self.prefetching_processed_keys if key not in self.processed_cache)
        self.set_progress_bar(self.processed_prefetch_bar, processed_done, processed_done + processed_pending, "拡大後メモリ読込")

        pixmap_done = len(self.viewer.pixmap_cache)
        pixmap_total = pixmap_done + len(self.viewer.pixmap_prefetch_keys)
        self.set_progress_bar(self.pixmap_prefetch_bar, pixmap_done, pixmap_total, "表示用QPixmap")

    def pixmap_progress_key(self, kind: str, path: Path) -> tuple:
        return (
            kind,
            self.normalized_path_text(path),
            self.current_engine(),
            self.effective_scale(),
            int(self.denoise_combo.currentText()) if self.current_engine() == ENGINE_REALCUGAN else 0,
            self.tile_spin.value(),
            self.realesrgan_model_combo.currentText() if self.current_engine() == ENGINE_REALESRGAN else "",
            self.viewer.display_rotation % 360,
            self.viewer.display_flip_horizontal,
            self.viewer.display_flip_vertical,
        )

    def on_pixmap_prefetch_progress(self, warmed: int, remaining: int, cache_count: int, elapsed_ms: float) -> None:
        self.record_profile("QPixmap生成(UI)", elapsed_ms)
        if not self.show_log_panel:
            return
        self.pixmap_prefetch_log_accum += warmed
        self.update_prefetch_progress_bars()
        if remaining == 0 or self.pixmap_prefetch_log_accum >= 25:
            self.append_log(f"Pixmap prefetch: warmed +{self.pixmap_prefetch_log_accum}, remaining={remaining}, pixmaps={cache_count}")
            self.pixmap_prefetch_log_accum = 0

    # ── plan helpers ──────────────────────────────────────────────────────

    def make_plan(self, count: int) -> list[Path]:
        plan = [self.image_paths[self.current_index]]
        directions = (1, -1) if self.last_navigation_step >= 0 else (-1, 1)
        for offset in range(1, count + 1):
            for direction in directions:
                index = self.current_index + offset * direction
                if 0 <= index < len(self.image_paths):
                    plan.append(self.image_paths[index])
        return plan

    def make_prefetch_plan(self, count: int) -> list[Path]:
        return self.make_plan(count)[1:]

    def is_current_processing_key(self, key: tuple[str, str, int, int, int, str], current_paths: set[str] | None = None) -> bool:
        if len(key) != 6:
            return False
        current_paths = current_paths or self.image_path_string_set
        return (
            key[0] in current_paths
            and key[1] == self.current_engine()
            and key[2] == self.effective_scale()
            and key[3] == (int(self.denoise_combo.currentText()) if self.current_engine() == ENGINE_REALCUGAN else 0)
            and key[4] == self.tile_spin.value()
            and key[5] == (self.realesrgan_model_combo.currentText() if self.current_engine() == ENGINE_REALESRGAN else "")
        )

    # ── io queue ──────────────────────────────────────────────────────────

    def clear_prefetch_io_queue(self) -> None:
        with self.prefetch_io_queue.mutex:
            self.prefetch_io_queue.queue.clear()

    def queue_prefetch_io_task(self, generation: int, priority: int, kind: str, key: object, source: str, target: str) -> None:
        with self.prefetch_io_lock:
            self.prefetch_io_sequence += 1
            sequence = self.prefetch_io_sequence
        self.prefetch_io_queue.put((int(priority), sequence, generation, kind, key, source, target))

    def _prefetch_io_worker_loop(self) -> None:
        while True:
            priority, sequence, generation, kind, key, source, target = self.prefetch_io_queue.get()
            if generation != self.prefetch_generation:
                continue
            started = time.perf_counter()
            originals: dict[Path, QImage] = {}
            processed: dict[tuple, QImage] = {}
            attempted_originals: list[Path] = []
            attempted_processed: list[tuple] = []
            if kind == "original":
                path = self.normalized_path(Path(source))
                attempted_originals.append(path)
                image = QImage(str(path))
                if not image.isNull():
                    originals[path] = image
                self.signals.profile_event.emit("元画像IO", (time.perf_counter() - started) * 1000)
            elif kind == "processed" and isinstance(key, tuple):
                attempted_processed.append(key)
                target_path = Path(target)
                if target_path.exists():
                    image = QImage(str(target_path))
                    if not image.isNull():
                        processed[key] = image
                self.signals.profile_event.emit("拡大画像IO", (time.perf_counter() - started) * 1000)
            if originals or processed or attempted_originals or attempted_processed:
                self.signals.prefetch_done.emit(generation, originals, processed, attempted_originals, attempted_processed)

    # ── schedule ──────────────────────────────────────────────────────────

    def request_schedule_prefetch(self, delay_ms: int = PREFETCH_DEBOUNCE_MS) -> None:
        if not self.image_paths:
            return
        self.prefetch_timer.start(max(0, delay_ms))

    def schedule_prefetch(self) -> None:
        if not self.image_paths:
            return
        self.prefetch_generation += 1
        self.prefetching_original_paths.clear()
        self.prefetching_processed_keys.clear()
        self.clear_prefetch_io_queue()
        realcugan_plan = self.make_plan(self.realcugan_prefetch_spin.value())
        viewer_plan = self.make_prefetch_plan(self.viewer_prefetch_spin.value())
        self.prefetch_viewer_plan = viewer_plan
        self.prefetch_engine_plan = realcugan_plan[1:]
        self.prefetch_engine_done_paths = {
            self.normalized_path(p)
            for p in self.prefetch_engine_plan
            if self.processing_key(p) in self.processed_cache
        }
        self.start_viewer_prefetch(viewer_plan)
        self.update_prefetch_progress_bars()
        for position, path in enumerate(realcugan_plan):
            self.enqueue_realcugan(path, front=position == 0, check_existing=False, check_skip=False)
        self.reorder_work_queue(realcugan_plan)

    def start_viewer_prefetch(self, viewer_plan: list[Path]) -> None:
        if not viewer_plan:
            self.update_prefetch_progress_bars(viewer_plan)
            return
        generation = self.prefetch_generation
        before_originals = len(self.original_cache)
        before_processed = len(self.processed_cache)
        before_pixmaps = len(self.viewer.pixmap_cache)
        original_paths = [
            self.normalized_path(p)
            for p in viewer_plan
            if self.normalized_path(p) not in self.original_cache
            and self.normalized_path(p) not in self.prefetching_original_paths
        ]
        processed_candidates: list[tuple[tuple, Path]] = []
        for path in viewer_plan:
            key = self.processing_key(path)
            if key in self.processed_cache or key in self.prefetching_processed_keys:
                continue
            if self.archive_mode_active() or not self.use_scale_cache_check.isChecked():
                continue
            processed_candidates.append((key, self.cache_output_path(path, create_dir=False)))
        if not original_paths and not processed_candidates:
            self.update_prefetch_progress_bars(viewer_plan)
            self.append_log_if_visible(f"Viewer prefetch: ready originals={before_originals}, processed={before_processed}, pixmaps={before_pixmaps}")
            return
        self.prefetching_original_paths.update(original_paths)
        self.prefetching_processed_keys.update(key for key, _ in processed_candidates)
        self.update_prefetch_progress_bars(viewer_plan)
        self.append_log_if_visible(
            f"Viewer prefetch start: plan={len(viewer_plan)}, original_read={len(original_paths)}, "
            f"processed_check={len(processed_candidates)}, cache originals={before_originals}, "
            f"processed={before_processed}, pixmaps={before_pixmaps}"
        )
        priority_rank = {self.normalized_path(p): i for i, p in enumerate(viewer_plan)}
        for path in original_paths:
            self.queue_prefetch_io_task(generation, priority_rank.get(self.normalized_path(path), len(priority_rank)), "original", path, str(path), "")
        for key, processed_path in processed_candidates:
            source_path = self.normalized_path(Path(key[0]))
            self.queue_prefetch_io_task(generation, priority_rank.get(source_path, len(priority_rank)) + 1, "processed", key, key[0], str(processed_path))

    def on_prefetch_done(
        self,
        generation: int,
        originals: dict[Path, QImage],
        processed: dict[tuple, QImage],
        attempted_originals: list[Path],
        attempted_processed: list[tuple],
    ) -> None:
        for path in attempted_originals:
            self.prefetching_original_paths.discard(path)
        for key in attempted_processed:
            self.prefetching_processed_keys.discard(key)
        if generation != self.prefetch_generation:
            return
        started = time.perf_counter()
        current_paths = self.image_path_set
        current_path_strings = self.image_path_string_set
        for path, image in originals.items():
            if path in current_paths and path not in self.original_cache:
                self.original_cache[path] = image
        while len(self.original_cache) > max(6, self.config_data.viewer_prefetch_count * 2 + 3):
            self.original_cache.popitem(last=False)
        engine_plan_paths = {self.normalized_path(p) for p in self.prefetch_engine_plan}
        for key, image in processed.items():
            if self.is_current_processing_key(key, current_path_strings) and key not in self.processed_cache:
                self.processed_cache[key] = image
            if self.normalized_path(Path(key[0])) in engine_plan_paths:
                self.prefetch_engine_done_paths.add(self.normalized_path(Path(key[0])))
        warm_items: list[tuple[object, QImage]] = [
            (self.pixmap_progress_key("original", path), image)
            for path, image in originals.items()
            if path in current_paths and not image.isNull()
        ]
        warm_items.extend(
            (self.pixmap_progress_key("processed", Path(key[0])), image)
            for key, image in processed.items()
            if self.is_current_processing_key(key, current_path_strings) and not image.isNull()
        )
        if warm_items:
            self.viewer.queue_pixmap_prefetch(warm_items)
        self.update_prefetch_progress_bars()
        if not self.prefetching_original_paths and not self.prefetching_processed_keys:
            self.append_log_if_visible(
                f"Viewer prefetch done: cache originals={len(self.original_cache)}, "
                f"processed={len(self.processed_cache)}, pixmaps={len(self.viewer.pixmap_cache)}"
            )
        self.record_profile("先読み反映(UI)", (time.perf_counter() - started) * 1000)
