import os
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QFormLayout,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
    QPushButton, QLabel, QGroupBox, QFileDialog, QMessageBox,
    QSlider, QPlainTextEdit
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from src.utils.preset_manager import PresetManager, DEFAULT_SETTINGS
from src.core.bitrate_calc import BitrateCalculator
from src.core.ffmpeg_worker import FFmpegWorker
from src.core.command_build import build_ffmpeg_commands
from src.utils.path_helper import get_tool_path

ENCODER_DISPLAY_NAMES = {
    "libx264": "H.264 (CPU)",
    "h264_nvenc": "H.264 (NVIDIA GPU)",
    "h264_amf": "H.264 (AMD GPU)",
    "h264_qsv": "H.264 (Intel GPU)",
    "libx265": "H.265/HEVC (CPU)",
    "hevc_nvenc": "H.265/HEVC (NVIDIA GPU)",
    "hevc_amf": "H.265/HEVC (AMD GPU)",
    "hevc_qsv": "H.265/HEVC (Intel GPU)",
    "libsvtav1": "AV1 (CPU)",
    "av1_nvenc": "AV1 (NVIDIA GPU)",
    "av1_amf": "AV1 (AMD GPU)",
    "av1_qsv": "AV1 (Intel GPU)"
}

def detect_available_encoders() -> List[str]:
    """
    PC環境で実際に動作する動画エンコーダーのリストを返す。
    CPUエンコーダーは常に有効とし、GPUエンコーダーはテストエンコードで判定する。
    """
    ffmpeg_bin = get_tool_path("ffmpeg")
    candidate_encoders = [
        "libx264", "h264_nvenc", "h264_amf", "h264_qsv",
        "libx265", "hevc_nvenc", "hevc_amf", "hevc_qsv",
        "libsvtav1", "av1_nvenc", "av1_amf", "av1_qsv"
    ]
    available = []
    
    for encoder in candidate_encoders:
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "color=c=black:s=128x128:r=30",
            "-frames:v", "2",
            "-c:v", encoder,
            "-f", "null", "-"
        ]
        #print(cmd)
        
        try:
            startupinfo = None
            if os.name == 'nt' and hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                timeout=3
            )
            
            if res.returncode == 0:
                available.append(encoder)
        except Exception as e:
            #print(e)
            pass
        #print(encoder, res.returncode)
        #print(res.stderr.decode(errors="ignore"))
    #print(available)
    return available

