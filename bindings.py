from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

MODIFIER_MASK = (
    Qt.ControlModifier.value
    | Qt.ShiftModifier.value
    | Qt.AltModifier.value
)

_MOUSE_BUTTON_NAMES: dict[int, str] = {
    Qt.LeftButton.value: "左クリック",
    Qt.RightButton.value: "右クリック",
    Qt.MiddleButton.value: "ホイールクリック",
    Qt.BackButton.value: "戻るボタン",
    Qt.ForwardButton.value: "進むボタン",
}


def key_binding(key: Qt.Key | int, modifiers: int = 0) -> dict[str, int]:
    return {"key": int(key), "modifiers": int(modifiers) & MODIFIER_MASK}


def mouse_binding(button: Qt.MouseButton | int, modifiers: int = 0, double: bool = False) -> dict[str, int | bool]:
    return {
        "button": int(button.value if hasattr(button, "value") else button),
        "modifiers": int(modifiers) & MODIFIER_MASK,
        "double": bool(double),
    }


def default_key_bindings() -> dict[str, dict[str, dict | None]]:
    return {
        "open_image": {"keyboard": key_binding(Qt.Key_O), "mouse": None},
        "open_folder": {"keyboard": key_binding(Qt.Key_F), "mouse": None},
        "next_page": {"keyboard": key_binding(Qt.Key_Left), "mouse": None},
        "previous_page": {"keyboard": key_binding(Qt.Key_Right), "mouse": None},
        "last_page": {"keyboard": None, "mouse": mouse_binding(Qt.ForwardButton)},
        "first_page": {"keyboard": None, "mouse": mouse_binding(Qt.BackButton)},
        "toggle_fullscreen": {"keyboard": None, "mouse": mouse_binding(Qt.MiddleButton)},
        "toggle_thumbnail_panel": {"keyboard": key_binding(Qt.Key_F3), "mouse": None},
        "toggle_side_panel": {"keyboard": key_binding(Qt.Key_F4), "mouse": None},
        "toggle_compare": {"keyboard": None, "mouse": None},
        "actual_size": {"keyboard": None, "mouse": mouse_binding(Qt.RightButton, double=True)},
        "fit_view": {"keyboard": None, "mouse": mouse_binding(Qt.LeftButton, double=True)},
        "rotate_right": {"keyboard": key_binding(Qt.Key_R), "mouse": None},
        "rotate_left": {"keyboard": key_binding(Qt.Key_L), "mouse": None},
        "flip_horizontal": {"keyboard": key_binding(Qt.Key_H), "mouse": None},
        "flip_vertical": {"keyboard": key_binding(Qt.Key_V), "mouse": None},
    }


def normalize_key_bindings(value: object) -> dict[str, dict[str, dict | None]]:
    defaults = default_key_bindings()
    if not isinstance(value, dict):
        return defaults
    normalized = defaults
    for action_id, parts in value.items():
        if action_id not in normalized or not isinstance(parts, dict):
            continue
        for kind in ("keyboard", "mouse"):
            binding = parts.get(kind)
            if binding is None:
                normalized[action_id][kind] = None
                continue
            if not isinstance(binding, dict):
                continue
            if kind == "keyboard":
                key = binding.get("key")
                if isinstance(key, int) and key > 0:
                    normalized[action_id][kind] = {
                        "key": key,
                        "modifiers": int(binding.get("modifiers", 0)) & MODIFIER_MASK,
                    }
            else:
                button = binding.get("button")
                if isinstance(button, int) and button > 0:
                    normalized[action_id][kind] = {
                        "button": button,
                        "modifiers": int(binding.get("modifiers", 0)) & MODIFIER_MASK,
                        "double": bool(binding.get("double", False)),
                    }
    return normalized


def modifier_value(modifiers: object) -> int:
    return int(modifiers.value if hasattr(modifiers, "value") else modifiers) & MODIFIER_MASK


def binding_modifiers_text(modifiers: int) -> list[str]:
    names = []
    if modifiers & Qt.ControlModifier.value:
        names.append("Ctrl")
    if modifiers & Qt.ShiftModifier.value:
        names.append("Shift")
    if modifiers & Qt.AltModifier.value:
        names.append("Alt")
    return names


def key_binding_text(binding: dict | None) -> str:
    if not binding:
        return "未割当"
    parts = binding_modifiers_text(int(binding.get("modifiers", 0)))
    key = int(binding.get("key", 0))
    key_text = QKeySequence(key).toString(QKeySequence.NativeText) if key else ""
    parts.append(key_text or f"Key {key}")
    return "+".join(parts)


def mouse_binding_text(binding: dict | None) -> str:
    if not binding:
        return "未割当"
    parts = binding_modifiers_text(int(binding.get("modifiers", 0)))
    button = int(binding.get("button", 0))
    button_text = _MOUSE_BUTTON_NAMES.get(button, f"ボタン{button}")
    if binding.get("double"):
        button_text = button_text.replace("クリック", "ダブルクリック")
        if "ダブルクリック" not in button_text:
            button_text = f"{button_text}ダブルクリック"
    parts.append(button_text)
    return "+".join(parts)


def keyboard_signature(binding: dict | None) -> tuple[int, int] | None:
    if not binding:
        return None
    key = int(binding.get("key", 0))
    if key <= 0:
        return None
    return key, int(binding.get("modifiers", 0)) & MODIFIER_MASK


def mouse_signature(binding: dict | None) -> tuple[int, int, bool] | None:
    if not binding:
        return None
    button = int(binding.get("button", 0))
    if button <= 0:
        return None
    return button, int(binding.get("modifiers", 0)) & MODIFIER_MASK, bool(binding.get("double", False))


def duplicate_binding_signatures(bindings: dict[str, dict[str, dict | None]], kind: str) -> set[tuple]:
    seen: dict[tuple, str] = {}
    duplicates: set[tuple] = set()
    if kind == "keyboard":
        seen[(int(Qt.Key_Space), 0)] = "__fixed_space__"
        seen[(int(Qt.Key_Backspace), 0)] = "__fixed_backspace__"
        signature_func = keyboard_signature
    else:
        signature_func = mouse_signature
    for action_id, action_bindings in bindings.items():
        if not isinstance(action_bindings, dict):
            continue
        signature = signature_func(action_bindings.get(kind))
        if signature is None:
            continue
        if signature in seen:
            duplicates.add(signature)
        else:
            seen[signature] = action_id
    return duplicates
