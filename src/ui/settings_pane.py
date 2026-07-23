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

def build_quality_args(encoder: str, quality_value: int) -> List[str]:
    """
    エンコーダー（H.264 / HEVC / AV1共通）に応じた固定画質パラメータを生成する
    """
    if "lib" in encoder:
        return ["-crf", str(quality_value)]
    elif "nvenc" in encoder:
        return ["-rc", "vbr", "-cq", str(quality_value)]
    elif "qsv" in encoder:
        return ["-global_quality", str(quality_value)]
    elif "amf" in encoder:
        q_str = str(quality_value)
        return ["-rc", "cqp", "-qp_i", q_str, "-qp_p", q_str]
    return ["-crf", str(quality_value)]

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
        layout.addRow("音声出力フォーマット:", self.cmb_audio_format)

        self.txt_a_suffix = QLineEdit("_novideo")
        layout.addRow("出力サフィックス:", self.txt_a_suffix)

        # Connect signals
        self.cmb_audio_format.currentIndexChanged.connect(self._on_settings_changed)
        self.txt_a_suffix.textChanged.connect(self._on_settings_changed)

    # ------------------- Tab B Init -------------------
    def _init_tab_b(self):
        layout = QFormLayout(self.tab_b)

        self.cmb_b_res = QComboBox()
        self.cmb_b_res.addItems(["Original", "1920x1080", "1280x720", "854x480", "640x360"])
        layout.addRow("解像度:", self.cmb_b_res)

        self.cmb_b_fps = QComboBox()
        self.cmb_b_fps.addItems(["Original", "60", "50", "30", "24"])
        layout.addRow("フレームレート (FPS):", self.cmb_b_fps)

        self.cmb_b_encoder = QComboBox()
        for enc in self.available_encoders:
            self.cmb_b_encoder.addItem(ENCODER_DISPLAY_NAMES.get(enc, enc), enc)
        layout.addRow("エンコーダ:", self.cmb_b_encoder)

        # CRF slider and spinbox
        crf_layout = QHBoxLayout()
        self.slider_b_crf = QSlider(Qt.Horizontal)
        self.slider_b_crf.setRange(0, 51)
        self.slider_b_crf.setValue(23)
        self.spn_b_crf = QSpinBox()
        self.spn_b_crf.setRange(0, 51)
        self.spn_b_crf.setValue(23)

        self.slider_b_crf.valueChanged.connect(self.spn_b_crf.setValue)
        self.spn_b_crf.valueChanged.connect(self.slider_b_crf.setValue)

        crf_layout.addWidget(self.slider_b_crf)
        crf_layout.addWidget(self.spn_b_crf)
        layout.addRow("品質 (CRF / QP):", crf_layout)

        self.cmb_b_preset = QComboBox()
        self.cmb_b_preset.addItems([
            "ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"
        ])
        self.cmb_b_preset.setCurrentText("medium")
        layout.addRow("エンコード速度:", self.cmb_b_preset)

        self.chk_b_mono = QCheckBox("モノラル化 (-ac 1)")
        layout.addRow("音声チャンネル:", self.chk_b_mono)

        self.cmb_b_abitrate = QComboBox()
        self.cmb_b_abitrate.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        self.cmb_b_abitrate.setCurrentText("128k")
        layout.addRow("音声ビットレート:", self.cmb_b_abitrate)

        self.txt_b_suffix = QLineEdit("_compressed")
        layout.addRow("出力サフィックス:", self.txt_b_suffix)

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

    # ------------------- Tab C Init -------------------
    def _init_tab_c(self):
        layout = QFormLayout(self.tab_c)

        self.cmb_c_res = QComboBox()
        self.cmb_c_res.addItems(["Original", "1920x1080", "1280x720", "854x480", "640x360"])
        layout.addRow("解像度:", self.cmb_c_res)

        self.cmb_c_fps = QComboBox()
        self.cmb_c_fps.addItems(["Original", "60", "50", "30", "24"])
        layout.addRow("フレームレート (FPS):", self.cmb_c_fps)

        self.cmb_c_encoder = QComboBox()
        for enc in self.available_encoders:
            self.cmb_c_encoder.addItem(ENCODER_DISPLAY_NAMES.get(enc, enc), enc)
        layout.addRow("エンコーダ:", self.cmb_c_encoder)

        self.spn_c_target_mb = QDoubleSpinBox()
        self.spn_c_target_mb.setRange(1.0, 10000.0)
        self.spn_c_target_mb.setValue(50.0)
        self.spn_c_target_mb.setSuffix(" MB")
        layout.addRow("目標ファイルサイズ:", self.spn_c_target_mb)

        self.chk_c_mono = QCheckBox("モノラル化 (-ac 1)")
        layout.addRow("音声チャンネル:", self.chk_c_mono)

        self.cmb_c_abitrate = QComboBox()
        self.cmb_c_abitrate.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        self.cmb_c_abitrate.setCurrentText("128k")
        layout.addRow("音声ビットレート:", self.cmb_c_abitrate)

        self.txt_c_suffix = QLineEdit("_targetsize")
        layout.addRow("出力サフィックス:", self.txt_c_suffix)

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
                "preset_speed": self.cmb_b_preset.currentText(),
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
        self.cmb_b_res.setCurrentText(qb.get("resolution", "Original"))
        self.cmb_b_fps.setCurrentText(qb.get("fps", "Original"))
        
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
        self.cmb_c_res.setCurrentText(sc.get("resolution", "Original"))
        self.cmb_c_fps.setCurrentText(sc.get("fps", "Original"))
        
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
        ext = ".mp3" if active_tab == 0 else ".mp4"
        preview_out = os.path.join(tempfile.gettempdir(), f"myffmpeg_preview_10s{ext}")

        # Stop player and clear source BEFORE deleting the file
        self.media_player.stop()
        self.media_player.setSource(QUrl())  # Clear source to release file lock

        if os.path.exists(preview_out):
            try:
                os.remove(preview_out)
            except OSError:
                pass

        cmd = ["-y", "-ss", "0", "-t", "10", "-i", in_path]
        is_two_pass = False
        pass1_args, pass2_args, passlog_prefix = None, None, None

        settings = self.get_current_settings()

        if active_tab == 0:
            # Tab A: Video removal
            fmt = settings["remove_video"]["format"]
            cmd.extend(["-vn"])
            if fmt == "mp3":
                cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
            else:
                cmd.extend(["-c:a", "copy"])
            cmd.append(preview_out)

        elif active_tab == 1:
            # Tab B: Quality Compression
            qb = settings["quality_compress"]
            cmd.extend(self._build_video_args(qb))
            if settings["custom_options"]:
                cmd.extend(settings["custom_options"].split())
            cmd.append(preview_out)

        elif active_tab == 2:
            # Tab C: Target Size Compression
            sc = settings["size_compress"]
            target_mb = sc["target_size_mb"]
            # Spec: preview target size = target_size * 10 / duration
            if dur > 0:
                prev_target_mb = (target_mb * 10.0) / dur
            else:
                prev_target_mb = target_mb

            abitrate_kbps = BitrateCalculator.parse_bitrate_str_to_kbps(sc["audio_bitrate"])
            try:
                calc = BitrateCalculator.calculate_video_bitrate(
                    duration_sec=10.0,
                    target_size_mb=prev_target_mb,
                    audio_bitrate_kbps=abitrate_kbps
                )
                v_bitrate_kbps = calc["video_bitrate_kbps"]
            except ValueError as e:
                QMessageBox.warning(self, "エラー", f"プレビュー計算エラー: {e}")
                return

            is_two_pass = True
            passlog_prefix = os.path.join(tempfile.gettempdir(), "myffmpeg_preview_passlog")
            
            encoder_raw = sc["encoder"]

            pass1_args = ["-y", "-ss", "0", "-t", "10", "-i", in_path]
            pass1_args.extend(self._build_video_filter_args(sc))
            pass1_args.extend([
                "-c:v", encoder_raw,
                "-b:v", f"{v_bitrate_kbps}k",
                "-pass", "1",
                "-passlogfile", passlog_prefix,
                "-an",
                "-f", "null", "NUL" if os.name == "nt" else "/dev/null"
            ])

            pass2_args = ["-y", "-ss", "0", "-t", "10", "-i", in_path]
            pass2_args.extend(self._build_video_filter_args(sc))
            pass2_args.extend([
                "-c:v", encoder_raw,
                "-b:v", f"{v_bitrate_kbps}k",
                "-pass", "2",
                "-passlogfile", passlog_prefix
            ])
            pass2_args.extend(self._build_audio_args(sc))
            if settings["custom_options"]:
                pass2_args.extend(settings["custom_options"].split())
            pass2_args.append(preview_out)

        self._preview_output_path = preview_out

        # Start FFmpeg worker for preview
        self.btn_generate_preview.setEnabled(False)
        self.btn_generate_preview.setText("🎬 プレビュー作成中...")

        self.preview_worker = FFmpegWorker(
            command_args=cmd,
            output_file=preview_out,
            total_duration_sec=10.0,
            is_two_pass=is_two_pass,
            pass1_args=pass1_args,
            pass2_args=pass2_args,
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

    # ------------------- Command Builder Helpers -------------------
    def _build_video_filter_args(self, settings: Dict[str, Any]) -> List[str]:
        args = []
        res = settings.get("resolution", "Original")
        fps = settings.get("fps", "Original")

        filters = []
        if res != "Original" and "x" in res:
            w, h = res.split("x")
            filters.append(f"scale={w}:{h}")
        if fps != "Original" and fps.isdigit():
            filters.append(f"fps={fps}")

        if filters:
            args.extend(["-vf", ",".join(filters)])
        return args

    def _build_audio_args(self, settings: Dict[str, Any]) -> List[str]:
        args = ["-c:a", "aac"]
        if settings.get("audio_mono", False):
            args.extend(["-ac", "1"])
        abit = settings.get("audio_bitrate", "128k")
        args.extend(["-b:a", abit])
        return args

    def _build_video_args(self, qb: Dict[str, Any]) -> List[str]:
        args = self._build_video_filter_args(qb)
        encoder = qb.get("encoder", "libx264")
        args.extend(["-c:v", encoder])

        crf = qb.get("crf", 23)
        args.extend(build_quality_args(encoder, crf))

        preset = qb.get("preset_speed", "medium")
        args.extend(["-preset", preset])

        args.extend(self._build_audio_args(qb))
        return args

    # ------------------- Command Preview Display -------------------
    def set_command_preview(self, text: str):
        self.txt_command_preview.setPlainText(text)
