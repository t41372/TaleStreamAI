# app/stages/assets.py
import io
import os
import asyncio
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import aiohttp

import edge_tts
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
from PIL import Image

from ..config import settings
from loguru import logger
from ..models import Shot
from ..cache import image_cache, audio_cache


# --- Image Generation ---
@image_cache
async def _fetch_image(prompt: str) -> bytes:
    """使用 aiohttp 异步从 Flux API 获取图片"""
    # Pollinations.ai is a free service, but we can use a more specific model if needed
    # encoded_prompt = urllib.parse.quote(prompt)
    # url = (f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    #        f"?width={settings.image_width}&height={settings.image_height}&nologo=true")

    # Using a different free API that seems more stable for direct use
    url = "https://flux.fails.network/image/generator"
    payload = {
        "prompt": prompt,
        "width": settings.image_width,
        "height": settings.image_height,
        "style": "anime",  # Corresponds to our desired style
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=300) as response:
                response.raise_for_status()
                return await response.read()
        except aiohttp.ClientError as e:
            logger.error(
                f"Image generation API request failed for prompt '{prompt[:30]}...': {e}"
            )
            raise


async def _generate_image_asset(shot: Shot, book_path: Path) -> Shot:
    """生成单个镜头的图片资产"""
    if shot.error:
        return shot

    image_dir = book_path / "images" / str(shot.chapter_index)
    image_dir.mkdir(parents=True, exist_ok=True)
    shot.image_path = image_dir / f"{shot.shot_id}.jpg"

    if shot.image_path.exists():
        logger.debug(
            f"Image already exists for shot {shot.get_full_id()}, skipping generation."
        )
        return shot

    logger.debug(f"Generating image for shot {shot.get_full_id()}...")
    try:
        if not shot.image_prompt:
            raise ValueError("Image prompt is missing.")
        image_data = await _fetch_image(shot.image_prompt)
        with Image.open(io.BytesIO(image_data)) as img:
            img.convert("RGB").save(shot.image_path, "JPEG", quality=95)
    except Exception as e:
        shot.error = f"Image generation failed: {e}"
        logger.error(f"Shot {shot.get_full_id()} failed during image generation: {e}")

    return shot


# --- Audio Generation ---
@audio_cache
async def _fetch_audio(text: str, voice: str) -> bytes:
    """使用 edge-tts 异步获取音频"""
    try:
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        logger.error(f"Edge-TTS generation failed for text '{text[:30]}...': {e}")
        raise


async def _generate_audio_asset(shot: Shot, book_path: Path) -> Shot:
    """生成单个镜头的音频资产"""
    if shot.error:
        return shot

    audio_dir = book_path / "audio" / str(shot.chapter_index)
    audio_dir.mkdir(parents=True, exist_ok=True)
    shot.audio_path = audio_dir / f"{shot.shot_id}.mp3"
    shot.srt_path = shot.audio_path.with_suffix(".srt")  # srt logic to be added later

    if shot.audio_path.exists():
        logger.debug(
            f"Audio already exists for shot {shot.get_full_id()}, skipping generation."
        )
        return shot

    logger.debug(f"Generating audio for shot {shot.get_full_id()}...")
    try:
        if not shot.original_text:
            raise ValueError("Original text for audio is missing.")
        audio_data = await _fetch_audio(shot.original_text, settings.edge_tts_voice)
        shot.audio_path.write_bytes(audio_data)
        # Placeholder for srt generation
        shot.srt_path.write_text("")
    except Exception as e:
        shot.error = f"Audio generation failed: {e}"
        logger.error(f"Shot {shot.get_full_id()} failed during audio generation: {e}")

    return shot


# --- Video Clip Generation (CPU-Bound) ---
def _generate_video_clip_asset_sync(shot: Shot, book_path: Path) -> Shot:
    """
    [同步函数] 为单个镜头合成视频片段。
    这个函数将在一个单独的进程中运行，以避免阻塞事件循环。
    """
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
            raise FileNotFoundError(
                f"Missing audio or image file for shot {shot.get_full_id()}"
            )

        with (
            AudioFileClip(str(shot.audio_path)) as audio_clip,
            ImageClip(str(shot.image_path)).set_duration(
                audio_clip.duration
            ) as image_clip,
        ):
            # Simple zoom-in effect (Ken Burns)
            final_size = (settings.video_width, settings.video_height)

            # Resize image to be slightly larger than final dimensions for zoom
            zoomed_image = image_clip.resize(
                height=int(final_size[1] * 1.15)
            ).set_position(("center", "center"))

            # Animate the zoom over the duration of the clip
            final_video = zoomed_image.resize(
                lambda t: 1 + 0.15 * (1 - t / audio_clip.duration)
            )
            final_video = final_video.set_position(("center", "center"))

            final_clip = CompositeVideoClip([final_video], size=final_size)
            final_clip = final_clip.set_audio(audio_clip)

            final_clip.write_videofile(
                str(shot.video_clip_path),
                fps=24,
                codec="libx264",  # Use a more compatible encoder
                threads=os.cpu_count() or 2,
                logger=None,
                preset="ultrafast",  # Prioritize speed over quality for clip generation
            )
    except Exception as e:
        shot.error = f"Video synthesis failed: {e}"
        logger.exception(
            f"Shot {shot.get_full_id()} failed during video synthesis"
        )

    return shot


# --- Main Orchestrator ---
async def generate_all_assets(
    shots: list[Shot], book_path: Path, process_executor: ProcessPoolExecutor
) -> list[Shot]:
    """
    资产生成阶段的主函数。
    并发生成所有镜头的图片和音频，然后将视频合成任务分派到进程池。
    """
    # 步骤 1: 并发生成所有I/O密集型资产（图片和音频）
    logger.info(
        f"Starting parallel generation of I/O-bound assets (image, audio) for {len(shots)} shots..."
    )

    # We create image and audio tasks separately to handle potential errors gracefully
    image_tasks = [_generate_image_asset(shot, book_path) for shot in shots]
    audio_tasks = [_generate_audio_asset(shot, book_path) for shot in shots]

    # Await both sets of I/O tasks
    await asyncio.gather(*image_tasks, *audio_tasks)

    # 步骤 2: 将CPU密集型任务（视频合成）提交到进程池
    logger.info("Scheduling CPU-bound assets (video clips) to process pool...")
    loop = asyncio.get_event_loop()
    cpu_tasks = []
    for shot in shots:
        # run_in_executor 在一个指定的执行器（这里是进程池）中运行函数
        task = loop.run_in_executor(
            process_executor,
            _generate_video_clip_asset_sync,  # 必须是同步函数
            shot,
            book_path,
        )
        cpu_tasks.append(task)

    # 等待所有视频片段合成任务完成
    processed_shots = await asyncio.gather(*cpu_tasks)

    return list(processed_shots)
