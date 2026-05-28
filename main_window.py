from __future__ import annotations

import queue
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter, QWidget

from bindings import duplicate_binding_signatures
from config import load_config, save_config
from constants import (
    APP_ICON_ICO,
    APP_ICON_PNG,
    APP_ID,
    APP_NAME,
    TEMP_WORK_PREFIX,
    PROFILE_UPDATE_INTERVAL_MS,
)
from image_view import GLImageView
from mixin_archive import ArchiveMixin
from mixin_fullscreen import FullscreenMixin
from mixin_input import InputMixin
from mixin_language import LanguageMixin
from mixin_navigation import NavigationMixin
from mixin_prefetch import PrefetchMixin
from mixin_processing import ProcessingMixin
from mixin_profile import ProfileMixin
from mixin_settings import SettingsMixin
from mixin_side_panel import SidePanelMixin
from mixin_thumbnail import ThumbnailMixin
from mixin_ui_builder import UiBuilderMixin
from signals import AppSignals
from system import enable_high_dpi_awareness, set_process_app_user_model_id


class MainWindow(
    UiBuilderMixin,
    SettingsMixin,
    LanguageMixin,
    ProfileMixin,
    ThumbnailMixin,
    SidePanelMixin,
    FullscreenMixin,
    NavigationMixin,
    ProcessingMixin,
    PrefetchMixin,
    ArchiveMixin,
    InputMixin,
    QMainWindow,
):
    def __init__(self) -> None:
        super().__init__()
        self.initializing = True
        self.config_data = load_config()
        self.duplicate_keyboard_bindings = duplicate_binding_signatures(self.config_data.key_bindings, "keyboard")
        self.show_log_panel = self.config_data.show_log_panel
        if self.config_data.cleanup_temp_on_start:
            self._cleanup_stale_temp_files()
            self.config_data.cleanup_temp_on_start = False
            save_config(self.config_data)

        self.signals = AppSignals()
        self.signals.process_started.connect(self.on_process_started)
        self.signals.process_done.connect(self.on_process_done)
        self.signals.folder_images_ready.connect(self.on_folder_images_ready)
        self.signals.prefetch_done.connect(self.on_prefetch_done)
        self.signals.thumbnail_done.connect(self.on_thumbnail_done)
        self.signals.profile_event.connect(self.record_profile)

        # image state
        self.image_paths: list[Path] = []
        self.image_path_set: set[Path] = set()
        self.image_path_string_set: set[str] = set()
        self.current_index = -1
        self.last_navigation_step = 1
        self.folder_list_loading = False
        self.deferred_page_steps = 0
        self.original_cache: OrderedDict[Path, QImage] = OrderedDict()
        self.processed_cache: OrderedDict[tuple[str, str, int, int, int, str], QImage] = OrderedDict()
        self.processing_paths: set[Path] = set()
        self.queued_paths: set[Path] = set()

        # worker queues
        self.work_queue: queue.Queue[Path | None] = queue.Queue()
        self.prefetch_io_queue: queue.PriorityQueue[tuple[int, int, int, str, object, str, str]] = queue.PriorityQueue()
        self.prefetch_io_sequence = 0
        self.prefetch_io_lock = threading.Lock()

        # thumbnail state
        self.thumbnail_queue: queue.PriorityQueue[tuple[int, int, int, int, str]] = queue.PriorityQueue()
        self.thumbnail_sequence = 0
        self.thumbnail_lock = threading.Lock()
        self.thumbnail_generation = 0
        self.thumbnail_pending: set[int] = set()
        self.thumbnail_ready_indexes: set[int] = set()
        self.thumbnail_items: list = []
        self.thumbnail_overlay_visible = False
        self.thumbnail_height = int(self.config_data.thumbnail_height)
        self.thumbnail_render_size = int(self.config_data.thumbnail_size)
        self.thumbnail_resizing = False
        self.thumbnail_hide_suppressed_until = 0.0
        self.thumbnail_rebuild_index = 0
        self.thumbnail_rebuild_timer = QTimer(self)
        self.thumbnail_rebuild_timer.setSingleShot(True)
        self.thumbnail_rebuild_timer.timeout.connect(self.continue_thumbnail_rebuild)
        self.thumbnail_resize_refresh_timer = QTimer(self)
        self.thumbnail_resize_refresh_timer.setSingleShot(True)
        self.thumbnail_resize_refresh_timer.timeout.connect(self.refresh_thumbnail_icons_for_size)

        # profiling
        self.profile_stats: dict[str, dict[str, float]] = {}
        self.profile_update_timer = QTimer(self)
        self.profile_update_timer.setSingleShot(True)
        self.profile_update_timer.timeout.connect(self.update_profile_panel)

        # archive state
        self.archive_temp_dir: Path | None = None
        self.retired_archive_temp_dirs: list[Path] = []
        self.archive_display_names: dict[Path, str] = {}
        self.archive_source_path: Path | None = None
        self.archive_disabled_scale_options: tuple[bool, bool] | None = None
        self.process_temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_WORK_PREFIX))
        self.write_temp_lock(self.process_temp_dir)

        # navigation timers
        self.page_scroll_timer = QTimer(self)
        self.page_scroll_timer.timeout.connect(self._drain_page_steps)
        self.pending_page_steps = 0
        self.prefetch_timer = QTimer(self)
        self.prefetch_timer.setSingleShot(True)
        self.prefetch_timer.timeout.connect(self.schedule_prefetch)

        # prefetch state
        self.prefetch_generation = 0
        self.prefetching_original_paths: set[Path] = set()
        self.prefetching_processed_keys: set[tuple[str, str, int, int, int, str]] = set()
        self.prefetch_viewer_plan: list[Path] = []
        self.prefetch_engine_plan: list[Path] = []
        self.prefetch_engine_done_paths: set[Path] = set()
        self.pixmap_prefetch_log_accum = 0

        # panel/fullscreen state
        self.side_panel_visible_before_fullscreen = True
        self.side_panel_width = int(self.config_data.side_panel_width)
        self.fullscreen_cursor_hidden = False
        self.side_panel_overlay = False
        self.borderless_fullscreen = False
        self.before_fullscreen_geometry = QRect()
        self.before_fullscreen_flags = self.windowFlags()
        self.before_fullscreen_state = Qt.WindowNoState
        self.fullscreen_enforce_pending = False
        self.overlay_resizing = False
        self.overlay_modal_guard = False
        self.overlay_hide_suppressed_until = 0.0
        self.adjusting_splitter = False
        self.closing = False

        # window setup
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        if APP_ICON_ICO.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_ICO)))
        elif APP_ICON_PNG.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PNG)))

        # viewer host + viewer
        self.viewer_host = QWidget()
        self.viewer_host.setMouseTracking(True)
        self.viewer_host.installEventFilter(self)
        self.viewer = GLImageView()
        self.viewer.setParent(self.viewer_host)
        self.viewer.pageRequested.connect(self.queue_page_steps)
        self.viewer.firstRequested.connect(self.show_first_image)
        self.viewer.lastRequested.connect(self.show_last_image)
        self.viewer.zoomChanged.connect(self.update_zoom_label)
        self.viewer.splitChanged.connect(self.on_viewer_split_changed)
        self.viewer.fullscreenRequested.connect(self.toggle_fullscreen)
        self.viewer.resetRequested.connect(self.viewer.reset_display_state)
        self.viewer.actualSizeRequested.connect(self.viewer.zoom_to_actual_size)
        self.viewer.actionRequested.connect(self.perform_action)
        self.viewer.pixmapPrefetchProgress.connect(self.on_pixmap_prefetch_progress)
        self.viewer.installEventFilter(self)

        # thumbnail panel
        self.thumbnail_panel = self.build_thumbnail_panel()
        self.thumbnail_panel.setParent(self.viewer_host)
        self.thumbnail_panel.installEventFilter(self)
        self.thumbnail_list.installEventFilter(self)
        self.thumbnail_list.viewport().installEventFilter(self)

        # side panel + splitter
        self.side_panel = self._build_side_panel()
        self.side_panel.installEventFilter(self)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.viewer_host)
        self.splitter.addWidget(self.side_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self.on_splitter_moved)
        self.setCentralWidget(self.splitter)

        self._restore_geometry()
        self._apply_settings_to_viewer()
        self.initializing = False

        # background workers
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()
        self.prefetch_io_workers = [
            threading.Thread(target=self._prefetch_io_worker_loop, daemon=True)
            for _ in range(2)
        ]
        for worker in self.prefetch_io_workers:
            worker.start()
        self.thumbnail_worker = threading.Thread(target=self._thumbnail_worker_loop, daemon=True)
        self.thumbnail_worker.start()

    def closeEvent(self, event) -> None:
        self.closing = True
        self._show_fullscreen_cursor()
        self.persist_config()
        self.work_queue.put(None)
        paths = list(self.retired_archive_temp_dirs)
        if self.archive_temp_dir:
            paths.append(self.archive_temp_dir)
        if self.process_temp_dir:
            paths.append(self.process_temp_dir)
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
        super().closeEvent(event)


def main() -> None:
    enable_high_dpi_awareness()
    set_process_app_user_model_id(APP_ID)
    app = QApplication([])
    app.setApplicationName(APP_NAME)
    if APP_ICON_ICO.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_ICO)))
    window = MainWindow()
    window.show()
    app.exec()
