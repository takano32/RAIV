from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from constants import (
    ACTION_DEFS,
    ENGINE_LABELS,
    ENGINE_REALCUGAN,
    FORM_LABEL_WIDTH,
    REALESRGAN_MODELS,
    RESAMPLE_ALGORITHMS,
)


class UiBuilderMixin:
    def help_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #666;")
        return label

    def normalize_form_labels(self, *forms: QFormLayout) -> None:
        for form in forms:
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            form.setHorizontalSpacing(8)
            for row in range(form.rowCount()):
                item = form.itemAt(row, QFormLayout.LabelRole)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    widget.setFixedWidth(FORM_LABEL_WIDTH)

    def separator(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.HLine)
        frame.setFrameShadow(QFrame.Sunken)
        return frame

    def build_keyconfig_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self.help_label(
            "設定値をクリックすると割当を変更できます。Escを入力すると未割当に戻ります。"
            "Spaceは次ページ、Backspaceは前ページとして固定です。"
        ))
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.addWidget(QLabel("機能"), 0, 0)
        grid.addWidget(QLabel("キーボード"), 0, 1)
        grid.addWidget(QLabel("マウス"), 0, 2)
        self.key_binding_buttons: dict[tuple[str, str], QPushButton] = {}
        for row, (action_id, label) in enumerate(ACTION_DEFS, start=1):
            grid.addWidget(QLabel(label), row, 0)
            for column, kind in ((1, "keyboard"), (2, "mouse")):
                button = QPushButton()
                button.setMinimumWidth(132)
                button.clicked.connect(lambda _checked=False, aid=action_id, k=kind: self.edit_key_binding(aid, k))
                self.key_binding_buttons[(action_id, kind)] = button
                grid.addWidget(button, row, column)
        layout.addLayout(grid)
        reset_button = QPushButton("キーコンフィグを初期値に戻す")
        reset_button.clicked.connect(self.reset_key_bindings)
        layout.addWidget(reset_button)
        layout.addStretch(1)
        self.refresh_keyconfig_buttons()
        return content

    def _build_engine_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)

        form = QFormLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(list(ENGINE_LABELS.values()))
        self.engine_combo.setCurrentText(ENGINE_LABELS.get(self.config_data.engine, ENGINE_LABELS[ENGINE_REALCUGAN]))
        self.engine_combo.currentTextChanged.connect(self.on_engine_changed)
        form.addRow("エンジン", self.engine_combo)

        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["2", "3", "4"])
        self.scale_combo.setCurrentText(str(self.config_data.scale))
        self.scale_combo.currentTextChanged.connect(self.on_processing_settings_changed)
        form.addRow("倍率", self.scale_combo)

        self.denoise_combo = QComboBox()
        self.denoise_combo.addItems(["-1", "0", "1", "2", "3"])
        self.denoise_combo.setCurrentText(str(self.config_data.denoise))
        self.denoise_combo.currentTextChanged.connect(self.on_processing_settings_changed)
        form.addRow("ノイズ", self.denoise_combo)

        self.realesrgan_model_combo = QComboBox()
        self.realesrgan_model_combo.addItems(REALESRGAN_MODELS)
        self.realesrgan_model_combo.setCurrentText(self.config_data.realesrgan_model)
        self.realesrgan_model_combo.currentTextChanged.connect(self.on_processing_settings_changed)
        form.addRow("Real-ESRGANモデル", self.realesrgan_model_combo)

        self.tile_spin = QSpinBox()
        self.tile_spin.setRange(0, 16)
        self.tile_spin.setValue(self.config_data.tile)
        self.tile_spin.valueChanged.connect(self.on_processing_settings_changed)
        form.addRow("tile", self.tile_spin)
        layout.addLayout(form)

        self.denoise_help = self.help_label(
            "ノイズ: Real-CUGAN専用。-1 はノイズ除去なし。0/1/2/3 は数値が大きいほど強く除去します。"
        )
        layout.addWidget(self.denoise_help)
        self.realesrgan_model_help = self.help_label(
            "Real-ESRGANはノイズ値を使わず、モデルで画風や復元傾向を選びます。"
        )
        layout.addWidget(self.realesrgan_model_help)
        self.realesrgan_model_detail = self.help_label(
            "realesr-animevideov3: アニメ/イラスト向けの軽量標準モデル。"
            " realesrgan-x4plus: 写真や一般画像向け。"
            " realesrgan-x4plus-anime: アニメ/イラスト向けのx4plus派生モデル。"
            " RAIVではReal-ESRGAN選択中、倍率は4倍固定として処理します。"
        )
        layout.addWidget(self.realesrgan_model_detail)
        layout.addWidget(self.help_label(
            "tile: 0 は自動。小さめの値はGPUメモリ使用量を抑えますが、遅くなることがあります。"
        ))

        form3 = QFormLayout()
        self.realcugan_prefetch_spin = QSpinBox()
        self.realcugan_prefetch_spin.setRange(0, 99999)
        self.realcugan_prefetch_spin.setValue(self.config_data.realcugan_prefetch_count)
        self.realcugan_prefetch_spin.valueChanged.connect(self.on_processing_settings_changed)
        form3.addRow("エンジン先読み", self.realcugan_prefetch_spin)
        form3.addRow(self.help_label(
            "選択中の拡大エンジンで処理を先に進める枚数。大きいほど待ち時間を減らせますが、GPU負荷と一時ファイル作成が増えます。"
        ))

        self.skip_tall_check = QCheckBox("縦サイズが閾値以上なら拡大処理しない")
        self.skip_tall_check.setChecked(self.config_data.skip_realcugan_for_tall_images)
        self.skip_tall_check.stateChanged.connect(self.on_processing_settings_changed)
        self.skip_height_spin = QSpinBox()
        self.skip_height_spin.setRange(1, 99999)
        self.skip_height_spin.setValue(self.config_data.skip_realcugan_height_threshold)
        self.skip_height_spin.valueChanged.connect(self.on_processing_settings_changed)
        form3.addRow(self.skip_tall_check)
        form3.addRow("縦サイズ閾値(px)", self.skip_height_spin)
        form3.addRow(self.help_label(
            "モニタ解像度以上の画像をさらに拡大しても表示上の効果は小さく、処理時間とメモリ使用量が増えます。"
            "普段使うモニタの縦解像度に合わせる設定が目安です。"
        ))
        layout.addLayout(form3)

        self.save_scale_check = QCheckBox("拡大結果を倍率フォルダに保存")
        self.save_scale_check.setChecked(self.config_data.save_upscaled_to_scale_folder)
        self.save_scale_check.stateChanged.connect(self.on_processing_settings_changed)
        self.use_scale_cache_check = QCheckBox("倍率フォルダがあれば表示に使う")
        self.use_scale_cache_check.setChecked(self.config_data.use_scale_folder_cache)
        self.use_scale_cache_check.stateChanged.connect(self.on_processing_settings_changed)
        layout.addWidget(self.save_scale_check)
        layout.addWidget(self.use_scale_cache_check)

        self.archive_help = self.help_label(
            "アーカイブ表示中は保存先フォルダがないため、倍率フォルダ保存と倍率フォルダ読み込みは無効です。"
        )
        self.archive_help.hide()
        layout.addWidget(self.archive_help)

        rerun_button = QPushButton("再実行")
        rerun_button.clicked.connect(self.force_reprocess)
        layout.addWidget(rerun_button)
        layout.addWidget(self.separator())
        layout.addWidget(QLabel("コマンドテンプレート"))
        self.command_edit = QLineEdit(self.config_data.command_template)
        layout.addWidget(self.command_edit)
        exe_button = QPushButton("エンジンexeを選択")
        exe_button.clicked.connect(self.choose_engine_exe)
        layout.addWidget(exe_button)
        layout.addWidget(self.help_label("使用できる置換: {input} {output} {scale} {denoise} {tile} {model}"))
        layout.addStretch(1)
        self.normalize_form_labels(form, form3)
        return content

    def _build_general_tab(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)

        self.cleanup_check = QCheckBox("次回起動時に古い一時ファイルを削除")
        self.cleanup_check.setChecked(self.config_data.cleanup_temp_on_start)
        self.cleanup_check.stateChanged.connect(self.on_cleanup_changed)
        layout.addWidget(self.cleanup_check)
        layout.addWidget(self.separator())

        language_form = QFormLayout()
        self.language_combo = QComboBox()
        self.language_combo.addItem("日本語", "ja")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(0 if self.config_data.ui_language == "ja" else 1)
        self.language_combo.currentIndexChanged.connect(self.on_language_changed)
        self.language_label = QLabel("Language")
        self.language_label.setObjectName("languageLabel")
        language_form.addRow(self.language_label, self.language_combo)
        layout.addLayout(language_form)

        viewer_form = QFormLayout()
        self.viewer_prefetch_spin = QSpinBox()
        self.viewer_prefetch_spin.setRange(0, 99999)
        self.viewer_prefetch_spin.setValue(self.config_data.viewer_prefetch_count)
        self.viewer_prefetch_spin.valueChanged.connect(self.on_viewer_prefetch_changed)
        viewer_form.addRow("ビューアー先読み", self.viewer_prefetch_spin)
        layout.addLayout(viewer_form)
        layout.addWidget(self.help_label(
            "表示用に画像をメモリへ先読みする枚数。大きいほどページ送りは速くなりますが、メモリ使用量が増えます。"
        ))

        self.cpu_resample_check = QCheckBox("CPUリサンプルキャッシュを使う")
        self.cpu_resample_check.setChecked(self.config_data.cpu_resample_cache_enabled)
        self.cpu_resample_check.stateChanged.connect(self.on_resample_settings_changed)
        layout.addWidget(self.cpu_resample_check)

        resample_form = QFormLayout()
        self.cpu_resample_combo = QComboBox()
        self.cpu_resample_combo.addItems(RESAMPLE_ALGORITHMS.values())
        self.cpu_resample_combo.setCurrentText(
            RESAMPLE_ALGORITHMS.get(self.config_data.cpu_resample_algorithm, RESAMPLE_ALGORITHMS["lanczos3"])
        )
        self.cpu_resample_combo.currentTextChanged.connect(self.on_resample_settings_changed)
        self.cpu_resample_combo.setEnabled(self.cpu_resample_check.isChecked())
        resample_form.addRow("表示リサンプル方式", self.cpu_resample_combo)
        layout.addLayout(resample_form)
        layout.addWidget(self.help_label(
            "原寸と異なる表示サイズの画像を、よりきれいに見えるよう作成して保持します。オフにすると標準の高速表示になります。"
        ))
        layout.addWidget(self.help_label(
            "Lanczos3: 精細で標準的。Lanczos4: より鋭いがリンギングが出ることがあります。"
            "Bicubic: やや柔らかく自然。Area: 大きく縮小する時に安定し、ジャギーを抑えやすい方式です。"
        ))
        layout.addWidget(self.help_label(
            "Lanczos4はOpenCVがある環境ではLanczos4、ない環境ではLanczos3相当で処理します。"
        ))

        background_form = QFormLayout()
        bg_row = QHBoxLayout()
        self.background_edit = QLineEdit(self.config_data.background_color)
        bg_button = QPushButton("選択")
        bg_button.clicked.connect(self.choose_background_color)
        bg_row.addWidget(bg_button)
        bg_row.addWidget(self.background_edit)
        background_form.addRow("背景色", bg_row)
        self.background_edit.editingFinished.connect(self.on_background_changed)
        layout.addLayout(background_form)

        layout.addWidget(self.separator())
        self.compare_check = QCheckBox("比較モード")
        self.compare_check.setChecked(self.config_data.compare_enabled)
        self.compare_check.stateChanged.connect(self.on_compare_changed)
        layout.addWidget(self.compare_check)

        compare_form = QFormLayout()
        self.compare_slider = QSlider(Qt.Horizontal)
        self.compare_slider.setRange(0, 1000)
        self.compare_slider.setValue(self.config_data.compare_split)
        self.compare_slider.valueChanged.connect(self.on_compare_changed)
        compare_form.addRow("比較スライダー", self.compare_slider)
        compare_center_button = QPushButton("中央に戻す")
        compare_center_button.clicked.connect(self.reset_compare_split)
        compare_form.addRow("", compare_center_button)
        compare_color_row = QHBoxLayout()
        self.compare_line_edit = QLineEdit(self.config_data.compare_line_color)
        compare_color_button = QPushButton("選択")
        compare_color_button.clicked.connect(self.choose_compare_line_color)
        compare_color_row.addWidget(compare_color_button)
        compare_color_row.addWidget(self.compare_line_edit)
        compare_form.addRow("境界線色", compare_color_row)
        self.compare_line_edit.editingFinished.connect(self.on_compare_changed)
        self.compare_line_width_spin = QSpinBox()
        self.compare_line_width_spin.setRange(1, 20)
        self.compare_line_width_spin.setValue(self.config_data.compare_line_width)
        self.compare_line_width_spin.valueChanged.connect(self.on_compare_changed)
        compare_form.addRow("境界線の太さ(px)", self.compare_line_width_spin)
        layout.addLayout(compare_form)
        self.compare_swap_check = QCheckBox("比較の左右を入れ替える")
        self.compare_swap_check.setChecked(self.config_data.compare_swap_sides)
        self.compare_swap_check.stateChanged.connect(self.on_compare_changed)
        layout.addWidget(self.compare_swap_check)
        self.compare_shift_check = QCheckBox("比較中はShift+ドラッグで境界線を動かす")
        self.compare_shift_check.setChecked(self.config_data.compare_shift_drag_moves_boundary)
        self.compare_shift_check.stateChanged.connect(self.on_compare_changed)
        layout.addWidget(self.compare_shift_check)

        view_form = QFormLayout()
        self.zoom_label = QLabel("ズーム: 100%")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 500)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_slider_changed)
        view_form.addRow(self.zoom_label, self.zoom_slider)
        reset_button = QPushButton("表示を中央へリセット")
        reset_button.clicked.connect(self.viewer.reset_display_state)
        view_form.addRow("", reset_button)
        self.page_interval_spin = QSpinBox()
        self.page_interval_spin.setRange(0, 100)
        self.page_interval_spin.setValue(self.config_data.page_scroll_interval_ms)
        self.page_interval_spin.valueChanged.connect(self.on_general_settings_changed)
        view_form.addRow("ページ送り間隔(ms)", self.page_interval_spin)
        layout.addLayout(view_form)
        layout.addWidget(self.help_label("ホイールやキー操作で連続ページ送りする時の間隔。0 は最短です。"))

        page_position_form = QFormLayout()
        self.page_position_slider = QSlider(Qt.Horizontal)
        self.page_position_slider.setRange(0, 0)
        self.page_position_slider.setEnabled(False)
        self.page_position_slider.setInvertedAppearance(self.config_data.invert_page_position_slider)
        self.page_position_slider.valueChanged.connect(self.on_page_position_slider_changed)
        page_position_row = QHBoxLayout()
        self.page_position_count_label = QLabel("0/0")
        self.page_position_count_label.setMinimumWidth(52)
        self.page_position_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        page_position_row.addWidget(self.page_position_slider, 1)
        page_position_row.addWidget(self.page_position_count_label)
        page_position_form.addRow("ページ位置", page_position_row)
        layout.addLayout(page_position_form)

        self.invert_page_position_check = QCheckBox("ページ位置スライダーの左右を入れ替える")
        self.invert_page_position_check.setChecked(self.config_data.invert_page_position_slider)
        self.invert_page_position_check.stateChanged.connect(self.on_page_position_slider_direction_changed)
        layout.addWidget(self.invert_page_position_check)
        layout.addWidget(self.help_label(
            "オンにすると、ページ位置スライダーとサムネイル列の左右方向が連動して入れ替わります。"
        ))

        self.thumbnail_enabled_check = QCheckBox("画面下部にサムネイルを表示する")
        self.thumbnail_enabled_check.setChecked(self.config_data.thumbnail_enabled)
        self.thumbnail_enabled_check.stateChanged.connect(self.on_thumbnail_settings_changed)
        layout.addWidget(self.thumbnail_enabled_check)
        layout.addWidget(self.help_label(
            "オフにするとサムネイル生成処理も停止します。大量の画像を開く時に、初期表示や先読みを軽くできます。"
        ))
        self.thumbnail_pinned_check = QCheckBox("サムネイル列を固定表示する")
        self.thumbnail_pinned_check.setChecked(self.config_data.thumbnail_pinned)
        self.thumbnail_pinned_check.stateChanged.connect(self.on_thumbnail_settings_changed)
        self.thumbnail_pinned_check.setEnabled(self.thumbnail_enabled_check.isChecked())
        layout.addWidget(self.thumbnail_pinned_check)

        self.wrap_page_check = QCheckBox("最後/最初でページ送りしたら反対側へ移動")
        self.wrap_page_check.setChecked(self.config_data.wrap_page_navigation)
        self.wrap_page_check.stateChanged.connect(self.on_general_settings_changed)
        layout.addWidget(self.wrap_page_check)
        self.preserve_view_check = QCheckBox("ページ送り時にズームと表示位置を維持")
        self.preserve_view_check.setChecked(self.config_data.preserve_view_on_page_navigation)
        self.preserve_view_check.stateChanged.connect(self.on_general_settings_changed)
        layout.addWidget(self.preserve_view_check)
        self.horizontal_wheel_check = QCheckBox("マウス横スクロールでページ送り")
        self.horizontal_wheel_check.setChecked(self.config_data.horizontal_wheel_navigation)
        self.horizontal_wheel_check.stateChanged.connect(self.on_general_settings_changed)
        layout.addWidget(self.horizontal_wheel_check)
        self.horizontal_wheel_invert_check = QCheckBox("横スクロールのページ送り方向を反転")
        self.horizontal_wheel_invert_check.setChecked(self.config_data.horizontal_wheel_inverted)
        self.horizontal_wheel_invert_check.stateChanged.connect(self.on_general_settings_changed)
        layout.addWidget(self.horizontal_wheel_invert_check)
        self.hide_cursor_fullscreen_check = QCheckBox("全画面表示時にマウスカーソルを非表示")
        self.hide_cursor_fullscreen_check.setChecked(self.config_data.hide_cursor_in_fullscreen)
        self.hide_cursor_fullscreen_check.stateChanged.connect(self.on_general_settings_changed)
        layout.addWidget(self.hide_cursor_fullscreen_check)

        self.status_label = QLabel("画像またはフォルダ/アーカイブをドロップしてください")
        self.status_label.setWordWrap(True)
        layout.addWidget(QLabel("状態"))
        layout.addWidget(self.status_label)
        layout.addWidget(self.separator())

        self.show_log_check = QCheckBox("ログを表示")
        self.show_log_check.setChecked(self.config_data.show_log_panel)
        self.show_log_check.stateChanged.connect(self.on_log_visibility_changed)
        layout.addWidget(self.show_log_check)

        self.log_container = QWidget()
        log_layout = QVBoxLayout(self.log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self.prefetch_progress_panel = QWidget()
        progress_layout = QFormLayout(self.prefetch_progress_panel)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        self.original_prefetch_bar = QProgressBar()
        self.upscale_progress_bar = QProgressBar()
        self.processed_prefetch_bar = QProgressBar()
        self.pixmap_prefetch_bar = QProgressBar()
        for bar in (self.original_prefetch_bar, self.upscale_progress_bar, self.processed_prefetch_bar, self.pixmap_prefetch_bar):
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setTextVisible(True)
        progress_layout.addRow("拡大前メモリ読込", self.original_prefetch_bar)
        progress_layout.addRow("拡大画像生成", self.upscale_progress_bar)
        progress_layout.addRow("拡大後メモリ読込", self.processed_prefetch_bar)
        progress_layout.addRow("表示用QPixmap", self.pixmap_prefetch_bar)
        log_layout.addWidget(self.prefetch_progress_panel)
        self.log_label = QLabel("ログ")
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(160)
        self.log_edit.setSizePolicy(self.log_edit.sizePolicy().horizontalPolicy(), QSizePolicy.Fixed)
        self.log_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        log_layout.addWidget(self.log_label)
        log_layout.addWidget(self.log_edit)
        layout.addWidget(self.log_container)

        self.show_profile_check = QCheckBox("内部プロファイリングを表示")
        self.show_profile_check.setChecked(self.config_data.show_profile_panel)
        self.show_profile_check.stateChanged.connect(self.on_profile_visibility_changed)
        layout.addWidget(self.show_profile_check)
        self.profile_panel = QLabel()
        self.profile_panel.setWordWrap(True)
        self.profile_panel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.profile_panel)
        layout.addStretch(1)

        self.normalize_form_labels(language_form, viewer_form, resample_form, background_form, compare_form, view_form, page_position_form)
        return content

    def _build_side_panel(self) -> QWidget:
        root = QWidget()
        root.setMinimumWidth(240)
        root.setAutoFillBackground(True)
        root.setObjectName("sidePanel")
        root.setStyleSheet("#sidePanel { background: palette(window); }")
        layout = QVBoxLayout(root)

        header = QHBoxLayout()
        header.addWidget(QLabel("設定"))
        header.addStretch(1)
        self.pin_button = QPushButton("固定")
        self.pin_button.setCheckable(True)
        self.pin_button.setChecked(self.config_data.side_panel_pinned)
        self.pin_button.toggled.connect(self.on_side_panel_pin_changed)
        header.addWidget(self.pin_button)
        layout.addLayout(header)
        self.pin_button.setText("固定中" if self.config_data.side_panel_pinned else "自動表示")

        self.tabs = QTabWidget()
        engine_tab = QScrollArea()
        general_tab = QScrollArea()
        keyconfig_tab = QScrollArea()
        engine_tab.setWidgetResizable(True)
        general_tab.setWidgetResizable(True)
        keyconfig_tab.setWidgetResizable(True)
        self.tabs.addTab(engine_tab, "エンジン設定")
        self.tabs.addTab(general_tab, "全般")
        self.tabs.addTab(keyconfig_tab, "キーコンフィグ")
        self.tabs.currentChanged.connect(self.on_settings_tab_changed)
        layout.addWidget(self.tabs)

        engine_tab.setWidget(self._build_engine_tab())
        general_tab.setWidget(self._build_general_tab())
        keyconfig_tab.setWidget(self.build_keyconfig_tab())

        tab_index = {"realcugan": 0, "general": 1, "keyconfig": 2}.get(self.config_data.settings_tab, 0)
        self.tabs.setCurrentIndex(tab_index)
        self.apply_engine_ui()
        self.apply_log_visibility()
        QTimer.singleShot(0, self.apply_language)
        return root
