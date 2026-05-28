from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from archive import extract_archive_images
from constants import APP_NAME, TEMP_ARCHIVE_PREFIX, TEMP_LOCK_FILE, TEMP_WORK_PREFIX


class ArchiveMixin:
    def open_archive(self, archive_path: Path) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_ARCHIVE_PREFIX))
        self.write_temp_lock(temp_dir)
        try:
            images, names = extract_archive_images(archive_path, temp_dir)
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            QMessageBox.critical(self, APP_NAME, f"アーカイブを開けませんでした。\n{exc}")
            return
        if not images:
            shutil.rmtree(temp_dir, ignore_errors=True)
            QMessageBox.information(self, APP_NAME, self.tr_ui("このアーカイブには対応画像がありません。"))
            return
        self.leave_archive_mode()
        self.archive_temp_dir = temp_dir
        self.archive_source_path = archive_path
        self.archive_display_names = names
        self.set_archive_options_enabled(False)
        self.set_image_list(images, 0)

    def leave_archive_mode(self) -> None:
        if self.archive_temp_dir:
            self.retired_archive_temp_dirs.append(self.archive_temp_dir)
        self.archive_temp_dir = None
        self.archive_source_path = None
        self.archive_display_names.clear()
        self.set_archive_options_enabled(True)

    def archive_mode_active(self) -> bool:
        return self.archive_temp_dir is not None

    def set_archive_options_enabled(self, enabled: bool) -> None:
        if not enabled and self.archive_disabled_scale_options is None:
            self.archive_disabled_scale_options = (self.save_scale_check.isChecked(), self.use_scale_cache_check.isChecked())
        self.save_scale_check.setEnabled(enabled)
        self.use_scale_cache_check.setEnabled(enabled)
        self.archive_help.setVisible(not enabled)
        if not enabled:
            self.save_scale_check.blockSignals(True)
            self.use_scale_cache_check.blockSignals(True)
            self.save_scale_check.setChecked(False)
            self.use_scale_cache_check.setChecked(False)
            self.save_scale_check.blockSignals(False)
            self.use_scale_cache_check.blockSignals(False)
        elif self.archive_disabled_scale_options is not None:
            save_enabled, cache_enabled = self.archive_disabled_scale_options
            self.archive_disabled_scale_options = None
            self.save_scale_check.blockSignals(True)
            self.use_scale_cache_check.blockSignals(True)
            self.save_scale_check.setChecked(save_enabled)
            self.use_scale_cache_check.setChecked(cache_enabled)
            self.save_scale_check.blockSignals(False)
            self.use_scale_cache_check.blockSignals(False)

    def display_name(self, path: Path) -> str:
        return self.archive_display_names.get(path.resolve(), path.name)

    def write_temp_lock(self, temp_dir: Path) -> None:
        try:
            (temp_dir / TEMP_LOCK_FILE).write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def _cleanup_stale_temp_files(self) -> None:
        temp_root = Path(tempfile.gettempdir())
        for entry in list(temp_root.iterdir()):
            try:
                if entry.is_dir() and entry.name.startswith((TEMP_ARCHIVE_PREFIX, TEMP_WORK_PREFIX)):
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                pass
