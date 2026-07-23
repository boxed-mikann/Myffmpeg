import os
from typing import List, Dict, Any
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QLabel, QGroupBox,
    QAbstractItemView
)
from src.core.ffprobe_parser import FFprobeParser

SUPPORTED_EXTENSIONS = { ".mp4", ".mov"
#     ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
#     ".m4v", ".ts", ".m2ts", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a"
}

class FFprobeThread(QThread):
    file_parsed = Signal(dict)
    all_finished = Signal()

    def __init__(self, file_paths: List[str], parser: FFprobeParser):
        super().__init__()
        self.file_paths = file_paths
        self.parser = parser

    def run(self):
        for path in self.file_paths:
            try:
                info = self.parser.parse_file(path)
                self.file_parsed.emit(info)
            except Exception as e:
                # Return basic info fallback if probe failed
                size = os.path.getsize(path) if os.path.exists(path) else 0
                self.file_parsed.emit({
                    "file_path": os.path.abspath(path),
                    "file_name": os.path.basename(path),
                    "file_size": size,
                    "duration": 0.0,
                    "width": 0,
                    "height": 0,
                    "resolution_str": "エラー",
                    "fps": 0.0,
                    "video_codec": "不明",
                    "audio_codec": "不明",
                    "error": str(e)
                })
        self.all_finished.emit()


class InputPane(QGroupBox):
    files_changed = Signal()  # Emitted when file list or selection changes

    def __init__(self, parent=None):
        super().__init__("1. 入力ファイル (Input)", parent)
        self.setAcceptDrops(True)
        self.parser = FFprobeParser()
        self.file_items: List[Dict[str, Any]] = []

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Header summary label
        self.summary_label = QLabel("全 0 件 | 総サイズ: 0.00 MB")
        self.summary_label.setStyleSheet("font-weight: bold; color: #0d6efd;")
        layout.addWidget(self.summary_label)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("＋ ファイル追加")
        self.btn_add_dir = QPushButton("📁 フォルダ追加")
        self.btn_remove_sel = QPushButton("－ 選択削除")
        self.btn_clear_all = QPushButton("🗑️ 全削除")

        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_add_dir)
        btn_layout.addWidget(self.btn_remove_sel)
        btn_layout.addWidget(self.btn_clear_all)
        layout.addLayout(btn_layout)

        # File List Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "対象", "ファイル名", "解像度", "長さ", "サイズ", "映像", "音声", "パス"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive) #列幅の自由な変更を可能にする
        # Set default reasonable widths for commonly truncated columns
        self.table.setColumnWidth(1, 150) # ファイル名
        self.table.setColumnWidth(7, 200) # パス
        layout.addWidget(self.table)

        # Signals
        self.btn_add_files.clicked.connect(self._on_add_files)
        self.btn_add_dir.clicked.connect(self._on_add_dir)
        self.btn_remove_sel.clicked.connect(self._on_remove_selected)
        self.btn_clear_all.clicked.connect(self.clear_all)
        self.table.itemChanged.connect(self._on_item_changed)

    # Drag and drop events
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if os.path.isfile(local_path):
                ext = os.path.splitext(local_path)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    paths.append(local_path)
            elif os.path.isdir(local_path):
                paths.extend(self._scan_directory(local_path))
        if paths:
            self.add_files(paths)

    def _scan_directory(self, dir_path: str) -> List[str]:
        found = []
        for root, _, files in os.walk(dir_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SUPPORTED_EXTENSIONS:
                    found.append(os.path.join(root, f))
        return found

    def _on_add_files(self):
        filter_str = "動画・音声ファイル (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.ts *.m2ts *.mp3 *.wav *.aac *.flac *.ogg *.m4a);;すべてのファイル (*.*)"
        files, _ = QFileDialog.getOpenFileNames(self, "ファイルを選択", "", filter_str)
        if files:
            self.add_files(files)

    def _on_add_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if dir_path:
            files = self._scan_directory(dir_path)
            if files:
                self.add_files(files)

    def add_files(self, paths: List[str]):
        # Filter existing paths
        existing_paths = {item["file_path"] for item in self.file_items}
        new_paths = [os.path.abspath(p) for p in paths if os.path.abspath(p) not in existing_paths]
        if not new_paths:
            return

        # Disable table item signal during batch updates
        self.table.blockSignals(True)
        
        self.probe_thread = FFprobeThread(new_paths, self.parser)
        self.probe_thread.file_parsed.connect(self._on_file_parsed) # スレッドで処理されたらこれを行う
        self.probe_thread.all_finished.connect(self._on_probe_finished)
        self.probe_thread.start()

    def _on_file_parsed(self, info: Dict[str, Any]):
        info["checked"] = True
        self.file_items.append(info)

        row = self.table.rowCount()
        self.table.insertRow(row)

        # Checkbox column
        chk_item = QTableWidgetItem()
        chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        chk_item.setCheckState(Qt.Checked)
        self.table.setItem(row, 0, chk_item)

        # Metadata columns
        self.table.setItem(row, 1, QTableWidgetItem(info["file_name"]))
        self.table.setItem(row, 2, QTableWidgetItem(info["resolution_str"]))
        
        dur_str = f"{info['duration']:.1f}s" if info['duration'] > 0 else "-"
        self.table.setItem(row, 3, QTableWidgetItem(dur_str))

        size_mb = info["file_size"] / (1024 * 1024)
        self.table.setItem(row, 4, QTableWidgetItem(f"{size_mb:.2f} MB"))

        self.table.setItem(row, 5, QTableWidgetItem(info.get("video_codec", "-")))
        self.table.setItem(row, 6, QTableWidgetItem(info.get("audio_codec", "-")))
        self.table.setItem(row, 7, QTableWidgetItem(info["file_path"]))

    def _on_probe_finished(self):
        self.table.blockSignals(False)
        self._update_summary()
        self.files_changed.emit()

    def _on_remove_selected(self):
        selected_rows = sorted({item.row() for item in self.table.selectedItems()}, reverse=True)
        if not selected_rows:
            return

        self.table.blockSignals(True)
        for row in selected_rows:
            self.table.removeRow(row)
            if row < len(self.file_items):
                del self.file_items[row]
        self.table.blockSignals(False)

        self._update_summary()
        self.files_changed.emit()

    def clear_all(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.file_items.clear()
        self.table.blockSignals(False)
        self._update_summary()
        self.files_changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            row = item.row()
            if 0 <= row < len(self.file_items):
                self.file_items[row]["checked"] = (item.checkState() == Qt.Checked)
            self._update_summary()
            self.files_changed.emit()

    def _update_summary(self):
        total_count = len(self.file_items)
        checked_count = sum(1 for item in self.file_items if item.get("checked", True))
        total_bytes = sum(item["file_size"] for item in self.file_items if item.get("checked", True))
        total_mb = total_bytes / (1024 * 1024)

        self.summary_label.setText(
            f"全 {total_count} 件 (対象 {checked_count} 件) | 対象総サイズ: {total_mb:.2f} MB"
        )

    def get_selected_files(self) -> List[Dict[str, Any]]:
        return [item for item in self.file_items if item.get("checked", True)]

    def get_all_files(self) -> List[Dict[str, Any]]:
        return list(self.file_items)
