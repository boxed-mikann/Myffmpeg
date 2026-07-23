import os
import json
from typing import Dict, Any

DEFAULT_PRESET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "presets",
    "settings.json"
)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "active_tab": 0,  # 0: Remove Video, 1: Quality Compress, 2: Size Compress
    # Tab A: Remove Video
    "remove_video": {
        "format": "mp3",
        "output_suffix": "_novideo"
    },
    # Tab B: Quality Compression
    "quality_compress": {
        "resolution": "Original",
        "fps": "Original",
        "encoder": "CPU (libx264)",
        "crf": 23,
        "preset_speed": "medium",
        "audio_mono": False,
        "audio_bitrate": "128k",
        "output_suffix": "_compressed"
    },
    # Tab C: Target Size Compression
    "size_compress": {
        "resolution": "Original",
        "fps": "Original",
        "encoder": "CPU (libx264)",
        "target_size_mb": 50.0,
        "audio_mono": False,
        "audio_bitrate": "128k",
        "output_suffix": "_targetsize"
    },
    # Custom Extra Options
    "custom_options": ""
}

class PresetManager:
    def __init__(self, preset_path: str = DEFAULT_PRESET_PATH):
        self.preset_path = os.path.abspath(preset_path)

    def load_settings(self) -> Dict[str, Any]:
        """Loads settings from JSON file. Returns copy of default settings if file doesn't exist or is invalid."""
        if not os.path.isfile(self.preset_path):
            return dict(DEFAULT_SETTINGS)
        try:
            with open(self.preset_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_SETTINGS)
                for k, v in data.items():
                    if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                        merged[k].update(v)
                    else:
                        merged[k] = v
                return merged
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Saves settings dictionary to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.preset_path), exist_ok=True)
            with open(self.preset_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
