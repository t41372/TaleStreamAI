# app/ffmpeg_utils.py
import subprocess
import platform
import os
import functools
from loguru import logger


@functools.lru_cache(maxsize=None)
def _ffmpeg_has_encoder(encoder: str) -> bool:
    """
    缓存化地检查 FFmpeg 是否支持指定的编码器。
    使用 lru_cache 避免重复调用 ffmpeg 进程。
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"], capture_output=True, text=True, check=True
        )
        # 增加空格以确保匹配到完整的编码器名称，避免子字符串问题
        return f" {encoder} " in result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


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
                
                # 优先检查 h264, hevc, prores
                codec_preference = ("h264", "hevc", "prores")
                for codec_prefix in codec_preference:
                    vt_codec = f"{codec_prefix}_videotoolbox"
                    if _ffmpeg_has_encoder(vt_codec):
                        logger.info(f"✅ 检测到 {vt_codec} 编码器。启用 macOS 硬件加速。")
                        
                        # -hwaccel 是解码参数，不适用于此处的编码场景
                        params = []
                        
                        if codec_prefix != "prores":
                            params.extend(["-pix_fmt", "yuv420p"])
                        else:
                            # ProRes 使用不同的像素格式
                            params.extend(["-pix_fmt", "yuv422p10le"])
                            
                        return {
                            "codec": vt_codec,
                            "preset": "ultrafast",  # VideoToolbox 不使用 preset, 但 moviepy 需要一个值
                            "threads": None, # 硬编不依赖此线程数
                            "ffmpeg_params": params,
                        }
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logger.warning(f"在 macOS 上检测 VideoToolbox 时出错: {e}，将回退到 CPU。")
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
