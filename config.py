from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bindings import default_key_bindings, normalize_key_bindings
from constants import (
    APP_DIR,
    BUNDLED_REALCUGAN_EXE,
    BUNDLED_REALESRGAN_EXE,
    CONFIG_PATH,
    DEFAULT_REALCUGAN_TEMPLATE,
    DEFAULT_REALESRGAN_TEMPLATE,
    ENGINE_REALCUGAN,
    ENGINE_LABELS,
    LEGACY_REALCUGAN_TEMPLATE,
    LEGACY_REALESRGAN_TEMPLATE,
    REALESRGAN_MODELS,
    RESAMPLE_ALGORITHMS,
)


def command_executable_exists(command: str) -> bool:
    stripped = command.strip()
    if not stripped:
        return False
    if stripped.startswith('"'):
        end = stripped.find('"', 1)
        token = stripped[1:end] if end > 1 else ""
    else:
        token = stripped.split(maxsplit=1)[0]
    if not token:
        return False
    exe_path = Path(os.path.expandvars(token))
    if exe_path.is_absolute():
        return exe_path.is_file()
    return (APP_DIR / exe_path).is_file() or shutil.which(token) is not None


@dataclass
class AppConfig:
    engine: str = ENGINE_REALCUGAN
    command_template: str = DEFAULT_REALCUGAN_TEMPLATE
    realcugan_command_template: str = DEFAULT_REALCUGAN_TEMPLATE
    realesrgan_command_template: str = DEFAULT_REALESRGAN_TEMPLATE
    scale: int = 2
    denoise: int = 0
    tile: int = 0
    realesrgan_model: str = "realesr-animevideov3"
    realcugan_prefetch_count: int = 10
    viewer_prefetch_count: int = 20
    save_upscaled_to_scale_folder: bool = False
    use_scale_folder_cache: bool = True
    skip_realcugan_for_tall_images: bool = True
    skip_realcugan_height_threshold: int = 2160
    background_color: str = "#000000"
    cpu_resample_cache_enabled: bool = True
    cpu_resample_algorithm: str = "lanczos3"
    compare_enabled: bool = False
    compare_split: int = 500
    compare_line_color: str = "#ffffff"
    compare_line_width: int = 2
    compare_swap_sides: bool = False
    compare_shift_drag_moves_boundary: bool = False
    hide_cursor_in_fullscreen: bool = False
    show_log_panel: bool = False
    show_profile_panel: bool = False
    ui_language: str = "ja"
    thumbnail_enabled: bool = True
    thumbnail_pinned: bool = False
    thumbnail_size: int = 96
    thumbnail_height: int = 142
    horizontal_wheel_navigation: bool = False
    horizontal_wheel_inverted: bool = False
    wrap_page_navigation: bool = False
    preserve_view_on_page_navigation: bool = False
    invert_page_position_slider: bool = True
    page_scroll_interval_ms: int = 1
    arrow_right_next: bool = True
    key_bindings: dict[str, dict[str, dict | None]] = field(default_factory=default_key_bindings)
    cleanup_temp_on_start: bool = False
    settings_tab: str = "realcugan"
    window_rect: list[int] | None = None
    window_maximized: bool = False
    window_geometry: str = ""
    side_panel_visible: bool = True
    side_panel_pinned: bool = True
    side_panel_width: int = 460
    splitter_sizes: list[int] | None = None
    last_dir: str = ""


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        config = AppConfig(**{**asdict(AppConfig()), **data})
        if config.command_template == LEGACY_REALCUGAN_TEMPLATE and BUNDLED_REALCUGAN_EXE.exists():
            config.command_template = DEFAULT_REALCUGAN_TEMPLATE
        if config.realcugan_command_template in {LEGACY_REALCUGAN_TEMPLATE, ""} and BUNDLED_REALCUGAN_EXE.exists():
            config.realcugan_command_template = DEFAULT_REALCUGAN_TEMPLATE
        if config.realesrgan_command_template in {LEGACY_REALESRGAN_TEMPLATE, ""} and BUNDLED_REALESRGAN_EXE.exists():
            config.realesrgan_command_template = DEFAULT_REALESRGAN_TEMPLATE
        if "realcugan_command_template" not in data:
            config.realcugan_command_template = config.command_template or DEFAULT_REALCUGAN_TEMPLATE
        if config.engine not in ENGINE_LABELS:
            config.engine = ENGINE_REALCUGAN
        if config.realesrgan_model not in REALESRGAN_MODELS:
            config.realesrgan_model = REALESRGAN_MODELS[0]
        if config.cpu_resample_algorithm not in RESAMPLE_ALGORITHMS:
            config.cpu_resample_algorithm = "lanczos3"
        if config.ui_language not in {"ja", "en"}:
            config.ui_language = "ja"
        config.key_bindings = normalize_key_bindings(getattr(config, "key_bindings", None))
        if BUNDLED_REALCUGAN_EXE.exists() and not command_executable_exists(config.realcugan_command_template):
            config.realcugan_command_template = DEFAULT_REALCUGAN_TEMPLATE
        if BUNDLED_REALESRGAN_EXE.exists() and not command_executable_exists(config.realesrgan_command_template):
            config.realesrgan_command_template = DEFAULT_REALESRGAN_TEMPLATE
        if "compare_split" in data and 0 <= int(data.get("compare_split", 500)) <= 100:
            config.compare_split = int(data["compare_split"]) * 10
        return config
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
