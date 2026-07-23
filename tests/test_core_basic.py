import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.ffprobe_parser import FFprobeParser
from src.core.bitrate_calc import BitrateCalculator
from tests.generate_dummy import generate_dummy_video

class TestCoreBasic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dummy_path = os.path.join(PROJECT_ROOT, "tests", "dummy_core_test.mp4")
        generate_dummy_video(cls.dummy_path, duration_sec=5, width=640, height=360, fps=30)

    @classmethod
    def tearDownClass(cls):
        if os.path.isfile(cls.dummy_path):
            try:
                os.remove(cls.dummy_path)
            except OSError:
                pass

    def test_ffprobe_parser(self):
        parser = FFprobeParser()
        info = parser.parse_file(self.dummy_path)
        self.assertEqual(info["width"], 640)
        self.assertEqual(info["height"], 360)
        self.assertAlmostEqual(info["duration"], 5.0, delta=0.5)
        self.assertEqual(info["resolution_str"], "640x360")
        self.assertEqual(info["video_codec"], "h264")
        self.assertEqual(info["audio_codec"], "aac")

    def test_bitrate_calculator_valid(self):
        # 10s video, 128kbps audio => audio size = 128*10/8000 = 0.16 MB
        # Target size = 1.16 MB => video size = 1.0 MB => video bitrate = 1*8000/10 = 800 kbps
        res = BitrateCalculator.calculate_video_bitrate(duration_sec=10.0, target_size_mb=1.16, audio_bitrate_kbps=128.0)
        self.assertEqual(res["video_bitrate_kbps"], 800)
        self.assertAlmostEqual(res["video_size_mb"], 1.0, places=2)

    def test_bitrate_calculator_error_too_small(self):
        # Target size smaller than audio size
        with self.assertRaises(ValueError) as ctx:
            BitrateCalculator.calculate_video_bitrate(duration_sec=10.0, target_size_mb=0.1, audio_bitrate_kbps=128.0)
        self.assertIn("映像に割り当てるサイズがありません", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
