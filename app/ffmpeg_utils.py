# app/ffmpeg_utils.py
import subprocess
import platform
import os
import functools
from loguru import logger


@functools.lru_cache(maxsize=1)
def get_ffmpeg_gpu_params():
    """
    自动检测并返回适用于当前系统的 FFmpeg GPU 加速参数。
    使用 lru_cache 缓存结果，避免重复检测。

    Returns:
        dict: 包含 codec, preset, threads, 和 ffmpeg_params 的字典。
    """
    system = platform.system()
    logger.info(f"检测操作系统: {system}")

    # 检查 ffmpeg 是否存在
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("系统中未找到 ffmpeg 或无法执行。将使用纯 CPU 编码。")
        return {
            "codec": "libx264",
            "preset": "ultrafast",
            "threads": os.cpu_count() or 2,
            "ffmpeg_params": [],
        }

    # NVIDIA (Windows/Linux)
    if system in ["Windows", "Linux"]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hwaccels"], capture_output=True, text=True
            )
            if "cuda" in result.stdout:
                logger.info("✅ 检测到 NVIDIA CUDA 支持。")
                # 检查 h264_nvenc 编码器
                result = subprocess.run(
                    ["ffmpeg", "-encoders"], capture_output=True, text=True
                )
                if "h264_nvenc" in result.stdout:
                    logger.info("✅ 检测到 h264_nvenc 编码器。启用 NVIDIA GPU 加速。")
                    return {
                        "codec": "h264_nvenc",
                        "preset": "fast",
                        "threads": os.cpu_count() or 2,
                        # '-hwaccel cuda' 更多用于解码，编码器h264_nvenc会自动使用GPU。
                        "ffmpeg_params": [],
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass  # ffmpeg 未找到或执行失败，继续尝试其他选项

    # Apple Silicon / Intel (macOS)
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["ffmpeg", "-hwaccels"], capture_output=True, text=True
            )
            if "videotoolbox" in result.stdout:
                logger.info("✅ 检测到 Apple VideoToolbox 支持。")
                # 检查 h264_videotoolbox 编码器
                result = subprocess.run(
                    ["ffmpeg", "-encoders"], capture_output=True, text=True
                )
                if "h264_videotoolbox" in result.stdout:
                    logger.info(
                        "✅ 检测到 h264_videotoolbox 编码器。启用 macOS GPU 加速。"
                    )
                    return {
                        "codec": "h264_videotoolbox",
                        "preset": "ultrafast", # VideoToolbox没有像x264那样的preset，但保留此字段以保持API一致性
                        "threads": os.cpu_count() or 2,
                        "ffmpeg_params": ["-b:v", "8000k"], # 为macOS编码器设置合理的比特率
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    # Intel Quick Sync Video (Windows/Linux)
    if system in ["Windows", "Linux"]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hwaccels"], capture_output=True, text=True
            )
            if "qsv" in result.stdout:
                logger.info("✅ 检测到 Intel QSV 支持。")
                result = subprocess.run(
                    ["ffmpeg", "-encoders"], capture_output=True, text=True
                )
                if "h264_qsv" in result.stdout:
                    logger.info("✅ 检测到 h264_qsv 编码器。启用 Intel QSV 加速。")
                    return {
                        "codec": "h264_qsv",
                        "preset": "fast",
                        "threads": os.cpu_count() or 2,
                        "ffmpeg_params": ["-load_plugin", "hevc_hw", "-hwaccel", "qsv"],
                    }
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    logger.warning("⚠️ 未检测到可用的 GPU 加速硬件。将回退到 CPU (libx264) 进行编码。")
    return {
        "codec": "libx264",
        "preset": "ultrafast",
        "threads": os.cpu_count() or 2,
        "ffmpeg_params": [],
    }
