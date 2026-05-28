from __future__ import annotations

from constants import PROFILE_UPDATE_INTERVAL_MS


class ProfileMixin:
    def append_log(self, text: str) -> None:
        self.log_edit.append(text)

    def append_log_if_visible(self, text: str) -> None:
        if getattr(self, "closing", False):
            return
        if self.show_log_panel:
            self.append_log(text)

    def record_profile(self, name: str, elapsed_ms: float) -> None:
        if getattr(self, "closing", False) or elapsed_ms < 0:
            return
        stats = self.profile_stats.setdefault(name, {"count": 0.0, "total": 0.0, "last": 0.0, "max": 0.0})
        stats["count"] += 1.0
        stats["total"] += float(elapsed_ms)
        stats["last"] = float(elapsed_ms)
        stats["max"] = max(stats["max"], float(elapsed_ms))
        profile_check = getattr(self, "show_profile_check", None)
        if profile_check is not None and profile_check.isChecked() and not self.profile_update_timer.isActive():
            self.profile_update_timer.start(PROFILE_UPDATE_INTERVAL_MS)

    def update_profile_panel(self) -> None:
        if not hasattr(self, "profile_panel"):
            return
        profile_check = getattr(self, "show_profile_check", None)
        if profile_check is None or not profile_check.isChecked():
            self.profile_panel.hide()
            return
        lines = []
        for name, stats in sorted(self.profile_stats.items()):
            avg = stats["total"] / max(1.0, stats["count"])
            lines.append(f"{name}: last {stats['last']:.1f} ms / avg {avg:.1f} ms / max {stats['max']:.1f} ms")
        empty = "Profile: no measurements yet" if self.ui_language() == "en" else "プロファイル: まだ計測値がありません"
        self.profile_panel.setText("\n".join(lines[-8:]) if lines else empty)
        self.profile_panel.show()