class SettingsPane(QGroupBox):
    settings_changed = Signal()
    # Emitted when preview file selection changes or settings change — for command preview update
    command_preview_requested = Signal(object)  # Emits file_info dict or None

    def __init__(self, parent=None):
        super().__init__("2. エンコード設定 & プレビュー (Settings)", parent)
        self.preset_manager = PresetManager()
        self.preview_worker: Optional[FFmpegWorker] = None
        self._preview_output_path: str = ""
        self.available_encoders = detect_available_encoders()

        self._init_ui()
        self.load_from_preset(self.preset_manager.load_settings())

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # Tab Widget
        self.tab_widget = QTabWidget()

        # Tab A: Video Removal
        self.tab_a = QWidget()
        self._init_tab_a()
        self.tab_widget.addTab(self.tab_a, "映像消去 (Audio Only)")

        # Tab B: Quality Compression
        self.tab_b = QWidget()
        self._init_tab_b()
        self.tab_widget.addTab(self.tab_b, "圧縮 (品質ベース)")

        # Tab C: Target Size Compression
        self.tab_c = QWidget()
        self._init_tab_c()
        self.tab_widget.addTab(self.tab_c, "サイズ指定圧縮 (2パス)")

        main_layout.addWidget(self.tab_widget)

        # Custom Options
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("追加FFmpegオプション:"))
        self.txt_custom_options = QLineEdit()
        self.txt_custom_options.setPlaceholderText("例: -tune film -pix_fmt yuv420p")
        custom_layout.addWidget(self.txt_custom_options)
        main_layout.addLayout(custom_layout)

        # Preset Buttons
        preset_layout = QHBoxLayout()
        self.btn_save_preset = QPushButton("💾 プリセット保存")
        self.btn_load_preset = QPushButton("📂 プリセット読み込み")
        preset_layout.addWidget(self.btn_save_preset)
        preset_layout.addWidget(self.btn_load_preset)
        preset_layout.addStretch()
        main_layout.addLayout(preset_layout)

        # ---- Preview Section ----
        preview_box = QGroupBox("10秒 リアルタイムプレビュー")
        preview_layout = QVBoxLayout(preview_box)

        preview_ctrl_layout = QHBoxLayout()
        preview_ctrl_layout.addWidget(QLabel("対象ファイル:"))
        self.cmb_preview_file = QComboBox()
        preview_ctrl_layout.addWidget(self.cmb_preview_file, 1)

        self.btn_generate_preview = QPushButton("🎬 10秒プレビュー作成・再生")
        self.btn_generate_preview.setStyleSheet("font-weight: bold; background-color: #0d6efd; color: white;")
        preview_ctrl_layout.addWidget(self.btn_generate_preview)
        preview_layout.addLayout(preview_ctrl_layout)

        # Video Player Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(200)
        self.video_widget.setStyleSheet("background-color: black;")
        preview_layout.addWidget(self.video_widget)

        # Player Controls
        player_ctrl_layout = QHBoxLayout()
        self.btn_play = QPushButton("▶ 再生")
        self.btn_pause = QPushButton("⏸️ 一時停止")
        self.btn_stop = QPushButton("⏹️ 停止")

        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        player_ctrl_layout.addWidget(self.btn_play)
        player_ctrl_layout.addWidget(self.btn_pause)
        player_ctrl_layout.addWidget(self.btn_stop)

        player_ctrl_layout.addWidget(QLabel("音量:"))
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(80)
        self.audio_output.setVolume(0.8)
        player_ctrl_layout.addWidget(self.slider_volume)

        preview_layout.addLayout(player_ctrl_layout)
        main_layout.addWidget(preview_box)

        # ---- Command Preview (below preview section) ----
        cmd_preview_box = QGroupBox("実行コマンドプレビュー")
        cmd_preview_layout = QVBoxLayout(cmd_preview_box)

        self.txt_command_preview = QPlainTextEdit()
        self.txt_command_preview.setReadOnly(True)
        self.txt_command_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.txt_command_preview.setMaximumHeight(100)
        self.txt_command_preview.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; "
            "background-color: #212529; color: #adb5bd;"
        )
        cmd_preview_layout.addWidget(self.txt_command_preview)
        main_layout.addWidget(cmd_preview_box)

        # Connect signals
        self.tab_widget.currentChanged.connect(self._on_settings_changed)
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_load_preset.clicked.connect(self._on_load_preset)
        self.btn_generate_preview.clicked.connect(self._on_generate_preview)
        self.cmb_preview_file.currentIndexChanged.connect(self._on_preview_file_changed)

        self.btn_play.clicked.connect(self.media_player.play)
        self.btn_pause.clicked.connect(self.media_player.pause)
        self.btn_stop.clicked.connect(self.media_player.stop)
        self.slider_volume.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

    # ------------------- Tab A Init -------------------
    def _init_tab_a(self):
        layout = QFormLayout(self.tab_a)

        self.cmb_audio_format = QComboBox()
        self.cmb_audio_format.addItems(["mp3", "aac", "wav", "flac", "m4a"])
        layout.addRow("⚙️音声出力フォーマット(形式):", self.cmb_audio_format)
        self.cmb_audio_format.setToolTip("音声の出力フォーマットを選択します。mp3から変えなくていいと思う。しらんけど。")


        self.txt_a_suffix = QLineEdit("_novideo")
        layout.addRow("🏷️ ファイル名の末尾:", self.txt_a_suffix)
        self.txt_a_suffix.setToolTip("処理後のファイルを区別するために付けます。")

        # Connect signals
        self.cmb_audio_format.currentIndexChanged.connect(self._on_settings_changed)
        self.txt_a_suffix.textChanged.connect(self._on_settings_changed)

    # ------------------- Tab B Init -------------------
    def _init_tab_b(self):
        layout = QFormLayout(self.tab_b)

        self.cmb_b_res = QComboBox()
        self.cmb_b_res.addItems(["元のまま", "1920x1080", "1280x720", "854x480", "640x360"])
        layout.addRow("🖥️解像度:", self.cmb_b_res)
        self.cmb_b_res.setToolTip("動画の解像度を選択します")

        self.cmb_b_fps = QComboBox()
        self.cmb_b_fps.addItems(["元のまま", "60", "50", "30", "24"])
        layout.addRow("🎬フレームレート (FPS):", self.cmb_b_fps)
        self.cmb_b_fps.setToolTip("動画のフレームレートを選択します。元が60とかじゃない限り変えなくていいと思う。")

        self.cmb_b_encoder = QComboBox()
        for enc in self.available_encoders:
            self.cmb_b_encoder.addItem(ENCODER_DISPLAY_NAMES.get(enc, enc), enc)
        layout.addRow("⚙️エンコーダ(方式):", self.cmb_b_encoder)
        self.cmb_b_encoder.setToolTip("H.264:一般的でどこでも再生できる。\nHEVC:最近のスマホやPCならこっちのほうが容量小さいかも。\nAV1:最新の一番容量が小さいやつ。ただ再生できる環境がまだ少ない。あと時間かかる。\n GPU使うと早くなるけど、圧縮効率は少し落ちるらしい")
        
        # CRF slider and spinbox
        crf_layout = QHBoxLayout()
        # 1. 左右のガイド用ラベルを作成
        self.lbl_crf_left = QLabel("💎高画質")
        self.lbl_crf_right = QLabel("📦低サイズ")

        # 文字を少し小さく・灰色にしてスッキリ見せる見た目の設定 (スタイリング)
        self.lbl_crf_left.setStyleSheet("color: gray; font-size: 11px;")
        self.lbl_crf_right.setStyleSheet("color: gray; font-size: 11px;")

        self.slider_b_crf = QSlider(Qt.Horizontal)
        self.slider_b_crf.setRange(18, 51)
        self.slider_b_crf.setValue(23)
        self.spn_b_crf = QSpinBox()
        self.spn_b_crf.setRange(18, 51)
        self.spn_b_crf.setValue(23)

        self.slider_b_crf.valueChanged.connect(self.spn_b_crf.setValue)
        self.spn_b_crf.valueChanged.connect(self.slider_b_crf.setValue)

        crf_layout.addWidget(self.lbl_crf_left)
        crf_layout.addWidget(self.slider_b_crf)
        crf_layout.addWidget(self.spn_b_crf)
        crf_layout.addWidget(self.lbl_crf_right)
        layout.addRow("💎品質:", crf_layout)

        crf_tooltip = (
            "【画質の目安数値 (CRF)】\n"
            "・左側 : 高画質（劣化はほぼ無し / 容量は大きめ）\n"
            "・標準 (23～28) \n"
            "・右側 : 容量重視（かなり軽量化 / 画質は控えめ）\n"
            "プレビュー見ながら、どこまで落とせるか(数字をあげられるか)試しましょう！\n"
        )

        self.slider_b_crf.setToolTip(crf_tooltip)
        self.spn_b_crf.setToolTip(crf_tooltip)
        self.lbl_crf_left.setToolTip(crf_tooltip)
        self.lbl_crf_right.setToolTip(crf_tooltip)

        self.cmb_b_preset = QComboBox()
        self.cmb_b_preset.setCurrentText("medium")
        layout.addRow("⏱️処理速度:", self.cmb_b_preset)
        self.cmb_b_preset.setToolTip("速くするほどサイズが小さくなり、遅くするほどサイズが大きくなります。")

        self.chk_b_mono = QCheckBox("モノラル化")
        layout.addRow("🎧音声チャンネル:", self.chk_b_mono)
        self.chk_b_mono.setToolTip("モノラル化とは左耳右耳用(ステレオ)で2つある音声を合わせて1つにすることです。\nチェックを入れると音声のファイルサイズが約半分になります。")

        self.cmb_b_abitrate = QComboBox()
        self.cmb_b_abitrate.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        self.cmb_b_abitrate.setCurrentText("128k")
        layout.addRow("🎵音声ビットレート:", self.cmb_b_abitrate)
        self.cmb_b_abitrate.setToolTip("音声のビットレートとは1秒間当たりのデータ量です。数値が大きいほど音質が良くなります。\n普通は128kくらい。64kでも聞こえる。\n 音楽じゃなければ64でいいんじゃないかな")

        self.txt_b_suffix = QLineEdit("_compressed")
        layout.addRow("🏷️ファイル名の末尾:", self.txt_b_suffix)
        self.txt_b_suffix.setToolTip("処理後のファイルを区別するために付けます。")

        self.cmb_b_encoder.currentIndexChanged.connect(self._on_encoder_changed)
        # Connect signals
        for widget in [self.cmb_b_res, self.cmb_b_fps, self.cmb_b_encoder, self.spn_b_crf,
                       self.cmb_b_preset, self.chk_b_mono, self.cmb_b_abitrate]:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._on_settings_changed)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._on_settings_changed)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._on_settings_changed)
        self.txt_b_suffix.textChanged.connect(self._on_settings_changed)

        # 3. 初期表示のために手動で1回呼び出し
        self._on_encoder_changed()

    # ------------------- Tab C Init -------------------
    def _init_tab_c(self):
        layout = QFormLayout(self.tab_c)

        self.cmb_c_res = QComboBox()
        self.cmb_c_res.addItems(["元のまま", "1920x1080", "1280x720", "854x480", "640x360"])
        layout.addRow("🖥️解像度:", self.cmb_c_res)

        self.cmb_c_fps = QComboBox()
        self.cmb_c_fps.addItems(["元のまま", "60", "50", "30", "24"])
        layout.addRow("🎬フレームレート (FPS):", self.cmb_c_fps)

        self.cmb_c_encoder = QComboBox()
        for enc in self.available_encoders:
            self.cmb_c_encoder.addItem(ENCODER_DISPLAY_NAMES.get(enc, enc), enc)
        layout.addRow("⚙️エンコーダ(方式):", self.cmb_c_encoder)
        self.cmb_c_encoder.setToolTip("H.264:一般的でどこでも再生できる。\nHEVC:最近のスマホやPCならこっちのほうが容量小さいかも。\nAV1:最新の一番容量が小さいやつ。ただ再生できる環境がまだ少ない。あと時間かかる。\n GPU : 使うと処理が速くなるけど、圧縮率は少し落ちるらしい")

        self.spn_c_target_mb = QDoubleSpinBox()
        self.spn_c_target_mb.setRange(1.0, 10000.0)
        self.spn_c_target_mb.setValue(50.0)
        self.spn_c_target_mb.setSuffix(" MB")
        layout.addRow("🎯目標ファイルサイズ:", self.spn_c_target_mb)
        self.spn_c_target_mb.setToolTip("動画の目標サイズを入力します。")

        self.chk_c_mono = QCheckBox("モノラル化")
        layout.addRow("🎧音声チャンネル:", self.chk_c_mono)
        self.chk_c_mono.setToolTip("モノラル化とは左耳右耳用(ステレオ)で2つある音声を合わせて1つにすることです。\nチェックを入れると音声のファイルサイズが約半分になります。")

        self.cmb_c_abitrate = QComboBox()
        self.cmb_c_abitrate.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        self.cmb_c_abitrate.setCurrentText("128k")
        layout.addRow(" 🎵音声ビットレート:", self.cmb_c_abitrate)
        self.cmb_c_abitrate.setToolTip("音声のビットレートとは1秒間当たりのデータ量です。数値が大きいほど音質が良くなります。\n普通は128kくらい。64kでも聞こえる。\n 音楽じゃなければ64でいいんじゃないかな")

        self.txt_c_suffix = QLineEdit("_targetsize")
        layout.addRow("🏷️ファイル名の末尾:", self.txt_c_suffix)
        self.txt_c_suffix.setToolTip("処理後のファイルを区別するために付けます。")

        self.lbl_c_calc_info = QLabel("推定映像ビットレート: - kbps")
        self.lbl_c_calc_info.setStyleSheet("color: #198754; font-weight: bold;")
        layout.addRow("計算結果:", self.lbl_c_calc_info)

        # Connect signals
        for widget in [self.cmb_c_res, self.cmb_c_fps, self.cmb_c_encoder, self.chk_c_mono, self.cmb_c_abitrate]:
            if isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._on_settings_changed)
            else:
                widget.toggled.connect(self._on_settings_changed)
        self.spn_c_target_mb.valueChanged.connect(self._on_settings_changed)
        self.txt_c_suffix.textChanged.connect(self._on_settings_changed)


    # ------------------- Encoder Change Update -------------------
    def _on_encoder_changed(self):
        enc_key = self.cmb_b_encoder.currentData()
        config = ENCODER_CONFIGS.get(enc_key)
        if config is None:
            # 互換性のためフォールバック（これまでの挙動を維持）
            enc_key = "libx264"
            config = ENCODER_CONFIGS[enc_key]

        # 速度プリセットの更新。
        self.cmb_b_preset.blockSignals(True)
        self.cmb_b_preset.clear()
        default_idx = 0
        for idx, (text, value) in enumerate(config["presets"]):
            self.cmb_b_preset.addItem(text, value)
            if value == config["default_preset"]:
                default_idx = idx
        self.cmb_b_preset.setCurrentIndex(default_idx)
        self.cmb_b_preset.blockSignals(False)

        # B. 品質ラベルとSpinBoxの更新
        #self.lbl_crf_right.setText(config["quality_label"])
        min_q, max_q = config["quality_range"]
        print("min_q",min_q)
        print("max_q",max_q)
        self.spn_b_crf.blockSignals(True)
        self.slider_b_crf.blockSignals(True)
        self.spn_b_crf.setRange(min_q, max_q)
        self.spn_b_crf.setValue(config["default_quality"])
        self.slider_b_crf.setRange(min_q, max_q)
        self.slider_b_crf.setValue(config["default_quality"])
        self.spn_b_crf.blockSignals(False)
        self.slider_b_crf.blockSignals(False)

    # ------------------- File List Update -------------------
    def update_input_files(self, file_items: List[Dict[str, Any]]):
        """Populates preview file selector dropdown with checked input files."""
        self.cmb_preview_file.blockSignals(True)
        self.cmb_preview_file.clear()

        for item in file_items:
            if item.get("checked", True):
                self.cmb_preview_file.addItem(item["file_name"], item)

        self.cmb_preview_file.blockSignals(False)
        self.update_bitrate_estimate()

    def get_preview_file_info(self) -> Optional[Dict[str, Any]]:
        """Return currently selected preview file info dict, or None."""
        return self.cmb_preview_file.currentData()

    def _on_preview_file_changed(self):
        self.update_bitrate_estimate()
        # Notify main_window that the command preview file has changed
        self.command_preview_requested.emit(self.get_preview_file_info())

    # ------------------- Bitrate Estimate -------------------
    def update_bitrate_estimate(self):
        """Recalculates 2-pass bitrate for Tab C if a preview file is selected."""
        if self.tab_widget.currentIndex() != 2:
            return

        current_data = self.cmb_preview_file.currentData()
        if not current_data or current_data.get("duration", 0) <= 0:
            self.lbl_c_calc_info.setText("推定映像ビットレート: 対象ファイルを指定してください")
            return

        target_mb = self.spn_c_target_mb.value()
        abitrate_kbps = BitrateCalculator.parse_bitrate_str_to_kbps(self.cmb_c_abitrate.currentText())

        try:
            calc_prev = BitrateCalculator.calculate_video_bitrate(
                duration_sec=current_data["duration"],
                target_size_mb=target_mb,
                audio_bitrate_kbps=abitrate_kbps
            )
            prev_v_kbps = calc_prev["video_bitrate_kbps"]
            prev_v_mb = calc_prev["video_size_mb"]
            prev_total = calc_prev["total_bitrate_kbps"]
            
            base_text = f"推定映像(プレビュー中ファイル): {prev_v_kbps} kbps ({prev_v_mb:.2f} MB) / 全体: {prev_total} kbps"
        except ValueError as e:
            self.lbl_c_calc_info.setText(f"エラー: {e}")
            self.lbl_c_calc_info.setStyleSheet("color: #dc3545; font-weight: bold;")
            return
            
        count = self.cmb_preview_file.count()
        if count <= 1:
            self.lbl_c_calc_info.setText(base_text)
            self.lbl_c_calc_info.setStyleSheet("color: #198754; font-weight: bold;")
            return
            
        min_kbps = float('inf')
        max_kbps = 0
        has_error = False
        
        for i in range(count):
            file_info = self.cmb_preview_file.itemData(i)
            dur = file_info.get("duration", 0)
            if dur <= 0:
                has_error = True
                break
            try:
                calc = BitrateCalculator.calculate_video_bitrate(
                    duration_sec=dur,
                    target_size_mb=target_mb,
                    audio_bitrate_kbps=abitrate_kbps
                )
                vk = calc["video_bitrate_kbps"]
                if vk < min_kbps: min_kbps = vk
                if vk > max_kbps: max_kbps = vk
            except ValueError:
                has_error = True
                break
                
        if has_error:
            self.lbl_c_calc_info.setText(base_text + "\n(全体推定: エラーとなるファイルがあります)")
            self.lbl_c_calc_info.setStyleSheet("color: #d63384; font-weight: bold;") # highlight error softly
        else:
            self.lbl_c_calc_info.setText(base_text + f"\n(対象全ファイル推定映像: {min_kbps} 〜 {max_kbps} kbps)")
            self.lbl_c_calc_info.setStyleSheet("color: #198754; font-weight: bold;")

    def _on_settings_changed(self):
        self.update_bitrate_estimate()
        self.settings_changed.emit()
        # Update command preview using the preview combo selection
        self.command_preview_requested.emit(self.get_preview_file_info())

    # ------------------- Get Settings -------------------
    def get_current_settings(self) -> Dict[str, Any]:
        return {
            "active_tab": self.tab_widget.currentIndex(),
            "remove_video": {
                "format": self.cmb_audio_format.currentText(),
                "output_suffix": self.txt_a_suffix.text().strip() or "_novideo"
            },
            "quality_compress": {
                "resolution": self.cmb_b_res.currentText(),
                "fps": self.cmb_b_fps.currentText(),
                "encoder": self.cmb_b_encoder.currentData() or "libx264",
                "crf": self.spn_b_crf.value(),
                "preset_speed": self.cmb_b_preset.currentData(),
                "audio_mono": self.chk_b_mono.isChecked(),
                "audio_bitrate": self.cmb_b_abitrate.currentText(),
                "output_suffix": self.txt_b_suffix.text().strip() or "_compressed"
            },
            "size_compress": {
                "resolution": self.cmb_c_res.currentText(),
                "fps": self.cmb_c_fps.currentText(),
                "encoder": self.cmb_c_encoder.currentData() or "libx264",
                "target_size_mb": self.spn_c_target_mb.value(),
                "audio_mono": self.chk_c_mono.isChecked(),
                "audio_bitrate": self.cmb_c_abitrate.currentText(),
                "output_suffix": self.txt_c_suffix.text().strip() or "_targetsize"
            },
            "custom_options": self.txt_custom_options.text().strip()
        }

    # ------------------- Load From Preset -------------------
    def load_from_preset(self, settings: Dict[str, Any]):
        self.tab_widget.setCurrentIndex(settings.get("active_tab", 0))

        # Tab A
        ra = settings.get("remove_video", {})
        idx_fmt = self.cmb_audio_format.findText(ra.get("format", "mp3"))
        if idx_fmt >= 0:
            self.cmb_audio_format.setCurrentIndex(idx_fmt)
        self.txt_a_suffix.setText(ra.get("output_suffix", "_novideo"))

        # Tab B
        qb = settings.get("quality_compress", {})
        self.cmb_b_res.setCurrentText(qb.get("resolution", "元のまま"))
        self.cmb_b_fps.setCurrentText(qb.get("fps", "元のまま"))
        
        enc_b = qb.get("encoder", "libx264")
        idx_b = self.cmb_b_encoder.findData(enc_b)
        if idx_b >= 0:
            self.cmb_b_encoder.setCurrentIndex(idx_b)
            
        self.spn_b_crf.setValue(qb.get("crf", 23))
        self.cmb_b_preset.setCurrentText(qb.get("preset_speed", "medium"))
        self.chk_b_mono.setChecked(qb.get("audio_mono", False))
        self.cmb_b_abitrate.setCurrentText(qb.get("audio_bitrate", "128k"))
        self.txt_b_suffix.setText(qb.get("output_suffix", "_compressed"))

        # Tab C
        sc = settings.get("size_compress", {})
        self.cmb_c_res.setCurrentText(sc.get("resolution", "元のまま"))
        self.cmb_c_fps.setCurrentText(sc.get("fps", "元のまま"))
        
        enc_c = sc.get("encoder", "libx264")
        idx_c = self.cmb_c_encoder.findData(enc_c)
        if idx_c >= 0:
            self.cmb_c_encoder.setCurrentIndex(idx_c)
            
        self.spn_c_target_mb.setValue(sc.get("target_size_mb", 50.0))
        self.chk_c_mono.setChecked(sc.get("audio_mono", False))
        self.cmb_c_abitrate.setCurrentText(sc.get("audio_bitrate", "128k"))
        self.txt_c_suffix.setText(sc.get("output_suffix", "_targetsize"))

        self.txt_custom_options.setText(settings.get("custom_options", ""))
        self.update_bitrate_estimate()

    # ------------------- Preset Save/Load -------------------
    def _on_save_preset(self):
        settings = self.get_current_settings()
        file_path, _ = QFileDialog.getSaveFileName(self, "プリセットを保存", "", "JSON Files (*.json)")
        if file_path:
            pm = PresetManager(file_path)
            if pm.save_settings(settings):
                QMessageBox.information(self, "保存完了", f"プリセットを保存しました:\n{file_path}")
            else:
                QMessageBox.warning(self, "エラー", "プリセットの保存に失敗しました。")

    def _on_load_preset(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "プリセットを読み込み", "", "JSON Files (*.json)")
        if file_path:
            pm = PresetManager(file_path)
            settings = pm.load_settings()
            self.load_from_preset(settings)
            QMessageBox.information(self, "読み込み完了", f"プリセットを読み込みました:\n{file_path}")

    # ------------------- Preview -------------------
    def _on_generate_preview(self):
        """Generates a 10-second preview according to current tab settings."""
        file_info = self.cmb_preview_file.currentData()
        if not file_info:
            QMessageBox.warning(self, "注意", "プレビュー対象のファイルが選択されていません。")
            return

        # If previous worker is still running, wait for it to stop
        if self.preview_worker and self.preview_worker.isRunning():
            self.preview_worker.cancel()
            self.preview_worker.wait(3000)

        active_tab = self.tab_widget.currentIndex()
        in_path = file_info["file_path"]
        dur = file_info.get("duration", 10.0)

        # Output preview file in temp directory
        passlog_prefix = os.path.join(tempfile.gettempdir(), "myffmpeg_preview_passlog")
        try:
            cmd_list, preview_out = build_ffmpeg_commands(file_info=file_info, settings=self.get_current_settings(), passlog_prefix=passlog_prefix,overwrite=True, IsPreview=True)
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"コマンドの生成に失敗しました:\n{e}")
            return

        # Stop player and clear source BEFORE deleting the file
        self.media_player.stop()
        self.media_player.setSource(QUrl())  # Clear source to release file lock

        if os.path.exists(preview_out):
            try:
                os.remove(preview_out)
            except OSError:
                pass
            
        self._preview_output_path = preview_out

        # Start FFmpeg worker for preview
        self.btn_generate_preview.setEnabled(False)
        self.btn_generate_preview.setText("🎬 プレビュー作成中...")

        self.preview_worker = FFmpegWorker(
            command_args_list=cmd_list,
            output_file=preview_out,
            total_duration_sec=10.0,
            passlog_prefix=passlog_prefix,
            parent=self
        )
        self.preview_worker.job_finished.connect(self._on_preview_worker_finished)
        self.preview_worker.start()

    def _on_preview_worker_finished(self, success: bool, output_or_err: str):
        self.btn_generate_preview.setEnabled(True)
        self.btn_generate_preview.setText("🎬 10秒プレビュー作成・再生")

        if success and os.path.exists(output_or_err):
            # Must clear source first to release any previous file handle,
            # then set the new path, then play
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self.media_player.setSource(QUrl.fromLocalFile(output_or_err))
            self.media_player.play()
        else:
            QMessageBox.warning(self, "プレビュー生成エラー", f"プレビューの作成に失敗しました:\n{output_or_err}")

    # ------------------- Command Preview Display -------------------
    def set_command_preview(self, text: str):
        self.txt_command_preview.setPlainText(text)

