import os
import json
import subprocess
from typing import Dict, Any
from src.utils.path_helper import get_tool_path

class FFprobeParser:
    def __init__(self, ffprobe_exe: str = None):
        self.ffprobe_exe = ffprobe_exe or get_tool_path("ffprobe")

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        Executes ffprobe on the given file path and returns parsed metadata dict.
        """
        abs_path = os.path.abspath(file_path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found: {abs_path}")

        cmd = [
            self.ffprobe_exe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            abs_path
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"ffprobe failed for file {abs_path}: {res.stderr}")

        try:
            data = json.loads(res.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse ffprobe JSON output: {e}")

        streams = data.get("streams", [])
        format_info = data.get("format", {})

        file_size = int(format_info.get("size", os.path.getsize(abs_path)))
        duration = float(format_info.get("duration", 0.0))

        width = 0
        height = 0
        fps = 0.0
        video_codec = ""
        audio_codec = ""

        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type == "video" and not video_codec:
                video_codec = stream.get("codec_name", "")
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))

                # Parse frame rate
                r_frame_rate = stream.get("r_frame_rate", "")
                if "/" in r_frame_rate:
                    num, den = r_frame_rate.split("/")
                    if float(den) > 0:
                        fps = round(float(num) / float(den), 2)
                elif r_frame_rate:
                    try:
                        fps = round(float(r_frame_rate), 2)
                    except ValueError:
                        pass
            elif codec_type == "audio" and not audio_codec:
                audio_codec = stream.get("codec_name", "")

        resolution_str = f"{width}x{height}" if (width > 0 and height > 0) else "N/A"

        return {
            "file_path": abs_path,
            "file_name": os.path.basename(abs_path),
            "file_size": file_size,
            "duration": duration,
            "width": width,
            "height": height,
            "resolution_str": resolution_str,
            "fps": fps,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "raw_json": data
        }
