from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QWidget

from bindings import key_binding_text, mouse_binding_text
from i18n import UI_TEXT_EN, UI_TEXT_JA


class LanguageMixin:
    def ui_language(self) -> str:
        combo = getattr(self, "language_combo", None)
        if combo is not None:
            return combo.currentData() or "ja"
        return self.config_data.ui_language if self.config_data.ui_language in {"ja", "en"} else "ja"

    def tr_ui(self, text: str) -> str:
        if self.ui_language() == "en":
            return UI_TEXT_EN.get(text, text)
        return UI_TEXT_JA.get(text, text)

    def apply_language(self) -> None:
        if not hasattr(self, "side_panel"):
            return
        self._translate_widget_tree(self.side_panel)
        if hasattr(self, "tabs"):
            for index in range(self.tabs.count()):
                self.tabs.setTabText(index, self.tr_ui(self.tabs.tabText(index)))
        if hasattr(self, "pin_button"):
            self.pin_button.setText(self.tr_ui("固定中" if self.pin_button.isChecked() else "自動表示"))
        if hasattr(self, "language_label"):
            self.language_label.setText("Language")
        self.update_zoom_label(self.viewer.current_scale() if hasattr(self, "viewer") else 1.0)
        self.update_page_position_slider()
        self.refresh_keyconfig_buttons()

    def _translate_widget_tree(self, widget: QWidget) -> None:
        for child in widget.findChildren(QWidget):
            if child.objectName() == "languageLabel":
                continue
            if isinstance(child, QLabel):
                child.setText(self.tr_ui(child.text()))
            elif isinstance(child, QCheckBox):
                child.setText(self.tr_ui(child.text()))
            elif isinstance(child, QPushButton):
                child.setText(self.tr_ui(child.text()))

    def binding_text(self, kind: str, binding: dict | None) -> str:
        text = key_binding_text(binding) if kind == "keyboard" else mouse_binding_text(binding)
        table = UI_TEXT_EN if self.ui_language() == "en" else UI_TEXT_JA
        for source, target in table.items():
            text = text.replace(source, target)
        return text

    def state_text(self, state: str) -> str:
        if self.ui_language() != "en":
            return state
        return {
            "表示中": "Displaying",
            "対象外": "Skipped",
            "処理済み": "Processed",
            "処理中": "Processing",
            "処理対象外": "Skipped",
        }.get(state, state.replace("待ち", " waiting"))
