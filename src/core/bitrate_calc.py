from typing import Dict, Any

class BitrateCalculator:
    @staticmethod
    def parse_bitrate_str_to_kbps(bitrate_str: str) -> float:
        """Helper to parse strings like '128k', '320k', '1M' into kbps (float)."""
        s = str(bitrate_str).strip().lower()
        if s.endswith("k"):
            return float(s[:-1])
        elif s.endswith("m"):
            return float(s[:-1]) * 1000.0
        elif s.isdigit():
            return float(s) / 1000.0
        return 128.0

    @classmethod
    def calculate_video_bitrate(
        cls,
        duration_sec: float,
        target_size_mb: float,
        audio_bitrate_kbps: float = 128.0
    ) -> Dict[str, Any]:
        """
        Calculates optimal target video bitrate (in kbps) for 2-pass encoding.
        
        Formula:
        audio_size_mb = (audio_bitrate_kbps * duration_sec) / 8000.0
        video_size_mb = target_size_mb - audio_size_mb
        video_bitrate_kbps = (video_size_mb * 8000.0) / duration_sec
        """
        if duration_sec <= 0:
            raise ValueError("動画の長さ（秒数）が不正です。")

        if target_size_mb <= 0:
            raise ValueError("目標サイズ（MB）は0より大きい値を指定してください。")

        audio_size_mb = (audio_bitrate_kbps * duration_sec) / 8000.0
        video_size_mb = target_size_mb - audio_size_mb

        if video_size_mb <= 0:
            raise ValueError(
                f"目標サイズ ({target_size_mb:.2f} MB) が音声サイズ ({audio_size_mb:.2f} MB) 以下のため、映像に割り当てるサイズがありません。目標サイズを増やしてください。"
            )

        video_bitrate_kbps = (video_size_mb * 8000.0) / duration_sec

        if video_bitrate_kbps < 10.0:
            raise ValueError(
                f"計算された映像ビットレート ({video_bitrate_kbps:.1f} kbps) が極端に低すぎます。目標サイズを増やしてください。"
            )

        return {
            "duration_sec": duration_sec,
            "target_size_mb": target_size_mb,
            "audio_bitrate_kbps": audio_bitrate_kbps,
            "audio_size_mb": round(audio_size_mb, 3),
            "video_size_mb": round(video_size_mb, 3),
            "video_bitrate_kbps": int(round(video_bitrate_kbps)),
            "total_bitrate_kbps": int(round(video_bitrate_kbps + audio_bitrate_kbps))
        }