# 12種類の動画エンコーダー完全検証済み設定辞書
ENCODER_CONFIGS = {
    # -----------------------------------------------------------------
    # CPU エンコーダー
    # -----------------------------------------------------------------
    "libx264": {
        "name": "H.264 (CPU / libx264)",
        "presets": [
            ("ultrafast (最速)", "ultrafast"),
            ("superfast (超高速)", "superfast"),
            ("veryfast (高速)", "veryfast"),
            ("faster", "faster"),
            ("fast", "fast"),
            ("medium (標準・デフォルト)", "medium"),
            ("slow (高画質)", "slow"),
            ("slower (超高画質)", "slower"),
            ("veryslow (最高画質)", "veryslow"),
            ("placebo (実験用・非推奨)", "placebo"),
        ],
        "default_preset": "medium",
        "quality_label": "CRF (小＝高画質):",
        "quality_range": (0, 51),
        "default_quality": 23,
    },
    "libx265": {
        "name": "H.265/HEVC (CPU / libx265)",
        "presets": [
            ("ultrafast (最速)", "ultrafast"),
            ("superfast (超高速)", "superfast"),
            ("veryfast (高速)", "veryfast"),
            ("faster", "faster"),
            ("fast", "fast"),
            ("medium (標準・デフォルト)", "medium"),
            ("slow (高画質)", "slow"),
            ("slower (超高画質)", "slower"),
            ("veryslow (最高画質)", "veryslow"),
            ("placebo (実験用・非推奨)", "placebo"),
        ],
        "default_preset": "medium",
        "quality_label": "CRF (小＝高画質):",
        "quality_range": (0, 51),
        "default_quality": 28,
    },
    "libsvtav1": {
        "name": "AV1 (CPU / SVT-AV1)",
        "presets": [
            ("0 (最高画質・超低速)", "0"),
            ("1 (極高画質)", "1"),
            ("2 (極高画質)", "2"),
            ("3 (高画質・保存向け)", "3"),
            ("4 (高画質・保存向け)", "4"),
            ("5 (バランス高画質)", "5"),
            ("6 (バランス高画質)", "6"),
            ("7 (標準・高速)", "7"),
            ("8 (標準・おすすめ)", "8"),
            ("9 (高速・ストリーミング)", "9"),
            ("10 (高速)", "10"),
            ("11 (超高速)", "11"),
            ("12 (爆速)", "12"),
            ("13 (最速・デバッグ用)", "13"),
        ],
        "default_preset": "8",
        "quality_label": "CRF (0-63):",
        "quality_range": (0, 63),
        "default_quality": 33,
    },
    # -----------------------------------------------------------------
    # NVIDIA (NVENC)
    # -----------------------------------------------------------------
    "h264_nvenc": {
        "name": "H.264 (NVIDIA / NVENC)",
        "presets": [
            ("p1 (最速・最低画質)", "p1"),
            ("p2 (より高速)", "p2"),
            ("p3 (高速)", "p3"),
            ("p4 (標準・デフォルト)", "p4"),
            ("p5 (高画質)", "p5"),
            ("p6 (より高画質)", "p6"),
            ("p7 (最高画質・低速)", "p7"),
        ],
        "default_preset": "p4",
        "quality_label": "CQ (小＝高画質):",
        "quality_range": (0, 51),
        "default_quality": 23,
    },
    "hevc_nvenc": {
        "name": "H.265/HEVC (NVIDIA / NVENC)",
        "presets": [
            ("p1 (最速・最低画質)", "p1"),
            ("p2 (より高速)", "p2"),
            ("p3 (高速)", "p3"),
            ("p4 (標準・デフォルト)", "p4"),
            ("p5 (高画質)", "p5"),
            ("p6 (より高画質)", "p6"),
            ("p7 (最高画質・低速)", "p7"),
        ],
        "default_preset": "p4",
        "quality_label": "CQ (小＝高画質):",
        "quality_range": (0, 51),
        "default_quality": 26,
    },
    "av1_nvenc": {
        "name": "AV1 (NVIDIA / NVENC)",
        "presets": [
            ("p1 (最速・最低画質)", "p1"),
            ("p2 (より高速)", "p2"),
            ("p3 (高速)", "p3"),
            ("p4 (標準・デフォルト)", "p4"),
            ("p5 (高画質)", "p5"),
            ("p6 (より高画質)", "p6"),
            ("p7 (最高画質・低速)", "p7"),
        ],
        "default_preset": "p4",
        "quality_label": "CQ (小＝高画質):",
        "quality_range": (0, 51),
        "default_quality": 30,
    },
    # -----------------------------------------------------------------
    # Intel (QSV)
    # -----------------------------------------------------------------
    "h264_qsv": {
        "name": "H.264 (Intel / QSV)",
        "presets": [
            ("veryfast (最速)", "veryfast"),
            ("faster (より高速)", "faster"),
            ("fast (高速)", "fast"),
            ("medium (標準)", "medium"),
            ("slow (高画質)", "slow"),
            ("slower (より高画質)", "slower"),
            ("veryslow (最高画質)", "veryslow"),
        ],
        "default_preset": "medium",
        "quality_label": "Global Quality (1-51):",
        "quality_range": (1, 51),  # QSVは1〜51
        "default_quality": 23,
    },
    "hevc_qsv": {
        "name": "H.265/HEVC (Intel / QSV)",
        "presets": [
            ("veryfast (最速)", "veryfast"),
            ("faster (より高速)", "faster"),
            ("fast (高速)", "fast"),
            ("medium (標準)", "medium"),
            ("slow (高画質)", "slow"),
            ("slower (より高画質)", "slower"),
            ("veryslow (最高画質)", "veryslow"),
        ],
        "default_preset": "medium",
        "quality_label": "Global Quality (1-51):",
        "quality_range": (1, 51),
        "default_quality": 26,
    },
    "av1_qsv": {
        "name": "AV1 (Intel / QSV)",
        "presets": [
            ("veryfast (最速)", "veryfast"),
            ("faster (より高速)", "faster"),
            ("fast (高速)", "fast"),
            ("medium (標準)", "medium"),
            ("slow (高画質)", "slow"),
            ("slower (より高画質)", "slower"),
            ("veryslow (最高画質)", "veryslow"),
        ],
        "default_preset": "medium",
        "quality_label": "Global Quality (1-51):",
        "quality_range": (1, 51),
        "default_quality": 30,
    },
    # -----------------------------------------------------------------
    # AMD (AMF)
    # -----------------------------------------------------------------
    "h264_amf": {
        "name": "H.264 (AMD / AMF)",
        "presets": [
            ("speed (最速)", "speed"),
            ("balanced (標準)", "balanced"),
            ("quality (高画質)", "quality"),
        ],
        "default_preset": "balanced",
        "quality_label": "QP (0-51):",
        "quality_range": (0, 51),
        "default_quality": 23,
    },
    "hevc_amf": {
        "name": "H.265/HEVC (AMD / AMF)",
        "presets": [
            ("speed (最速)", "speed"),
            ("balanced (標準)", "balanced"),
            ("quality (高画質)", "quality"),
        ],
        "default_preset": "balanced",
        "quality_label": "QP (0-51):",
        "quality_range": (0, 51),
        "default_quality": 26,
    },
    "av1_amf": {
        "name": "AV1 (AMD / AMF)",
        "presets": [
            ("speed (最速)", "speed"),
            ("balanced (標準)", "balanced"),
            ("quality (高画質)", "quality"),
        ],
        "default_preset": "balanced",
        "quality_label": "QP (0-255):",
        "quality_range": (0, 255),  # AMF AV1のみ 0〜255
        "default_quality": 90,
    },
}