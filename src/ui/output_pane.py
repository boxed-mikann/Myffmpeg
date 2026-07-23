from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QProgressBar, QLabel, QGroupBox, QPlainTextEdit
)

class OutputPane(QGroupBox):
    start_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("3. 実行 & 出力ログ (Output & Controls)", parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Log Text Box header
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("処理ログ:"))
        self.btn_clear_log = QPushButton("ログクリア")
        log_header.addStretch()
        log_header.addWidget(self.btn_clear_log)
        layout.addLayout(log_header)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("font-family: Consolas, monospace; background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.txt_log)

        # FFmpeg progress stats label (fps=, speed=, out_time= etc. — not scrolled)
        self.lbl_ffmpeg_stats = QLabel("")
        self.lbl_ffmpeg_stats.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px; color: #adb5bd; "
            "background-color: #212529; padding: 2px 4px;"
        )
        self.lbl_ffmpeg_stats.setWordWrap(True)
        layout.addWidget(self.lbl_ffmpeg_stats)

        # Status Summary Label
        self.lbl_status = QLabel("ステータス: 待機中")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ ジョブ開始 (エンコード実行)")
        self.btn_start.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #198754; color: white; padding: 8px;")

        self.btn_cancel = QPushButton("⏹️ キャンセル")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #dc3545; color: white; padding: 8px;")

        btn_layout.addWidget(self.btn_start, 2)
        btn_layout.addWidget(self.btn_cancel, 1)
        layout.addLayout(btn_layout)

        # Signals
        self.btn_start.clicked.connect(self.start_requested.emit)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        self.btn_clear_log.clicked.connect(self._clear_log)

    def _clear_log(self):
        self.txt_log.clear()
        self.lbl_ffmpeg_stats.setText("")

    def append_log(self, text: str):
        cursor = self.txt_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.txt_log.setTextCursor(cursor)
        self.txt_log.insertPlainText(text)
        cursor = self.txt_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.txt_log.setTextCursor(cursor)

    def update_ffmpeg_stats(self, stats: dict):
        """Update the non-scrolling progress stats label."""
        if not stats:
            return
        parts = []
        for key in ["fps", "bitrate", "total_size", "out_time", "speed"]:
            if key in stats:
                parts.append(f"{key}={stats[key]}")
        self.lbl_ffmpeg_stats.setText("  ".join(parts))

    def set_progress(self, val: int):
        self.progress_bar.setValue(val)

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def set_processing_state(self, is_processing: bool):
        self.btn_start.setEnabled(not is_processing)
        self.btn_cancel.setEnabled(is_processing)
        if not is_processing:
            self.lbl_ffmpeg_stats.setText("")
