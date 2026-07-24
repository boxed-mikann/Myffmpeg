from typing import List, Dict, Any, Optional, Tuple
import os
from src.utils.path_helper import get_tool_path
from src.core.bitrate_calc import BitrateCalculator
import tempfile

def build_ffmpeg_commands(
        file_info: Dict[str, Any],
        settings: Dict[str, Any],
        overwrite: bool = False,
        passlog_prefix: Optional[str] = None,
        IsPreview:bool = False,
    ) -> Tuple[List[List[str]], str]:
        """
        Builds FFmpeg command list and output file path for Tab A or Tab B.
        Returns (command_args_list, output_file_path).
        この関数がコマンド生成を一括で担当しています。
        """
        in_path = file_info["file_path"]
        base_dir = os.path.dirname(in_path)
        base_name, _ = os.path.splitext(os.path.basename(in_path))

        active_tab = settings["active_tab"]
        ffmpeg_exe = get_tool_path("ffmpeg")

        cmd = [ffmpeg_exe]
        if overwrite:
            cmd.append("-y")
        if IsPreview:
            cmd.extend(["-ss", "0", "-t", "10"])
        cmd.extend(["-i", in_path]) 

        if active_tab == 0:
            ra = settings["remove_video"]
            fmt = ra.get("format", "mp3")
            out_ext = f".{fmt}"
            if IsPreview:
                out_file = os.path.join(tempfile.gettempdir(), f"myffmpeg_preview_10s{out_ext}")
            else:
                out_file = os.path.join(base_dir, f"{base_name}{ra.get('output_suffix', '_novideo')}{out_ext}")
            cmd.append("-vn")
            # if fmt == "mp3":
            #     cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
            # else:
            #     cmd.extend(["-c:a", "copy"])
            cmd.extend(["-f",fmt])
            if settings["custom_options"]:
                cmd.extend(settings["custom_options"].split())
            cmd.append(out_file)
            return [cmd], out_file

        elif active_tab == 1:
            qb = settings["quality_compress"]
            if IsPreview:
                out_file = os.path.join(tempfile.gettempdir(), f"myffmpeg_preview_10s.mp4")
            else:
                out_file = os.path.join(base_dir, f"{base_name}{qb.get('output_suffix', '_compressed')}.mp4")
            cmd.extend(build_video_args(qb))
            if settings["custom_options"]:
                cmd.extend(settings["custom_options"].split())
            cmd.append(out_file)
            return [cmd], out_file
        
        elif active_tab == 2:
            sc = settings["size_compress"]
            dur = file_info.get("duration", 0.0)
            if IsPreview:
                out_file = os.path.join(tempfile.gettempdir(), f"myffmpeg_preview_10s.mp4")
            else:
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
            if "libsvtav1" == sc["encoder"]:#av1も2パスが出来ない→1パス
                cmd.extend([
                    "-c:v", sc["encoder"],
                    "-preset","5",
                    "-b:v", f"{v_bitrate_kbps}k"
                ])
                cmd.extend(build_audio_args(sc))
                if settings["custom_options"]:
                    cmd.extend(settings["custom_options"].split())
                cmd.append(out_file)
                return [cmd], out_file
            elif "lib" in sc["encoder"]:
                pass1_args = [ffmpeg_exe]
                if overwrite:
                    pass1_args.append("-y")
                if IsPreview:
                    pass1_args.extend(["-ss", "0", "-t", "10"])
                pass1_args.extend(["-i", in_path])
                pass1_args.extend(build_video_filter_args(sc))
                pass1_args.extend([
                    "-c:v", sc["encoder"],
                    "-preset", "slow",
                    "-b:v", f"{v_bitrate_kbps}k",
                    "-pass", "1",
                    "-passlogfile", passlog_prefix,
                    "-an",
                    "-f", "null", "NUL" if os.name == "nt" else "/dev/null"
                ])

                pass2_args = [ffmpeg_exe]
                if overwrite:
                    pass2_args.append("-y")
                if IsPreview:
                    pass2_args.extend(["-ss", "0", "-t", "10"])
                pass2_args.extend(["-i", in_path])
                pass2_args.extend(build_video_filter_args(sc))
                pass2_args.extend([
                    "-c:v", sc["encoder"],
                    "-preset", "slow",
                    "-b:v", f"{v_bitrate_kbps}k",
                    "-pass", "2",
                    "-passlogfile", passlog_prefix
                ])
                pass2_args.extend(build_audio_args(sc))
                if settings["custom_options"]:
                    pass2_args.extend(settings["custom_options"].split())
                pass2_args.append(out_file)
                return [pass1_args,pass2_args], out_file
            elif "nvenc" in sc["encoder"]:
                cmd.extend([
                    "-c:v", sc["encoder"],
                    "-preset", "p6",
                    "-rc","vbr",
                    "-b:v", f"{v_bitrate_kbps}k",
                    "-maxrate", f"{int(v_bitrate_kbps*1.5)}k",
                    "-bufsize", f"{int(v_bitrate_kbps*3)}k"
                    "-multipass","fullres"
                ])
                cmd.extend(build_audio_args(sc))
                if settings["custom_options"]:
                    cmd.extend(settings["custom_options"].split())
                cmd.append(out_file)
                return [cmd], out_file
            elif "qsv" in sc["encoder"]:
                cmd.extend([
                    "-c:v", sc["encoder"],
                    "-preset","slow",
                    "-rc_mode","la_vbr",
                    "-b:v", f"{v_bitrate_kbps}k",
                    "-maxrate", f"{int(v_bitrate_kbps*1.5)}k",
                    "-bufsize", f"{int(v_bitrate_kbps*3)}k"
                ])
                cmd.extend(build_audio_args(sc))
                if settings["custom_options"]:
                    cmd.extend(settings["custom_options"].split())
                cmd.append(out_file)
                return [cmd], out_file
            elif "amf" in sc["encoder"]:
                cmd.extend([
                    "-c:v", sc["encoder"],
                    "-quality", "quality",
                    "-rc","vbr_peak",
                    "-b:v", f"{v_bitrate_kbps}k",
                    "-maxrate", f"{int(v_bitrate_kbps*1.5)}k",
                    "-bufsize", f"{int(v_bitrate_kbps*3)}k"
                    
                ])
                cmd.extend(build_audio_args(sc))
                if settings["custom_options"]:
                    cmd.extend(settings["custom_options"].split())
                cmd.append(out_file)
                return [cmd], out_file
            else:
                return [], f"未知のエンコーダーです: {sc['encoder']}"

