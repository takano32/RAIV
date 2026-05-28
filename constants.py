from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Realtime AI Image Viewer"
APP_SHORT_NAME = "RAIV"
APP_ID = "RealtimeAIImageViewer.RAIV"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "setting.json"
APP_ICON_ICO = APP_DIR / "assets" / "app_icon.ico"
APP_ICON_PNG = APP_DIR / "assets" / "app_icon.png"

REALESRGAN_FIXED_SCALE = 4

BUNDLED_REALCUGAN_EXE = APP_DIR / "tools" / "realcugan-ncnn-vulkan" / "realcugan-ncnn-vulkan.exe"
BUNDLED_REALESRGAN_EXE = APP_DIR / "tools" / "realesrgan-ncnn-vulkan" / "realesrgan-ncnn-vulkan.exe"

LEGACY_REALCUGAN_TEMPLATE = 'realcugan-ncnn-vulkan.exe -i "{input}" -o "{output}" -s {scale} -n {denoise} -t {tile}'
DEFAULT_REALCUGAN_TEMPLATE = (
    f'"{BUNDLED_REALCUGAN_EXE}" -i "{{input}}" -o "{{output}}" -s {{scale}} -n {{denoise}} -t {{tile}}'
    if BUNDLED_REALCUGAN_EXE.exists()
    else LEGACY_REALCUGAN_TEMPLATE
)
LEGACY_REALESRGAN_TEMPLATE = 'realesrgan-ncnn-vulkan.exe -i "{input}" -o "{output}" -s {scale} -t {tile} -n {model}'
DEFAULT_REALESRGAN_TEMPLATE = (
    f'"{BUNDLED_REALESRGAN_EXE}" -i "{{input}}" -o "{{output}}" -s {{scale}} -t {{tile}} -n {{model}}'
    if BUNDLED_REALESRGAN_EXE.exists()
    else LEGACY_REALESRGAN_TEMPLATE
)

ENGINE_REALCUGAN = "realcugan"
ENGINE_REALESRGAN = "realesrgan"
ENGINE_LABELS: dict[str, str] = {
    ENGINE_REALCUGAN: "Real-CUGAN",
    ENGINE_REALESRGAN: "Real-ESRGAN",
}
REALESRGAN_MODELS = ["realesr-animevideov3", "realesrgan-x4plus", "realesrgan-x4plus-anime"]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
ARCHIVE_EXTENSIONS = {".zip", ".cbz", ".rar", ".cbr", ".7z", ".cb7"}

TEMP_ARCHIVE_PREFIX = "realcugan_qt_archive_"
TEMP_WORK_PREFIX = "realcugan_qt_work_"
TEMP_OUTPUT_PREFIX = "realcugan_"
TEMP_LOCK_FILE = "viewer.lock"

BORDERLESS_FULLSCREEN_OVERSCAN = 1
FORM_LABEL_WIDTH = 132
MAX_DISPLAY_SCALE = 5.0
PREFETCH_DEBOUNCE_MS = 80

THUMBNAIL_TRIGGER_MARGIN = 48
THUMBNAIL_MIN_HEIGHT = 96
THUMBNAIL_MAX_HEIGHT = 320
THUMBNAIL_RESIZE_GRIP = 10
THUMBNAIL_HIDE_GRACE_SEC = 0.45
THUMBNAIL_HIDE_MARGIN = 28
THUMBNAIL_HIDE_DELAY_MS = 220

SIDE_PANEL_HIDE_GRACE_SEC = 0.45
SIDE_PANEL_HIDE_MARGIN = 36
SIDE_PANEL_HIDE_DELAY_MS = 220

PROFILE_UPDATE_INTERVAL_MS = 500

RESAMPLE_ALGORITHMS: dict[str, str] = {
    "lanczos3": "Lanczos3",
    "lanczos4": "Lanczos4",
    "bicubic": "Bicubic",
    "area": "Area",
}

ACTION_DEFS: list[tuple[str, str]] = [
    ("open_image", "画像を開く"),
    ("open_folder", "フォルダを開く"),
    ("next_page", "次ページ送り"),
    ("previous_page", "前ページ送り"),
    ("last_page", "最終ページ飛ばし"),
    ("first_page", "最初ページ飛ばし"),
    ("toggle_fullscreen", "全画面表示/解除"),
    ("toggle_thumbnail_panel", "サムネイル固定/自動表示"),
    ("toggle_side_panel", "右ペイン固定/自動表示"),
    ("toggle_compare", "比較モードオン/オフ"),
    ("actual_size", "等倍表示"),
    ("fit_view", "画面フィット表示"),
    ("rotate_right", "画像右回転"),
    ("rotate_left", "画像左回転"),
    ("flip_horizontal", "画像左右反転"),
    ("flip_vertical", "画像上下反転"),
]
