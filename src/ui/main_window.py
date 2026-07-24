import os
import sys
import tempfile
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon  # QIcon を追加インポート アイコン表示のため
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QMessageBox,QApplication
)
from src.ui.input_pane import InputPane
from src.ui.settings_pane import SettingsPane
from src.ui.output_pane import OutputPane
from src.core.bitrate_calc import BitrateCalculator
from src.core.ffmpeg_worker import FFmpegWorker
from src.utils.path_helper import get_tool_path, get_icon_path
from src.core.command_build import build_ffmpeg_commands


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Myffmpeg - Easy FFmpeg GUI Utility")
        self.resize(1280, 850)

        icon_path = get_icon_path("app_icon.ico")
        if icon_path:
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
            if QApplication.instance():
                QApplication.instance().setWindowIcon(app_icon)
        
        # Batch execution state
        self.job_queue: List[Dict[str, Any]] = []
        self.current_job_index: int = -1
        self.current_worker: Optional[FFmpegWorker] = None
        self.success_count: int = 0
        self.fail_count: int = 0
        self.total_bytes_written: int = 0
        self.is_batch_running: bool = False

        self._init_ui()
    
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Main Horizontal Splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left Column: Input Pane
        self.input_pane = InputPane()
        splitter.addWidget(self.input_pane)

        # Center Column: Settings Pane
        self.settings_pane = SettingsPane()
        splitter.addWidget(self.settings_pane)

        # Right Column: Output Pane
        self.output_pane = OutputPane()
        splitter.addWidget(self.output_pane)

        # Set initial splitter proportions (approx 30%, 40%, 30%)
        splitter.setSizes([380, 500, 400])
        main_layout.addWidget(splitter)

        # Connect signals
        self.input_pane.files_changed.connect(self._on_files_changed)
        self.settings_pane.settings_changed.connect(self._update_command_preview_from_settings)
        self.settings_pane.command_preview_requested.connect(self._update_command_preview_for_file)

        self.output_pane.start_requested.connect(self._start_batch_processing)
        self.output_pane.cancel_requested.connect(self._cancel_batch_processing)

        self._update_command_preview_from_settings()

    def _on_files_changed(self):
        selected_files = self.input_pane.get_selected_files()
        self.settings_pane.update_input_files(selected_files)
        self._update_command_preview_from_settings()

    def _update_command_preview_from_settings(self):
        """Update command preview using preview combo selection (or first file as fallback)."""
        preview_file = self.settings_pane.get_preview_file_info()
        if preview_file:
            self._update_command_preview_for_file(preview_file)
        else:
            # Fallback to first selected file
            selected_files = self.input_pane.get_selected_files()
            if selected_files:
                self._update_command_preview_for_file(selected_files[0])
            else:
                self.settings_pane.set_command_preview("（対象ファイルが選択されていません）")

    def _update_command_preview_for_file(self, file_info: Optional[Dict[str, Any]]):
        """Build and display command preview for a specific file_info."""
        if not file_info:
            self._update_command_preview_from_settings()
            return

        settings = self.settings_pane.get_current_settings()
        active_tab = settings["active_tab"]
        
        try:
            cmd_list, _ = build_ffmpeg_commands(file_info=file_info,settings=settings,overwrite=False)
            cmd_str_list = [ (subprocess.list2cmdline(cmd) if sys.platform == "win32" else " ".join(cmd)) for cmd in cmd_list]
            self.settings_pane.set_command_preview("\n".join(cmd_str_list))
        except Exception as e:
            self.settings_pane.set_command_preview(f"コマンド作成エラー: {e}")
        
    def _start_batch_processing(self, auto_overwrite: Optional[bool] = None):
        selected_files = self.input_pane.get_selected_files()
        if not selected_files:
            if auto_overwrite is None:
                QMessageBox.warning(self, "注意", "処理対象のファイルが選択されていません。")
            else:
                self.output_pane.append_log("[Myffmpeg] 処理対象ファイルがないため終了します。\n")
            return

        settings = self.settings_pane.get_current_settings()
        active_tab = settings["active_tab"]

        self.job_queue = []
        for file_info in selected_files:
            # Build command / check output path
            try:
                passlog_prefix = os.path.join(tempfile.gettempdir(), f"myffmpeg_passlog_{os.getpid()}")
                cmd_list, out_path = build_ffmpeg_commands(file_info=file_info,settings=settings,overwrite=False,passlog_prefix=passlog_prefix)
            except ValueError as e:
                QMessageBox.warning(self, "エラー", f"ファイル {file_info['file_name']} の設定エラー:\n{e}")
                return

            overwrite_flag = False
            if os.path.exists(out_path):
                if auto_overwrite is True:
                    overwrite_flag = True
                elif auto_overwrite is False:
                    self.output_pane.append_log(f"[Myffmpeg] スキップされました (自動応答): {out_path}\n")
                    continue
                else:
                    reply = QMessageBox.question(
                        self,
                        "上書き確認",
                        f"出力先ファイルが既に存在します:\n{out_path}\n\n上書きしますか？",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.Cancel:
                        self.output_pane.append_log("[Myffmpeg] 上書き確認によりジョブ全体をキャンセルしました。\n")
                        return
                    elif reply == QMessageBox.No:
                        self.output_pane.append_log(f"[Myffmpeg] スキップされました: {out_path}\n")
                        continue
                    else:
                        overwrite_flag = True

            # Rebuild with overwrite flag if needed
            if overwrite_flag:
                cmd_list, out_path = build_ffmpeg_commands(file_info=file_info,settings=settings,overwrite=True,passlog_prefix=passlog_prefix)

            self.job_queue.append({
                "file_info": file_info,
                "command_list": cmd_list,
                "output_file": out_path,
                "passlog_prefix": passlog_prefix
            })

        if not self.job_queue:
            if auto_overwrite is None:
                QMessageBox.information(self, "案内", "実行対象のジョブがありません（全件スキップされたか無効です）。")
            return

        # Prepare Batch Run
        self.is_batch_running = True
        self.current_job_index = 0
        self.success_count = 0
        self.fail_count = 0
        self.total_bytes_written = 0

        self.output_pane.set_processing_state(True)
        self.output_pane.append_log(
            f"========================================\n"
            f"[Myffmpeg] バッチ処理開始: 全 {len(self.job_queue)} 件\n"
            f"========================================\n"
        )

        self._run_next_job()

    def _run_next_job(self):
        if not self.is_batch_running or self.current_job_index >= len(self.job_queue):
            self._finish_batch_processing()
            return

        job = self.job_queue[self.current_job_index]
        file_info = job["file_info"]
        total_jobs = len(self.job_queue)
        idx_display = self.current_job_index + 1

        status_text = f"処理中 [{idx_display}/{total_jobs}]: {file_info['file_name']}"
        self.output_pane.set_status(status_text)
        self.output_pane.append_log(f"\n[{idx_display}/{total_jobs}] 処理開始: {file_info['file_name']}\n")

        self.current_worker = FFmpegWorker(
            command_args_list=job["command_list"],
            output_file=job["output_file"],
            total_duration_sec=file_info.get("duration", 0.0),
            passlog_prefix=job["passlog_prefix"],
            parent=self
        )

        self.current_worker.progress_updated.connect(self._on_worker_progress)
        self.current_worker.log_received.connect(self.output_pane.append_log)
        self.current_worker.progress_stats_updated.connect(self.output_pane.update_ffmpeg_stats)
        self.current_worker.status_changed.connect(self.output_pane.set_status)
        self.current_worker.job_finished.connect(self._on_worker_job_finished)
        self.current_worker.start()

    def _on_worker_progress(self, job_progress_pct: int):
        total_jobs = len(self.job_queue)
        if total_jobs > 0:
            overall_pct = int(((self.current_job_index + (job_progress_pct / 100.0)) / total_jobs) * 100)
            self.output_pane.set_progress(min(100, max(0, overall_pct)))

    def _on_worker_job_finished(self, success: bool, result_msg: str):
        if success and os.path.exists(result_msg):
            self.success_count += 1
            file_size = os.path.getsize(result_msg)
            self.total_bytes_written += file_size
            size_mb = file_size / (1024 * 1024)
            self.output_pane.append_log(f"✅ 成功 ({size_mb:.2f} MB): {result_msg}\n")
        else:
            self.fail_count += 1
            self.output_pane.append_log(f"❌ 失敗: {result_msg}\n")

        self.current_job_index += 1
        self._run_next_job()

    def _cancel_batch_processing(self):
        if not self.is_batch_running:
            return

        self.output_pane.append_log("\n⚠️ ユーザーによりキャンセルが要求されました...\n")
        self.is_batch_running = False

        if self.current_worker:
            self.current_worker.cancel()

        self._finish_batch_processing()

    def _finish_batch_processing(self):
        self.is_batch_running = False
        self.output_pane.set_processing_state(False)
        self.output_pane.set_progress(100 if self.success_count > 0 else 0)

        total_mb = self.total_bytes_written / (1024 * 1024)
        summary_msg = (
            f"バッチ処理完了 - 成功: {self.success_count} 件 | 失敗: {self.fail_count} 件 | 生成総サイズ: {total_mb:.2f} MB"
        )
        self.output_pane.set_status(summary_msg)
        self.output_pane.append_log(
            f"\n========================================\n"
            f"{summary_msg}\n"
            f"========================================\n"
        )

    def get_current_settings(self) -> Dict[str, Any]:
        return self.settings_pane.get_current_settings()
