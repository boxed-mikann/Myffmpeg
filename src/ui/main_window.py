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
            if active_tab == 2:
                # 2-pass: show Pass1 and Pass2 on separate lines
                p1, p2, _ = self._build_two_pass_args(file_info, settings, overwrite=True)
                cmd1_str = subprocess.list2cmdline(p1) if sys.platform == "win32" else " ".join(p1)
                cmd2_str = subprocess.list2cmdline(p2) if sys.platform == "win32" else " ".join(p2)
                self.settings_pane.set_command_preview(f"Pass1: {cmd1_str}\n\nPass2: {cmd2_str}")
            else:
                cmd, _ = self._build_ffmpeg_command(file_info, settings, overwrite=True)
                cmd_str = subprocess.list2cmdline(cmd) if sys.platform == "win32" else " ".join(cmd)
                self.settings_pane.set_command_preview(cmd_str)
        except Exception as e:
            self.settings_pane.set_command_preview(f"コマンド作成エラー: {e}")

    def _build_ffmpeg_command(
        self,
        file_info: Dict[str, Any],
        settings: Dict[str, Any],
        overwrite: bool = False
    ) -> Tuple[List[str], str]:
        """
        Builds FFmpeg command list and output file path for Tab A or Tab B.
        Returns (command_args_list, output_file_path).
        """
        in_path = file_info["file_path"]
        base_dir = os.path.dirname(in_path)
        base_name, _ = os.path.splitext(os.path.basename(in_path))

        active_tab = settings["active_tab"]
        ffmpeg_exe = get_tool_path("ffmpeg")

        cmd = [ffmpeg_exe]
        if overwrite:
            cmd.append("-y")
        cmd.extend(["-i", in_path])

        if active_tab == 0:
            ra = settings["remove_video"]
            fmt = ra.get("format", "mp3")
            out_ext = f".{fmt}"
            out_file = os.path.join(base_dir, f"{base_name}{ra.get('output_suffix', '_novideo')}{out_ext}")
            cmd.append("-vn")
            if fmt == "mp3":
                cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
            else:
                cmd.extend(["-c:a", "copy"])
            if settings["custom_options"]:
                cmd.extend(settings["custom_options"].split())
            cmd.append(out_file)
            return cmd, out_file

        elif active_tab == 1:
            qb = settings["quality_compress"]
            out_file = os.path.join(base_dir, f"{base_name}{qb.get('output_suffix', '_compressed')}.mp4")
            cmd.extend(self.settings_pane._build_video_args(qb))
            if settings["custom_options"]:
                cmd.extend(settings["custom_options"].split())
            cmd.append(out_file)
            return cmd, out_file

        raise ValueError(f"この関数は Tab A/B のみ対応しています。active_tab={active_tab}")

    def _build_two_pass_args(
        self,
        file_info: Dict[str, Any],
        settings: Dict[str, Any],
        overwrite: bool = False,
        passlog_prefix: Optional[str] = None
    ) -> Tuple[List[str], List[str], str]:
        """
        Builds Pass1 and Pass2 argument lists for Tab C (2-pass).
        Returns (pass1_args, pass2_args, output_file_path).
        """
        in_path = file_info["file_path"]
        dur = file_info.get("duration", 0.0)
        base_dir = os.path.dirname(in_path)
        base_name, _ = os.path.splitext(os.path.basename(in_path))

        sc = settings["size_compress"]
        out_file = os.path.join(base_dir, f"{base_name}{sc.get('output_suffix', '_targetsize')}.mp4")

        calc = BitrateCalculator.calculate_video_bitrate(
            duration_sec=dur,
            target_size_mb=sc["target_size_mb"],
            audio_bitrate_kbps=BitrateCalculator.parse_bitrate_str_to_kbps(sc["audio_bitrate"])
        )
        v_bitrate_kbps = calc["video_bitrate_kbps"]

        if passlog_prefix is None:
            passlog_prefix = os.path.join(tempfile.gettempdir(), f"myffmpeg_passlog_{os.getpid()}")

        ffmpeg_exe = get_tool_path("ffmpeg")

        pass1_args = [ffmpeg_exe]
        if overwrite:
            pass1_args.append("-y")
        pass1_args.extend(["-i", in_path])
        pass1_args.extend(self.settings_pane._build_video_filter_args(sc))
        pass1_args.extend([
            "-c:v", self.settings_pane._get_codec_name(sc["encoder"]),
            "-b:v", f"{v_bitrate_kbps}k",
            "-pass", "1",
            "-passlogfile", passlog_prefix,
            "-an",
            "-f", "null", "NUL" if os.name == "nt" else "/dev/null"
        ])

        pass2_args = [ffmpeg_exe]
        if overwrite:
            pass2_args.append("-y")
        pass2_args.extend(["-i", in_path])
        pass2_args.extend(self.settings_pane._build_video_filter_args(sc))
        pass2_args.extend([
            "-c:v", self.settings_pane._get_codec_name(sc["encoder"]),
            "-b:v", f"{v_bitrate_kbps}k",
            "-pass", "2",
            "-passlogfile", passlog_prefix
        ])
        pass2_args.extend(self.settings_pane._build_audio_args(sc))
        if settings["custom_options"]:
            pass2_args.extend(settings["custom_options"].split())
        pass2_args.append(out_file)

        return pass1_args, pass2_args, out_file

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
                if active_tab == 2:
                    passlog_prefix = os.path.join(tempfile.gettempdir(), f"myffmpeg_passlog_{os.getpid()}")
                    pass1_args, pass2_args, out_path = self._build_two_pass_args(
                        file_info, settings, overwrite=False, passlog_prefix=passlog_prefix
                    )
                    cmd = pass2_args  # dummy placeholder (not used for 2-pass jobs)
                    is_two_pass = True
                else:
                    cmd, out_path = self._build_ffmpeg_command(file_info, settings, overwrite=False)
                    is_two_pass = False
                    pass1_args, pass2_args, passlog_prefix = None, None, None
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
                if active_tab == 2:
                    pass1_args, pass2_args, out_path = self._build_two_pass_args(
                        file_info, settings, overwrite=True, passlog_prefix=passlog_prefix
                    )
                    cmd = pass2_args
                else:
                    cmd, out_path = self._build_ffmpeg_command(file_info, settings, overwrite=True)

            self.job_queue.append({
                "file_info": file_info,
                "command": cmd,
                "output_file": out_path,
                "is_two_pass": is_two_pass,
                "pass1_args": pass1_args,
                "pass2_args": pass2_args,
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
            command_args=job["command"],
            output_file=job["output_file"],
            total_duration_sec=file_info.get("duration", 0.0),
            is_two_pass=job["is_two_pass"],
            pass1_args=job["pass1_args"],
            pass2_args=job["pass2_args"],
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
