# app/stages/assets.py
import io
import os
import asyncio
import tempfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

# v2.x: Import specific classes, avoid moviepy.editor
from moviepy.video.VideoClip import ImageClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from PIL import Image  # Still needed for image processing in _generate_image_asset
from loguru import logger

from ..config import settings
from ..models import Shot
from ..services.image_provider import PollinationsImageGenerator
from ..services.audio_provider import EdgeTTSAudioGenerator
from ..ffmpeg_utils import get_ffmpeg_gpu_params

# Service providers will be injected via dependency injection


# --- Image Generation (Now uses the service provider) ---
async def _generate_image_asset(shot: Shot, book_path: Path, image_generator: PollinationsImageGenerator) -> Shot:
    """生成单个镜头的图片资产"""
    if shot.error:
        return shot

    image_dir = book_path / "images" / str(shot.chapter_index)
    image_dir.mkdir(parents=True, exist_ok=True)
    shot.image_path = image_dir / f"{shot.shot_id}.jpg"

    if shot.image_path.exists():
        logger.debug(f"Image already exists for shot {shot.get_full_id()}, skipping generation.")
        return shot

    logger.debug(f"Generating image for shot {shot.get_full_id()}...")
    try:
        if not shot.image_prompt:
            raise ValueError("Image prompt is missing.")

        image_data = await image_generator.generate(shot.image_prompt)

        with Image.open(io.BytesIO(image_data)) as img:
            img.convert("RGB").save(shot.image_path, "JPEG", quality=95)
    except Exception as e:
        shot.error = f"Image generation failed: {e}"
        logger.error(f"Shot {shot.get_full_id()} failed during image generation: {e}")

    return shot


# --- Audio Generation (Now uses the service provider) ---
async def _generate_audio_asset(shot: Shot, book_path: Path, audio_generator: EdgeTTSAudioGenerator) -> Shot:
    """生成单个镜头的音频和SRT字幕资产"""
    if shot.error:
        return shot

    audio_dir = book_path / "audio" / str(shot.chapter_index)
    audio_dir.mkdir(parents=True, exist_ok=True)
    shot.audio_path = audio_dir / f"{shot.shot_id}.mp3"
    shot.srt_path = shot.audio_path.with_suffix(".srt")

    if shot.audio_path.exists() and shot.srt_path.exists() and shot.srt_path.stat().st_size > 0:
        logger.debug(f"Audio and SRT already exist for shot {shot.get_full_id()}, skipping generation.")
        return shot

    logger.debug(f"Generating audio and SRT for shot {shot.get_full_id()}...")
    try:
        if not shot.original_text:
            raise ValueError("Original text for audio is missing.")

        # 调用新版方法，解包返回的元组
        audio_data, srt_content = await audio_generator.generate(
            shot.original_text, settings.edge_tts_voice
        )

        shot.audio_path.write_bytes(audio_data)
        
        # 写入真实的SRT内容
        if srt_content:
            shot.srt_path.write_text(srt_content, encoding="utf-8")
            logger.debug(f"SRT file generated for shot {shot.get_full_id()}.")
        else:
            # 作为后备，如果没生成字幕，也创建一个空文件，避免后续流程出错
            shot.srt_path.write_text("", encoding="utf-8")
            logger.warning(f"No SRT content generated for shot {shot.get_full_id()}.")

    except Exception as e:
        shot.error = f"Audio/SRT generation failed: {e}"
        logger.error(f"Shot {shot.get_full_id()} failed during audio/SRT generation: {e}")

    return shot


