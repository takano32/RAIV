from __future__ import annotations

import re
import time
from pathlib import Path

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from bindings import (
    default_key_bindings,
    duplicate_binding_signatures,
    keyboard_signature,
    mouse_signature,
    normalize_key_bindings,
)
from constants import (
    ACTION_DEFS,
    APP_DIR,
    APP_NAME,
    APP_SHORT_NAME,
    DEFAULT_REALESRGAN_TEMPLATE,
    DEFAULT_REALCUGAN_TEMPLATE,
    ENGINE_LABELS,
    ENGINE_REALESRGAN,
    RESAMPLE_ALGORITHMS,
    SIDE_PANEL_HIDE_GRACE_SEC,
)
from config import save_config


class SettingsMixin:
    # ── geometry ──────────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        if not self._restore_window_rect(self.config_data.window_rect):
            self.resize(1200, 760)
            self._center_on_available_screen()
        if self.config_data.window_maximized:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self._apply_splitter_panel_width()
        if self.config_data.side_panel_pinned:
            self.attach_side_panel_to_splitter(visible=self.config_data.side_panel_visible)
        else:
            self.detach_side_panel_for_overlay(visible=False)

    def _available_virtual_geometry(self) -> QRect:
        available = QRect()
        for screen in QApplication.screens():
            available = screen.availableGeometry() if available.isNull() else available.united(screen.availableGeometry())
        if available.isNull() and QApplication.primaryScreen():
            available = QApplication.primaryScreen().availableGeometry()
        return available

    def _restore_window_rect(self, values: list[int] | None) -> bool:
        if not values or len(values) != 4:
            return False
        available = self._available_virtual_geometry()
        if available.isNull():
            return False
        try:
            x, y, width, height = [int(v) for v in values]
        except (TypeError, ValueError):
            return False
        width = max(640, min(width, max(640, available.width())))
        height = max(480, min(height, max(480, available.height())))
        x = max(available.left(), min(x, available.right() - width + 1))
        y = max(available.top(), min(y, available.bottom() - height + 1))
        self.setGeometry(x, y, width, height)
        return True

    def _center_on_available_screen(self) -> None:
        available = self._available_virtual_geometry()
        if available.isNull():
            return
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    # ── persist ───────────────────────────────────────────────────────────

    def persist_config(self, log: bool = False) -> None:
        if getattr(self, "initializing", False):
            return
        self.save_active_command_template()
        self.config_data.engine = self.current_engine()
        self.config_data.command_template = self.config_data.realcugan_command_template
        self.config_data.scale = int(self.scale_combo.currentText())
        self.config_data.denoise = int(self.denoise_combo.currentText())
        self.config_data.tile = self.tile_spin.value()
        self.config_data.realesrgan_model = self.realesrgan_model_combo.currentText()
        self.config_data.realcugan_prefetch_count = self.realcugan_prefetch_spin.value()
        self.config_data.viewer_prefetch_count = self.viewer_prefetch_spin.value()
        if not self.archive_mode_active():
            self.config_data.save_upscaled_to_scale_folder = self.save_scale_check.isChecked()
            self.config_data.use_scale_folder_cache = self.use_scale_cache_check.isChecked()
        self.config_data.skip_realcugan_for_tall_images = self.skip_tall_check.isChecked()
        self.config_data.skip_realcugan_height_threshold = self.skip_height_spin.value()
        self.config_data.background_color = self.background_edit.text().strip() or "#000000"
        self.config_data.cpu_resample_cache_enabled = self.cpu_resample_check.isChecked()
        self.config_data.cpu_resample_algorithm = self.current_resample_algorithm()
        self.config_data.compare_enabled = self.compare_check.isChecked()
        self.config_data.compare_split = self.compare_slider.value()
        self.config_data.compare_line_color = self.compare_line_edit.text().strip() or "#ffffff"
        self.config_data.compare_line_width = self.compare_line_width_spin.value()
        self.config_data.compare_swap_sides = self.compare_swap_check.isChecked()
        self.config_data.compare_shift_drag_moves_boundary = self.compare_shift_check.isChecked()
        self.config_data.page_scroll_interval_ms = self.page_interval_spin.value()
        self.config_data.wrap_page_navigation = self.wrap_page_check.isChecked()
        self.config_data.preserve_view_on_page_navigation = self.preserve_view_check.isChecked()
        self.config_data.invert_page_position_slider = self.invert_page_position_check.isChecked()
        self.config_data.horizontal_wheel_navigation = self.horizontal_wheel_check.isChecked()
        self.config_data.horizontal_wheel_inverted = self.horizontal_wheel_invert_check.isChecked()
        self.config_data.hide_cursor_in_fullscreen = self.hide_cursor_fullscreen_check.isChecked()
        self.config_data.show_log_panel = self.show_log_check.isChecked()
        self.config_data.show_profile_panel = self.show_profile_check.isChecked()
        if hasattr(self, "language_combo"):
            self.config_data.ui_language = self.language_combo.currentData() or "ja"
        self.config_data.thumbnail_enabled = self.thumbnail_enabled_check.isChecked()
        self.config_data.thumbnail_pinned = self.thumbnail_pinned_check.isChecked()
        self.config_data.thumbnail_height = self.clamped_thumbnail_height()
        self.config_data.thumbnail_size = self.thumbnail_icon_size()
        self.config_data.cleanup_temp_on_start = self.cleanup_check.isChecked()
        self.config_data.settings_tab = ["realcugan", "general", "keyconfig"][max(0, min(2, self.tabs.currentIndex()))]
        if not self.is_app_fullscreen():
            rect = self.normalGeometry() if self.isMaximized() else self.geometry()
            if rect.isValid():
                self.config_data.window_rect = [rect.x(), rect.y(), rect.width(), rect.height()]
                self.config_data.window_maximized = self.isMaximized()
        self.config_data.window_geometry = ""
        side_panel = getattr(self, "side_panel", None)
        pin_button = getattr(self, "pin_button", None)
        self.config_data.side_panel_visible = (
            self.side_panel_visible_before_fullscreen
            if self.is_app_fullscreen()
            else (side_panel.isVisible() if side_panel is not None else self.config_data.side_panel_visible)
        )
        self.config_data.side_panel_pinned = pin_button.isChecked() if pin_button is not None else self.config_data.side_panel_pinned
        splitter = getattr(self, "splitter", None)
        if side_panel is not None:
            self.config_data.side_panel_width = int(self.side_panel_width)
        if splitter is not None and not self.side_panel_overlay:
            sizes = self.splitter.sizes()
            if len(sizes) >= 2 and sizes[1] >= 80:
                self.config_data.splitter_sizes = sizes
        save_config(self.config_data)
        if log:
            self.append_log(f"Saved settings: {self.config_data}")

    def _apply_settings_to_viewer(self) -> None:
        self.viewer.set_background(self.config_data.background_color)
        self.viewer.set_resample_options(self.config_data.cpu_resample_cache_enabled, self.config_data.cpu_resample_algorithm)
        self.viewer.set_key_bindings(self.config_data.key_bindings)
        self.viewer.set_pixmap_cache_limit(self.viewer_prefetch_spin.value() * 2 + 8)
        self.viewer.set_horizontal_wheel_options(
            self.config_data.horizontal_wheel_navigation,
            self.config_data.horizontal_wheel_inverted,
        )
        self.update_thumbnail_metrics()
        self.layout_viewer_host()
        self.on_compare_changed()

    def current_resample_algorithm(self) -> str:
        label = self.cpu_resample_combo.currentText() if hasattr(self, "cpu_resample_combo") else RESAMPLE_ALGORITHMS["lanczos3"]
        for key, value in RESAMPLE_ALGORITHMS.items():
            if label == value:
                return key
        return "lanczos3"

    # ── log / profile visibility ──────────────────────────────────────────

    def apply_log_visibility(self) -> None:
        log_visible = bool(self.show_log_panel)
        profile_visible = bool(self.show_profile_check.isChecked())
        self.log_container.setVisible(log_visible)
        self.log_container.setMaximumHeight(16777215 if log_visible else 0)
        self.log_container.setMinimumHeight(0)
        if hasattr(self, "profile_panel"):
            self.profile_panel.setVisible(profile_visible)
        if hasattr(self, "prefetch_progress_panel"):
            self.prefetch_progress_panel.setVisible(log_visible)
        if hasattr(self, "log_label"):
            self.log_label.setVisible(log_visible)
        if hasattr(self, "log_edit"):
            self.log_edit.setVisible(log_visible)
        if profile_visible:
            self.update_profile_panel()
        if log_visible:
            self.update_prefetch_progress_bars()
            if self.image_paths:
                self.request_schedule_prefetch(0)

    def on_log_visibility_changed(self) -> None:
        self.show_log_panel = self.show_log_check.isChecked()
        self.apply_log_visibility()
        self.persist_config()

    def on_profile_visibility_changed(self) -> None:
        self.update_profile_panel()
        self.apply_log_visibility()
        self.persist_config()

    # ── viewer controls ───────────────────────────────────────────────────

    def update_zoom_label(self, scale: float) -> None:
        percent = max(1, round(scale * 100))
        prefix = "Zoom" if self.ui_language() == "en" else "ズーム"
        self.zoom_label.setText(f"{prefix}: {percent}%")
        if hasattr(self, "zoom_slider") and not self.zoom_slider.isSliderDown():
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(max(self.zoom_slider.minimum(), min(self.zoom_slider.maximum(), percent)))
            self.zoom_slider.blockSignals(False)

    def on_zoom_slider_changed(self, value: int) -> None:
        self.viewer.set_actual_zoom_percent(value)

    def on_viewer_split_changed(self, value: int) -> None:
        self.compare_slider.blockSignals(True)
        self.compare_slider.setValue(value)
        self.compare_slider.blockSignals(False)
        self.config_data.compare_split = value

    def reset_compare_split(self) -> None:
        self.compare_slider.setValue(500)
        self.on_compare_changed()

    def toggle_compare_mode(self) -> None:
        self.compare_check.setChecked(not self.compare_check.isChecked())
        self.on_compare_changed()

    def open_image_dialog(self) -> None:
        start = self.config_data.last_dir or str(Path.home())
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "画像を開く",
            start,
            "Images/Archives (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.zip *.cbz *.rar *.cbr *.7z *.cb7);;All files (*.*)",
        )
        if path:
            self.open_path(Path(path))

    def open_folder_dialog(self) -> None:
        start = self.config_data.last_dir or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "フォルダを開く", start)
        if path:
            self.open_path(Path(path))

    def toggle_thumbnail_panel(self) -> None:
        if not self.thumbnails_enabled():
            self.thumbnail_enabled_check.setChecked(True)
        self.thumbnail_pinned_check.setChecked(not self.thumbnail_pinned_check.isChecked())

    # ── settings change handlers ──────────────────────────────────────────

    def on_compare_changed(self) -> None:
        line_color = self.compare_line_edit.text().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", line_color):
            return
        self.viewer.set_compare(
            self.compare_check.isChecked(),
            self.compare_slider.value(),
            line_color,
            self.compare_line_width_spin.value(),
            self.compare_swap_check.isChecked(),
            self.compare_shift_check.isChecked(),
        )
        self.persist_config()

    def on_background_changed(self) -> None:
        color = self.background_edit.text().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return
        self.viewer.set_background(color)
        self.persist_config()

    def on_resample_settings_changed(self) -> None:
        self.cpu_resample_combo.setEnabled(self.cpu_resample_check.isChecked())
        self.viewer.set_resample_options(self.cpu_resample_check.isChecked(), self.current_resample_algorithm())
        self.persist_config()

    def on_general_settings_changed(self) -> None:
        self.viewer.set_horizontal_wheel_options(
            self.horizontal_wheel_check.isChecked(),
            self.horizontal_wheel_invert_check.isChecked(),
        )
        self.persist_config()
        if self.is_app_fullscreen():
            if self.hide_cursor_fullscreen_check.isChecked():
                self._apply_fullscreen_cursor()
            else:
                self._show_fullscreen_cursor()

    def on_language_changed(self) -> None:
        self.config_data.ui_language = self.language_combo.currentData() or "ja"
        self.apply_language()
        self.persist_config()

    def on_settings_tab_changed(self, index: int) -> None:
        self.config_data.settings_tab = ["realcugan", "general", "keyconfig"][max(0, min(2, index))]
        self.persist_config()

    def on_engine_changed(self, *_args) -> None:
        previous_engine = self.config_data.engine
        previous_text = self.command_edit.text().strip()
        if previous_engine == ENGINE_REALESRGAN:
            self.config_data.realesrgan_command_template = previous_text or DEFAULT_REALESRGAN_TEMPLATE
        else:
            self.config_data.realcugan_command_template = previous_text or DEFAULT_REALCUGAN_TEMPLATE
        self.config_data.engine = self.current_engine()
        self.apply_engine_ui()
        self.on_processing_settings_changed()

    def on_cleanup_changed(self) -> None:
        self.persist_config()
        if self.cleanup_check.isChecked():
            QMessageBox.information(
                self,
                APP_NAME,
                f"次回起動時に、{APP_SHORT_NAME} が作成した古い一時フォルダと一時PNGを削除します。\n\n"
                "このチェックをオンのまま終了した場合に実行されます。",
            )

    def on_processing_settings_changed(self) -> None:
        self.persist_config()
        self.processed_cache.clear()
        self.prefetching_processed_keys.clear()
        self.prefetch_engine_done_paths.clear()
        self.prefetch_generation += 1
        if self.image_paths:
            self.display_current_image()

    def on_viewer_prefetch_changed(self) -> None:
        self.persist_config()
        self.viewer.set_pixmap_cache_limit(self.viewer_prefetch_spin.value() * 2 + 8)
        if self.image_paths:
            self.request_schedule_prefetch(0)

    def choose_engine_exe(self) -> None:
        engine = self.current_engine()
        title = f"{ENGINE_LABELS[engine]} exeを選択"
        path, _filter = QFileDialog.getOpenFileName(
            self, title, self.config_data.last_dir or str(APP_DIR), "Executable (*.exe);;All files (*.*)"
        )
        if path:
            if engine == ENGINE_REALESRGAN:
                self.command_edit.setText(f'"{path}" -i "{{input}}" -o "{{output}}" -s {{scale}} -t {{tile}} -n {{model}}')
            else:
                self.command_edit.setText(f'"{path}" -i "{{input}}" -o "{{output}}" -s {{scale}} -n {{denoise}} -t {{tile}}')
            self.persist_config()

    # ── color pickers ─────────────────────────────────────────────────────

    def choose_background_color(self) -> None:
        title = "Select background color" if self.ui_language() == "en" else "背景色を選択"
        color = self.choose_simple_color(self.background_edit.text(), title)
        if color:
            self.background_edit.setText(color)
            self.on_background_changed()

    def choose_compare_line_color(self) -> None:
        title = "Select compare divider color" if self.ui_language() == "en" else "比較境界線の色を選択"
        color = self.choose_simple_color(self.compare_line_edit.text(), title)
        if color:
            self.compare_line_edit.setText(color)
            self.on_compare_changed()

    def choose_simple_color(self, current: str, title: str) -> str | None:
        self.overlay_modal_guard = True
        self.overlay_hide_suppressed_until = time.monotonic() + 3600
        if self.side_panel_overlay and not self.pin_button.isChecked() and not self.side_panel.isVisible():
            self.show_side_panel()
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        red = QSpinBox()
        green = QSpinBox()
        blue = QSpinBox()
        for spin in (red, green, blue):
            spin.setRange(0, 255)
        qcolor = QColor(current if re.fullmatch(r"#[0-9a-fA-F]{6}", current or "") else "#000000")
        red.setValue(qcolor.red())
        green.setValue(qcolor.green())
        blue.setValue(qcolor.blue())
        preview = QLabel()
        preview.setFixedHeight(40)
        hex_edit = QLineEdit(qcolor.name().upper())

        def update_from_rgb() -> None:
            value = QColor(red.value(), green.value(), blue.value()).name().upper()
            hex_edit.blockSignals(True)
            hex_edit.setText(value)
            hex_edit.blockSignals(False)
            preview.setStyleSheet(f"background: {value}; border: 1px solid palette(mid);")

        def update_from_hex() -> None:
            value = hex_edit.text().strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return
            c = QColor(value)
            for spin, component in ((red, c.red()), (green, c.green()), (blue, c.blue())):
                spin.blockSignals(True)
                spin.setValue(component)
                spin.blockSignals(False)
            preview.setStyleSheet(f"background: {c.name().upper()}; border: 1px solid palette(mid);")

        rgb_labels = (
            (("Red", red), ("Green", green), ("Blue", blue))
            if self.ui_language() == "en"
            else (("赤", red), ("緑", green), ("青", blue))
        )
        for label, spin in rgb_labels:
            spin.valueChanged.connect(update_from_rgb)
            form.addRow(label, spin)
        hex_edit.editingFinished.connect(update_from_hex)
        form.addRow("HEX", hex_edit)
        layout.addWidget(preview)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("OK")
        buttons.button(QDialogButtonBox.Cancel).setText(self.tr_ui("キャンセル"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        update_from_rgb()
        try:
            if dialog.exec() == QDialog.Accepted:
                value = hex_edit.text().strip().upper()
                return value if re.fullmatch(r"#[0-9A-F]{6}", value) else None
            return None
        finally:
            self.overlay_modal_guard = False
            self.overlay_hide_suppressed_until = time.monotonic() + SIDE_PANEL_HIDE_GRACE_SEC

    # ── key binding ───────────────────────────────────────────────────────

    def refresh_keyconfig_buttons(self) -> None:
        buttons = getattr(self, "key_binding_buttons", {})
        self.duplicate_keyboard_bindings = duplicate_binding_signatures(self.config_data.key_bindings, "keyboard")
        keyboard_duplicates = self.duplicate_keyboard_bindings
        mouse_duplicates = duplicate_binding_signatures(self.config_data.key_bindings, "mouse")
        for action_id, _label in ACTION_DEFS:
            bindings = self.config_data.key_bindings.get(action_id, {"keyboard": None, "mouse": None})
            keyboard_button = buttons.get((action_id, "keyboard"))
            mouse_button = buttons.get((action_id, "mouse"))
            if keyboard_button is not None:
                binding = bindings.get("keyboard")
                duplicate = keyboard_signature(binding) in keyboard_duplicates
                prefix = ("Duplicate: " if self.ui_language() == "en" else "重複: ") if duplicate else ""
                keyboard_button.setText(prefix + self.binding_text("keyboard", binding))
                keyboard_button.setStyleSheet("background-color: #7a2020; color: white;" if duplicate else "")
                keyboard_button.setToolTip(self.tr_ui("重複しているため、この割当は無効です。") if duplicate else "")
            if mouse_button is not None:
                binding = bindings.get("mouse")
                duplicate = mouse_signature(binding) in mouse_duplicates
                prefix = ("Duplicate: " if self.ui_language() == "en" else "重複: ") if duplicate else ""
                mouse_button.setText(prefix + self.binding_text("mouse", binding))
                mouse_button.setStyleSheet("background-color: #7a2020; color: white;" if duplicate else "")
                mouse_button.setToolTip(self.tr_ui("重複しているため、この割当は無効です。") if duplicate else "")

    def edit_key_binding(self, action_id: str, kind: str) -> None:
        from dialogs import KeyBindingDialog
        bindings = self.config_data.key_bindings.setdefault(action_id, {"keyboard": None, "mouse": None})
        action_label = self.tr_ui(dict(ACTION_DEFS).get(action_id, action_id))
        title = f"{action_label} - {self.tr_ui('キーボード' if kind == 'keyboard' else 'マウス')}"
        dialog = KeyBindingDialog(self, title, kind, bindings.get(kind), language=self.ui_language())
        if dialog.exec() == QDialog.Accepted:
            bindings[kind] = dialog.binding
            self.config_data.key_bindings = normalize_key_bindings(self.config_data.key_bindings)
            self.viewer.set_key_bindings(self.config_data.key_bindings)
            self.refresh_keyconfig_buttons()
            self.persist_config()

    def reset_key_bindings(self) -> None:
        self.config_data.key_bindings = default_key_bindings()
        self.viewer.set_key_bindings(self.config_data.key_bindings)
        self.refresh_keyconfig_buttons()
        self.persist_config()
