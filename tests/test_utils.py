import os
import sys
import unittest
import tempfile
import json

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.utils.path_helper import get_tool_path
from src.utils.preset_manager import PresetManager, DEFAULT_SETTINGS

class TestUtils(unittest.TestCase):
    def test_path_helper_tools_exist(self):
        ffmpeg_path = get_tool_path("ffmpeg")
        ffprobe_path = get_tool_path("ffprobe")
        self.assertTrue(os.path.isfile(ffmpeg_path), f"ffmpeg tool not found at {ffmpeg_path}")
        self.assertTrue(os.path.isfile(ffprobe_path), f"ffprobe tool not found at {ffprobe_path}")
        self.assertTrue(ffmpeg_path.endswith("ffmpeg.exe") or ffmpeg_path.endswith("ffmpeg"))

    def test_preset_manager_defaults_and_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            preset_file = os.path.join(tmpdir, "test_preset.json")
            pm = PresetManager(preset_file)
            
            # Initial load should return default settings
            settings = pm.load_settings()
            self.assertEqual(settings["active_tab"], DEFAULT_SETTINGS["active_tab"])
            self.assertEqual(settings["quality_compress"]["crf"], 23)

            # Modify and save
            settings["quality_compress"]["crf"] = 18
            settings["custom_options"] = "-tune film"
            save_success = pm.save_settings(settings)
            self.assertTrue(save_success)
            self.assertTrue(os.path.exists(preset_file))

            # Reload
            loaded = pm.load_settings()
            self.assertEqual(loaded["quality_compress"]["crf"], 18)
            self.assertEqual(loaded["custom_options"], "-tune film")

if __name__ == "__main__":
    unittest.main()