# --- Video Clip Generation (CPU-Bound) ---
def _generate_video_clip_asset_sync(shot: Shot, book_path: Path) -> Shot:
    """
    [同步函数] 为单个镜头合成视频片段。
    这个函数将在一个单独的进程中运行，以避免阻塞事件循环。
    """
    # v2.x: No longer need monkey-patch, MoviePy 2.x natively supports Pillow 10+

    if shot.error or not shot.image_path or not shot.audio_path:
        logger.warning(
            f"Skipping video clip for shot {shot.get_full_id()} due to previous errors or missing assets."
        )
        return shot

    video_dir = book_path / "video" / str(shot.chapter_index)
    video_dir.mkdir(parents=True, exist_ok=True)
    shot.video_clip_path = video_dir / f"{shot.shot_id}.mp4"

    if shot.video_clip_path.exists():
        logger.debug(f"Video clip exists for shot {shot.get_full_id()}, skipping.")
        return shot

    logger.debug(f"Synthesizing video for shot {shot.get_full_id()}...")
    try:
        # Validate assets exist before processing
        if not shot.audio_path.exists() or not shot.image_path.exists():
            raise FileNotFoundError(f"Missing audio or image file for shot {shot.get_full_id()}")

        # 获取动态的、硬件加速的ffmpeg参数
        encoding_params = get_ffmpeg_gpu_params()
        logger.debug(f"Using encoding params: {encoding_params}")

        # Use compatible API while removing monkey-patch
        with AudioFileClip(str(shot.audio_path)) as audio_clip:
            final_size = (settings.video_width, settings.video_height)

            # Create image clip with duration matching audio
            image_clip: ImageClip = ImageClip(str(shot.image_path)).with_duration(
                audio_clip.duration
            )

            # Simple zoom-in effect (Ken Burns) with method chaining where possible
            # Resize image to be slightly larger than final dimensions for zoom
            zoomed_image: ImageClip = image_clip.resized(
                height=int(final_size[1] * 1.15)
            ).with_position(("center", "center"))

            # Animate the zoom over the duration of the clip
            final_video = zoomed_image.resized(
                lambda t: 1 + 0.15 * (1 - t / audio_clip.duration)
            ).with_position(("center", "center"))

            # Compose video with audio
            final_clip = CompositeVideoClip([final_video], size=final_size)
            final_clip = final_clip.with_audio(audio_clip)

            # 使用 NamedTemporaryFile 来安全地管理临时音频文件
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp_audio:
                final_clip.write_videofile(
                    str(shot.video_clip_path),
                    fps=24,
                    codec=encoding_params["codec"],
                    threads=encoding_params["threads"],
                    preset=encoding_params["preset"],
                    logger=None,
                    # 将额外参数传递给ffmpeg
                    ffmpeg_params=encoding_params["ffmpeg_params"],
                    # 关键：指定临时音频文件路径，防止污染根目录
                    temp_audiofile=tmp_audio.name,
                )
    except Exception as e:
        shot.error = f"Video synthesis failed: {e}"
        logger.exception(f"Shot {shot.get_full_id()} failed during video synthesis")

    return shot


# --- Main Orchestrator ---
async def generate_all_assets(
    shots: list[Shot],
    book_path: Path,
    image_generator: PollinationsImageGenerator,
    audio_generator: EdgeTTSAudioGenerator,
    process_executor: ProcessPoolExecutor,
) -> list[Shot]:
    """
    资产生成阶段的主函数。
    并发生成所有镜头的图片和音频，然后将视频合成任务分派到进程池。
    """
    # 步骤 1: 并发生成图片资产
    logger.info(
        f"Starting parallel generation of image assets for {len(shots)} shots..."
    )
    image_tasks = [
        _generate_image_asset(shot, book_path, image_generator) for shot in shots
    ]
    # +++ 捕获更新后的 Shot 对象 +++
    shots_with_images = await asyncio.gather(*image_tasks)

    # 步骤 2: 基于已更新的Shot列表，并发生成音频资产
    logger.info(
        f"Starting parallel generation of audio assets for {len(shots_with_images)} shots..."
    )
    # +++ 使用上一步的结果来创建新任务 +++
    shots_to_process_audio = [s for s in shots_with_images if not s.error]
    audio_tasks = [
        _generate_audio_asset(shot, book_path, audio_generator)
        for shot in shots_to_process_audio
    ]
    # +++ 再次捕获更新后的 Shot 对象 +++
    shots_with_audio = await asyncio.gather(*audio_tasks)
    
    # 合并成功和失败的结果，保持列表完整性
    processed_io_shots = {s.get_full_id(): s for s in shots_with_audio}
    all_shots_after_io = [
        processed_io_shots.get(s.get_full_id(), s) for s in shots_with_images
    ]

    # 步骤 3: 将CPU密集型任务（视频合成）提交到进程池
    logger.info("Scheduling CPU-bound assets (video clips) to process pool...")
    loop = asyncio.get_event_loop()
    cpu_tasks = []
    
    # +++ 使用经过IO处理后、状态完全更新的 Shot 列表 +++
    for shot in all_shots_after_io:
        # run_in_executor 在一个指定的执行器（这里是进程池）中运行函数
        task = loop.run_in_executor(
            process_executor,
            _generate_video_clip_asset_sync,  # 必须是同步函数
            shot,
            book_path,
        )
        cpu_tasks.append(task)

    # 等待所有视频片段合成任务完成
    final_processed_shots = await asyncio.gather(*cpu_tasks)

    return list(final_processed_shots)
