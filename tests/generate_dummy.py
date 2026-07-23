import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.utils.path_helper import get_tool_path

def generate_dummy_video(output_path: str, duration_sec: int = 5, width: int = 640, height: int = 360, fps: int = 30) -> str:
    """
    Generates a dummy MP4 video with video test patterns and synthetic sine audio using ffmpeg.
    """
    ffmpeg_exe = get_tool_path("ffmpeg")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_sec}:size={width}x{height}:rate={fps}",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration_sec}",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to generate dummy video: {res.stderr}")
    
    return os.path.abspath(output_path)

if __name__ == "__main__":
    out = os.path.join(PROJECT_ROOT, "tests", "dummy_test.mp4")
    generate_dummy_video(out, duration_sec=5)
    print(f"Dummy video generated at: {out}")
