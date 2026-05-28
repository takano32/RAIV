from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    process_started = Signal(str)
    process_done = Signal(object)
    folder_images_ready = Signal(object, object)
    prefetch_done = Signal(int, object, object, object, object)
    thumbnail_done = Signal(int, int, object)
    profile_event = Signal(str, float)