# ------------------- Command Builder Helpers -------------------
def build_video_filter_args(settings: Dict[str, Any]) -> List[str]:
        args = []
        res = settings.get("resolution", "元のまま")
        fps = settings.get("fps", "元のまま")

        filters = []
        if res != "元のまま" and "x" in res:
            w, h = res.split("x")
            filters.append(f"scale={w}:{h}")
        if fps != "元のまま" and fps.isdigit():
            filters.append(f"fps={fps}")

        if filters:
            args.extend(["-vf", ",".join(filters)])
        return args

def build_audio_args(settings: Dict[str, Any]) -> List[str]:
    args = ["-c:a", "aac"]
    if settings.get("audio_mono", False):
        args.extend(["-ac", "1"])
    abit = settings.get("audio_bitrate", "元のまま")
    if abit != "元のまま":
        args.extend(["-b:a", abit])
    return args

def build_video_args(qb: Dict[str, Any]) -> List[str]:
    args = build_video_filter_args(qb)
    encoder = qb.get("encoder", "libx264")
    args.extend(["-c:v", encoder])

    crf = qb.get("crf", 23)
    args.extend(build_quality_args(encoder, crf))

    preset = qb.get("preset_speed", "medium")
    args.extend(["-preset", preset])

    args.extend(build_audio_args(qb))
    return args

def build_quality_args(encoder: str, quality_value: int) -> List[str]:
    """
    エンコーダー（H.264 / HEVC / AV1共通）に応じた固定画質パラメータを生成する
    """
    if "lib" in encoder:
        return ["-crf", str(quality_value)]
    elif "nvenc" in encoder:
        return ["-rc", "vbr", "-cq", str(quality_value)]
    elif "qsv" in encoder:
        return ["-global_quality", str(quality_value)]
    elif "amf" in encoder:
        q_str = str(quality_value)
        return ["-rc", "cqp", "-qp_i", q_str, "-qp_p", q_str, "-qp_b",q_str]
    return ["-crf", str(quality_value)]