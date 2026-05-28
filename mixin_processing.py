from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage

from constants import (
    ENGINE_REALCUGAN,
    ENGINE_REALESRGAN,
    ENGINE_LABELS,
    REALESRGAN_FIXED_SCALE,
    TEMP_OUTPUT_PREFIX,
)
from upscale import run_upscale_engine


class ProcessingMixin:
    # ── engine helpers ────────────────────────────────────────────────────

    def current_engine(self) -> str:
        label = self.engine_combo.currentText() if hasattr(self, "engine_combo") else ENGINE_LABELS[ENGINE_REALCUGAN]
        for engine, engine_label in ENGINE_LABELS.items():
            if label == engine_label:
                return engine
        return ENGINE_REALCUGAN

    def effective_scale(self) -> int:
        return REALESRGAN_FIXED_SCALE if self.current_engine() == ENGINE_REALESRGAN else int(self.scale_combo.currentText())

    def engine_label(self) -> str:
        return ENGINE_LABELS.get(self.current_engine(), ENGINE_LABELS[ENGINE_REALCUGAN])

    def default_template_for_engine(self, engine: str) -> str:
        from constants import DEFAULT_REALESRGAN_TEMPLATE, DEFAULT_REALCUGAN_TEMPLATE
        return DEFAULT_REALESRGAN_TEMPLATE if engine == ENGINE_REALESRGAN else DEFAULT_REALCUGAN_TEMPLATE

    def active_command_template(self) -> str:
        if self.current_engine() == ENGINE_REALESRGAN:
            return self.config_data.realesrgan_command_template
        return self.config_data.realcugan_command_template

    def save_active_command_template(self) -> None:
        if not hasattr(self, "command_edit"):
            return
        text = self.command_edit.text().strip() or self.default_template_for_engine(self.current_engine())
        if self.current_engine() == ENGINE_REALESRGAN:
            self.config_data.realesrgan_command_template = text
        else:
            self.config_data.realcugan_command_template = text

    def apply_engine_ui(self) -> None:
        if not hasattr(self, "engine_combo"):
            return
        engine = self.current_engine()
        self.scale_combo.setEnabled(engine == ENGINE_REALCUGAN)
        self.denoise_combo.setEnabled(engine == ENGINE_REALCUGAN)
        self.denoise_help.setEnabled(engine == ENGINE_REALCUGAN)
        self.realesrgan_model_combo.setEnabled(engine == ENGINE_REALESRGAN)
        self.realesrgan_model_help.setEnabled(engine == ENGINE_REALESRGAN)
        self.realesrgan_model_detail.setEnabled(engine == ENGINE_REALESRGAN)
        self.command_edit.blockSignals(True)
        self.command_edit.setText(self.active_command_template())
        self.command_edit.blockSignals(False)

    # ── cache / path helpers ──────────────────────────────────────────────

    def processing_key(self, source: Path) -> tuple[str, str, int, int, int, str]:
        return (
            self.normalized_path_text(source),
            self.current_engine(),
            self.effective_scale(),
            int(self.denoise_combo.currentText()) if self.current_engine() == ENGINE_REALCUGAN else 0,
            self.tile_spin.value(),
            self.realesrgan_model_combo.currentText() if self.current_engine() == ENGINE_REALESRGAN else "",
        )

    def cache_model_name(self) -> str:
        if self.current_engine() == ENGINE_REALESRGAN:
            raw = f"realesrgan_{self.realesrgan_model_combo.currentText()}"
        else:
            raw = "realcugan"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)

    def cache_output_path(self, source: Path, create_dir: bool) -> Path:
        folder = source.parent / f"{self.cache_model_name()}_x{self.effective_scale()}"
        if create_dir:
            folder.mkdir(parents=True, exist_ok=True)
        return folder / source.name

    def prepare_output_path(self, source: Path) -> tuple[Path, bool]:
        if self.save_scale_check.isChecked() and not self.archive_mode_active():
            return self.cache_output_path(source, create_dir=True), False
        fd, text_path = tempfile.mkstemp(prefix=TEMP_OUTPUT_PREFIX, suffix=".png", dir=self.process_temp_dir)
        os.close(fd)
        Path(text_path).unlink(missing_ok=True)
        return Path(text_path), True

    def has_processed_result(self, source: Path) -> bool:
        return self.processing_key(source) in self.processed_cache or self.existing_processed_path(source) is not None

    def existing_processed_path(self, source: Path) -> Path | None:
        if self.archive_mode_active() or not self.use_scale_cache_check.isChecked():
            return None
        path = self.cache_output_path(source, create_dir=False)
        return path if path.exists() else None

    def should_skip_realcugan(self, path: Path) -> bool:
        return self.skip_tall_check.isChecked() and self.load_original(path).height() >= self.skip_height_spin.value()

    # ── queue management ──────────────────────────────────────────────────

    def enqueue_realcugan(
        self,
        path: Path,
        front: bool = False,
        force: bool = False,
        check_existing: bool = True,
        check_skip: bool = True,
    ) -> None:
        path = self.normalized_path(path)
        if check_existing and not force and self.has_processed_result(path):
            return
        if check_skip and self.should_skip_realcugan(path):
            return
        if path in self.processing_paths:
            return
        if path in self.queued_paths:
            if front:
                self.promote_work_item(path)
            return
        self.queued_paths.add(path)
        if front:
            with self.work_queue.mutex:
                self.work_queue.queue.appendleft(path)
                self.work_queue.unfinished_tasks += 1
                self.work_queue.not_empty.notify()
        else:
            self.work_queue.put(path)

    def promote_work_item(self, path: Path) -> None:
        with self.work_queue.mutex:
            items = [item for item in self.work_queue.queue if item != path]
            self.work_queue.queue.clear()
            self.work_queue.queue.extend(items)
            self.work_queue.queue.appendleft(path)
            self.work_queue.not_empty.notify()

    def reorder_work_queue(self, priority_paths: list[Path]) -> None:
        priority = [self.normalized_path(p) for p in priority_paths]
        priority_rank = {p: i for i, p in enumerate(priority)}
        with self.work_queue.mutex:
            items = [item for item in self.work_queue.queue if item is not None]
            if not items:
                return
            items.sort(key=lambda item: priority_rank.get(self.normalized_path(item), len(priority_rank) + 1))
            self.work_queue.queue.clear()
            self.work_queue.queue.extend(items)
            self.work_queue.not_empty.notify()

    # ── worker loop ───────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while True:
            path = self.work_queue.get()
            if path is None or getattr(self, "closing", False):
                return
            self.queued_paths.discard(path)
            if self.has_processed_result(path):
                continue
            if self._should_skip_upscale_in_worker(path):
                continue
            self.processing_paths.add(path)
            self.signals.process_started.emit(str(path))
            output_path, is_temporary = self.prepare_output_path(path)
            result = run_upscale_engine(
                source=path,
                output_path=output_path,
                command_template=self.active_command_template(),
                scale=self.effective_scale(),
                denoise=self.denoise_combo.currentText(),
                tile=self.tile_spin.value(),
                model=self.realesrgan_model_combo.currentText(),
                temporary_output=is_temporary,
            )
            self.processing_paths.discard(path)
            self.signals.process_done.emit(result)

    def _should_skip_upscale_in_worker(self, path: Path) -> bool:
        if not self.config_data.skip_realcugan_for_tall_images:
            return False
        image = QImage(str(path))
        return not image.isNull() and image.height() >= self.config_data.skip_realcugan_height_threshold

    # ── process signals ───────────────────────────────────────────────────

    def on_process_started(self, path_text: str) -> None:
        self.append_log(f"{self.engine_label()} started: {self.display_name(Path(path_text))}")
        self.update_window_title()

    def on_process_done(self, result: dict) -> None:
        path: Path = result["path"]
        output = result.get("output") or ""
        if output:
            self.append_log(output)
        if result["code"] == 0 and not result["image"].isNull():
            self.record_profile(f"{self.engine_label()}処理", float(result.get("elapsed_ms", 0.0)))
            self.append_log(f"Done: {self.display_name(path)}")
            key = self.processing_key(path)
            self.processed_cache[key] = result["image"]
            self.prefetch_engine_done_paths.add(self.normalized_path(path))
            self.update_prefetch_progress_bars()
            if self.current_index >= 0 and self.normalized_path(path) == self.normalized_path(self.image_paths[self.current_index]):
                self.viewer.set_processed(result["image"])
                self.viewer.pixmap_prefetch_done_keys.add(self.pixmap_progress_key("processed", path))
                self.status_label.setText(f"{self.current_index + 1}/{len(self.image_paths)} 処理済み: {self.display_name(path)}")
                self.update_window_title()
        else:
            self.append_log(f"Process exited with code {result['code']}: {self.display_name(path)}")
            self.update_prefetch_progress_bars()

    def force_reprocess(self) -> None:
        if not self.image_paths:
            return
        path = self.image_paths[self.current_index]
        self.processed_cache.pop(self.processing_key(path), None)
        self.viewer.set_processed(None)
        self.enqueue_realcugan(path, front=True, force=True)
