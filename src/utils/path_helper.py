import os
import sys
import shutil

def get_tool_path(tool_name: str) -> str:
    """
    Get absolute path to executable tool (e.g. 'ffmpeg', 'ffprobe').
    Checks sys._MEIPASS for PyInstaller bundles first, then project's tools/ directory,
    and finally falls back to system PATH.
    """
    # Ensure extension on Windows if missing
    base_name = tool_name
    if sys.platform == "win32" and not base_name.lower().endswith(".exe"):
        exe_name = base_name + ".exe"
    else:
        exe_name = base_name

    # 1. PyInstaller bundled path
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, "tools", exe_name)
        if os.path.isfile(bundled_path):
            return os.path.abspath(bundled_path)
        bundled_root_path = os.path.join(sys._MEIPASS, exe_name)
        if os.path.isfile(bundled_root_path):
            return os.path.abspath(bundled_root_path)

    # 2. Local workspace tools directory
    # Assume workspace root is parent of src/ or current working directory
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_tools_path = os.path.join(base_dir, "tools", exe_name)
    if os.path.isfile(local_tools_path):
        return os.path.abspath(local_tools_path)

    # Fallback checking cwd / tools
    cwd_tools_path = os.path.join(os.getcwd(), "tools", exe_name)
    if os.path.isfile(cwd_tools_path):
        return os.path.abspath(cwd_tools_path)

    # 3. System PATH fallback
    system_path = shutil.which(tool_name) or shutil.which(exe_name)
    if system_path:
        return os.path.abspath(system_path)

    # Return default expected path even if not found (calling code can handle missing file error)
    return os.path.abspath(local_tools_path)

def get_icon_path(icon_name: str = "app_icon.ico") -> str:
    """
    Get absolute path to icon file.
    Checks sys._MEIPASS for PyInstaller bundles first, then project's assets/ directory.
    """
    # 1. PyInstaller bundled path
    if hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, "assets", icon_name)
        if os.path.isfile(bundled_path):
            return os.path.abspath(bundled_path)

    # 2. Local workspace assets directory
    # Assume workspace root is parent of src/ (src/utils/path_helper.py -> src/utils -> src -> root)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_asset_path = os.path.join(base_dir, "assets", icon_name)
    if os.path.isfile(local_asset_path):
        return os.path.abspath(local_asset_path)

    # Fallback checking cwd / assets
    cwd_asset_path = os.path.join(os.getcwd(), "assets", icon_name)
    if os.path.isfile(cwd_asset_path):
        return os.path.abspath(cwd_asset_path)

    return ""