from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bindings import (
    key_binding,
    key_binding_text,
    mouse_binding,
    mouse_binding_text,
)
from i18n import UI_TEXT_EN, UI_TEXT_JA


def _dialog_text(text: str, language: str) -> str:
    if language == "en":
        return UI_TEXT_EN.get(text, text)
    return UI_TEXT_JA.get(text, text)


class KeyBindingDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        kind: str,
        binding: dict | None,
        language: str = "ja",
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.binding = dict(binding) if binding else None
        self.capturing = False
        self.language = language
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)

        prompt_key = "ここをクリック後、設定するキーを押下" if kind == "keyboard" else "ここをクリック後、設定するマウスボタンを押下"
        self.capture_button = QPushButton(self._t(prompt_key))
        self.capture_button.clicked.connect(self.start_capture)
        layout.addWidget(self.capture_button)

        mods = QHBoxLayout()
        self.ctrl_check = QCheckBox("Ctrl")
        self.shift_check = QCheckBox("Shift")
        self.alt_check = QCheckBox("Alt")
        for checkbox in (self.ctrl_check, self.shift_check, self.alt_check):
            checkbox.stateChanged.connect(self.on_option_changed)
            mods.addWidget(checkbox)
        mods.addStretch(1)
        layout.addLayout(mods)

        self.double_check = QCheckBox(self._t("ダブルクリック"))
        self.double_check.stateChanged.connect(self.on_option_changed)
        if kind == "mouse":
            layout.addWidget(self.double_check)

        self.preview_label = QLabel()
        layout.addWidget(self.preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("OK")
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("キャンセル"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_binding(binding)

    def _t(self, text: str) -> str:
        return _dialog_text(text, self.language)

    def _load_binding(self, binding: dict | None) -> None:
        modifiers = int(binding.get("modifiers", 0)) if binding else 0
        self.ctrl_check.setChecked(bool(modifiers & Qt.ControlModifier.value))
        self.shift_check.setChecked(bool(modifiers & Qt.ShiftModifier.value))
        self.alt_check.setChecked(bool(modifiers & Qt.AltModifier.value))
        if self.kind == "mouse":
            self.double_check.setChecked(bool(binding.get("double", False)) if binding else False)
        self._update_preview()

    def _selected_modifiers(self) -> int:
        modifiers = 0
        if self.ctrl_check.isChecked():
            modifiers |= Qt.ControlModifier.value
        if self.shift_check.isChecked():
            modifiers |= Qt.ShiftModifier.value
        if self.alt_check.isChecked():
            modifiers |= Qt.AltModifier.value
        return modifiers

    def start_capture(self) -> None:
        self.capturing = True
        self.capture_button.setText(self._t("入力待ち... Escで解除"))
        self.capture_button.setFocus()
        if self.kind == "keyboard":
            self.grabKeyboard()
        else:
            self.grabMouse()

    def on_option_changed(self) -> None:
        if self.binding:
            self.binding["modifiers"] = self._selected_modifiers()
            if self.kind == "mouse":
                self.binding["double"] = self.double_check.isChecked()
        self._update_preview()

    def _stop_capture(self) -> None:
        if self.kind == "keyboard":
            self.releaseKeyboard()
        else:
            self.releaseMouse()
        self.capturing = False
        prompt_key = "ここをクリック後、設定するキーを押下" if self.kind == "keyboard" else "ここをクリック後、設定するマウスボタンを押下"
        self.capture_button.setText(self._t(prompt_key))

    def keyPressEvent(self, event) -> None:
        if not self.capturing:
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Escape:
            self.binding = None
        elif key not in {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta}:
            self.binding = key_binding(key, self._selected_modifiers())
        self._stop_capture()
        self._update_preview()

    def mousePressEvent(self, event) -> None:
        if not self.capturing or self.kind != "mouse":
            super().mousePressEvent(event)
            return
        self.binding = mouse_binding(event.button(), self._selected_modifiers(), self.double_check.isChecked())
        self._stop_capture()
        self._update_preview()

    def _update_preview(self) -> None:
        text = key_binding_text(self.binding) if self.kind == "keyboard" else mouse_binding_text(self.binding)
        if self.language == "en":
            for source, target in UI_TEXT_EN.items():
                text = text.replace(source, target)
        self.preview_label.setText(f"{self._t('現在')}: {text}")


class ColorPickerDialog(QDialog):
    def __init__(self, parent: QWidget, current: str, title: str, language: str = "ja") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._language = language

        color = QColor(current if re.fullmatch(r"#[0-9a-fA-F]{6}", current or "") else "#000000")

        layout = QVBoxLayout(self)
        self._preview = QLabel()
        self._preview.setFixedHeight(40)
        layout.addWidget(self._preview)

        form = QFormLayout()
        self._red = QSpinBox()
        self._green = QSpinBox()
        self._blue = QSpinBox()
        for spin in (self._red, self._green, self._blue):
            spin.setRange(0, 255)
        self._red.setValue(color.red())
        self._green.setValue(color.green())
        self._blue.setValue(color.blue())
        self._hex_edit = QLineEdit(color.name().upper())

        rgb_labels = (("Red", self._red), ("Green", self._green), ("Blue", self._blue)) if language == "en" else (("赤", self._red), ("緑", self._green), ("青", self._blue))
        for label, spin in rgb_labels:
            spin.valueChanged.connect(self._update_from_rgb)
            form.addRow(label, spin)
        self._hex_edit.editingFinished.connect(self._update_from_hex)
        form.addRow("HEX", self._hex_edit)
        layout.addLayout(form)

        cancel_text = "Cancel" if language == "en" else "キャンセル"
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("OK")
        buttons.button(QDialogButtonBox.Cancel).setText(cancel_text)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_from_rgb()

    def _update_from_rgb(self) -> None:
        value = QColor(self._red.value(), self._green.value(), self._blue.value()).name().upper()
        self._hex_edit.blockSignals(True)
        self._hex_edit.setText(value)
        self._hex_edit.blockSignals(False)
        self._preview.setStyleSheet(f"background: {value}; border: 1px solid palette(mid);")

    def _update_from_hex(self) -> None:
        value = self._hex_edit.text().strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            return
        qcolor = QColor(value)
        for spin, component in ((self._red, qcolor.red()), (self._green, qcolor.green()), (self._blue, qcolor.blue())):
            spin.blockSignals(True)
            spin.setValue(component)
            spin.blockSignals(False)
        self._preview.setStyleSheet(f"background: {qcolor.name().upper()}; border: 1px solid palette(mid);")

    def selected_color(self) -> str | None:
        if self.exec() == QDialog.Accepted:
            value = self._hex_edit.text().strip().upper()
            return value if re.fullmatch(r"#[0-9A-F]{6}", value) else None
        return None
