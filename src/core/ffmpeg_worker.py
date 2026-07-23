import os
import re
import sys
import glob
import subprocess
from typing import List, Optional, Tuple
from PySide6.QtCore import QThread, Signal
from src.utils.path_helper import get_tool_path

# キー=値 形式の progress ラインのキー一覧（ログに流さず進捗ステータス欄に表示する）
PROGRESS_KEYS = {
    "frame", "fps", "stream_0_0_q", "bitrate", "total_size",
    "out_time_us", "out_time_ms", "out_time", "dup_frames",
    "drop_frames", "speed", "progress"
}

class FFmpegWorker(QThread):
    progress_updated = Signal(int)        # Progress 0 - 100%
    log_received = Signal(str)            # Raw log line from FFmpeg (普通のログのみ)
    progress_stats_updated = Signal(dict) # key=value 型の進捗行 (fps=, speed=, out_time= など)
    time_updated = Signal(float)          # Processed duration in seconds
    status_changed = Signal(str)          # Status message
    job_finished = Signal(bool, str)      # (Success, output_file or error message)

    def __init__(
        self,
        command_args: List[str],
        output_file: str,
        total_duration_sec: float = 0.0,
        is_two_pass: bool = False,
        pass1_args: Optional[List[str]] = None,
        pass2_args: Optional[List[str]] = None,
        passlog_prefix: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.ffmpeg_exe = get_tool_path("ffmpeg")
        self.command_args = command_args
        self.output_file = os.path.abspath(output_file)
        self.total_duration_sec = total_duration_sec
        self.is_two_pass = is_two_pass
        self.pass1_args = pass1_args
        self.pass2_args = pass2_args
        self.passlog_prefix = passlog_prefix

        self._process: Optional[subprocess.Popen] = None
        self._is_cancelled = False

    def cancel(self):
        """Cancels the ongoing FFmpeg process and cleans up output file."""
        self._is_cancelled = True
        self.status_changed.emit("キャンセル処理中...")
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        # Clean up partial output file
        self._cleanup_partial_file()

    def _cleanup_partial_file(self):
        if os.path.isfile(self.output_file):
            try:
                os.remove(self.output_file)
                self.log_received.emit(f"[Myffmpeg] 途中の出力ファイルを削除しました: {self.output_file}\n")
            except Exception as e:
                self.log_received.emit(f"[Myffmpeg] 途中ファイルの削除に失敗しました: {e}\n")

    def _cleanup_pass_logs(self):
        if self.passlog_prefix:
            pattern = self.passlog_prefix + "*"
            for f in glob.glob(pattern):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def run(self):
        self._is_cancelled = False
        self.progress_updated.emit(0)

        if self.is_two_pass and self.pass1_args and self.pass2_args:
            success, err_msg = self._run_two_pass()
        else:
            success, err_msg = self._run_single_pass(self.command_args, progress_scale=(0.0, 1.0))

        # Cleanup pass logs if any
        self._cleanup_pass_logs()

        if self._is_cancelled:
            self._cleanup_partial_file()
            self.job_finished.emit(False, "処理がキャンセルされました。")
        elif success:
            self.progress_updated.emit(100)
            self.job_finished.emit(True, self.output_file)
        else:
            self._cleanup_partial_file()
            self.job_finished.emit(False, err_msg)

    def _run_single_pass(self, cmd_args: List[str], progress_scale: Tuple[float, float] = (0.0, 1.0)) -> Tuple[bool, str]:
        # Build command: include ffmpeg exe if not present
        full_cmd = list(cmd_args)
        if full_cmd[0] != self.ffmpeg_exe:
            full_cmd.insert(0, self.ffmpeg_exe)

        # Force -progress - and -nostats if not present
        if "-progress" not in full_cmd:
            full_cmd.extend(["-progress", "-", "-nostats"])

        # Display full command in logs
        cmd_str = subprocess.list2cmdline(full_cmd) if sys.platform == "win32" else " ".join(full_cmd)
        self.log_received.emit(f"$ {cmd_str}\n")

        try:
            # Set creationflags to hide command prompt window on Windows
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **kwargs
            )
        except Exception as e:
            return False, f"FFmpegプロセスの起動に失敗しました: {e}"

        min_p, max_p = progress_scale
        current_stats: dict = {}

        while True:
            if self._is_cancelled:
                break

            line = self._process.stdout.readline()
            if not line and self._process.poll() is not None:
                break

            if not line:
                continue

            # Check if line is a progress key=value line
            stripped = line.rstrip("\n\r")
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                key = key.strip()
                val = val.strip()
                if key in PROGRESS_KEYS:
                    current_stats[key] = val

                    # Parse out_time_us for progress
                    if key == "out_time_us":
                        if val.lstrip("-").isdigit() and int(val) >= 0:
                            us = float(val)
                            sec = us / 1000000.0
                            self.time_updated.emit(sec)
                            if self.total_duration_sec > 0:
                                pct = (sec / self.total_duration_sec) * 100.0
                                scaled_pct = min_p * 100.0 + (pct * (max_p - min_p))
                                self.progress_updated.emit(int(min(100, max(0, scaled_pct))))
                    elif key == "out_time":
                        m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", val)
                        if m:
                            h, mins, s = map(float, m.groups())
                            sec = h * 3600 + mins * 60 + s
                            self.time_updated.emit(sec)
                            if self.total_duration_sec > 0:
                                pct = (sec / self.total_duration_sec) * 100.0
                                scaled_pct = min_p * 100.0 + (pct * (max_p - min_p))
                                self.progress_updated.emit(int(min(100, max(0, scaled_pct))))

                    # Emit updated stats dict (overwrite display, not scroll log)
                    self.progress_stats_updated.emit(dict(current_stats))
                    continue  # Don't write progress lines to log

            # Regular log line — emit to scrollable log
            self.log_received.emit(line)

        if self._process and self._process.stdout:
            try:
                self._process.stdout.close()
            except Exception:
                pass
        self._process.wait()
        return_code = self._process.returncode

        if self._is_cancelled:
            return False, "キャンセルされました"
        if return_code != 0:
            return False, f"FFmpegが終了コード {return_code} でエラー終了しました。"
        return True, ""

    def _run_two_pass(self) -> Tuple[bool, str]:
        self.status_changed.emit("2パスエンコード: パス1実行中...")
        ok1, err1 = self._run_single_pass(self.pass1_args, progress_scale=(0.0, 0.5))
        if not ok1 or self._is_cancelled:
            return False, f"Pass 1 エラー: {err1}"

        self.status_changed.emit("2パスエンコード: パス2実行中...")
        ok2, err2 = self._run_single_pass(self.pass2_args, progress_scale=(0.5, 1.0))
        if not ok2 or self._is_cancelled:
            return False, f"Pass 2 エラー: {err2}"

        return True, ""
