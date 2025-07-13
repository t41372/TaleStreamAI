# app/ffmpeg_utils.py
import subprocess
import platform
import functools
from .logger import log_info, log_warning

@functools.lru_cache(maxsize=1)
def get_ffmpeg_gpu_params():
    """
    自动检测并返回适用于当前系统的 FFmpeg GPU 加速参数。
    使用 lru_cache 缓存结果，避免重复检测。
    
    Returns:
        dict: 包含 pre_input 和 output_params 的字典。
    """
    system = platform.system()
    log_info(f"检测操作系统: {system}")

    # 检查 ffmpeg 是否存在
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        log_warning("系统中未找到 ffmpeg 或无法执行。将使用纯 CPU 编码。")
        return {"pre_input": [], "output_params": {"codec": "libx264"}, "extra_params": []}

    # NVIDIA (Windows/Linux)
    if system in ["Windows", "Linux"]:
        try:
            result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True)
            if "cuda" in result.stdout:
                log_info("✅ 检测到 NVIDIA CUDA 支持。")
                # 检查 h264_nvenc 编码器
                result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
                if 'h264_nvenc' in result.stdout:
                    log_info("✅ 检测到 h264_nvenc 编码器。启用 NVIDIA GPU 加速。")
                    return {
                        "pre_input": ["-hwaccel", "cuda"],
                        "output_params": {"codec": "h264_nvenc", "preset": "fast"},
                        "extra_params": [] # NVIDIA编码器不需要额外参数
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass # ffmpeg 未找到或执行失败，继续尝试其他选项

    # Apple Silicon / Intel (macOS)
    if system == "Darwin":
        try:
            result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True)
            if "videotoolbox" in result.stdout:
                log_info("✅ 检测到 Apple VideoToolbox 支持。")
                # 检查 h264_videotoolbox 编码器
                result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
                if 'h264_videotoolbox' in result.stdout:
                    log_info("✅ 检测到 h264_videotoolbox 编码器。启用 macOS GPU 加速。")
                    return {
                        "pre_input": ["-hwaccel", "videotoolbox"],
                        "output_params": {"codec": "h264_videotoolbox"},
                        "extra_params": ["-b:v", "8000k"] # 比特率参数通过ffmpeg_params传递
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
             pass

    # Intel Quick Sync Video (Windows/Linux)
    if system in ["Windows", "Linux"]:
        try:
            result = subprocess.run(["ffmpeg", "-hwaccels"], capture_output=True, text=True)
            if "qsv" in result.stdout:
                log_info("✅ 检测到 Intel QSV 支持。")
                result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
                if 'h264_qsv' in result.stdout:
                    log_info("✅ 检测到 h264_qsv 编码器。启用 Intel QSV 加速。")
                    return {
                        "pre_input": ["-hwaccel", "qsv"],
                        "output_params": {"codec": "h264_qsv", "preset": "fast"},
                        "extra_params": [] # Intel QSV不需要额外参数
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    log_warning("⚠️ 未检测到可用的 GPU 加速硬件。将回退到 CPU (libx264) 进行编码。")
    return {"pre_input": [], "output_params": {"codec": "libx264"}, "extra_params": []} 