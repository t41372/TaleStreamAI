# app/stages/finalizer.py
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

import srt
# v2.x: Import VideoFileClip from specific module, avoid moviepy.editor  
from moviepy.video.io.VideoFileClip import VideoFileClip

from ..config import settings
from loguru import logger
from ..models import Shot


async def _merge_srt_files(sorted_shots: list[Shot], output_srt_path: Path):
    """异步合并所有SRT文件，并校正时间戳。"""
    logger.info("🚀 开始合并SRT字幕文件...")
    final_subtitles = []
    cumulative_duration = timedelta(seconds=0)
    subtitle_index = 1

    for shot in sorted_shots:
        if not shot.video_clip_path or not shot.video_clip_path.exists():
            continue

        # 获取视频时长
        try:
            # 使用 MoviePy 异步获取时长可能复杂，这里暂时用同步IO
            # 在真实的高性能场景，可考虑用 ffprobe 的异步封装
            with VideoFileClip(str(shot.video_clip_path)) as clip:
                duration = timedelta(seconds=clip.duration)
        except Exception as e:
            logger.warning(
                f"无法获取视频时长 {shot.video_clip_path.name}: {e}, 跳过此片段的字幕处理。"
            )
            continue

        # 处理SRT文件
        if (
            shot.srt_path
            and shot.srt_path.exists()
            and shot.srt_path.stat().st_size > 0
        ):
            try:
                content = shot.srt_path.read_text("utf-8")
                subs = list(srt.parse(content))
                for sub in subs:
                    sub.start += cumulative_duration
                    sub.end += cumulative_duration
                    sub.index = subtitle_index
                    final_subtitles.append(sub)
                    subtitle_index += 1
                logger.debug(
                    f"已处理字幕 {shot.srt_path.name}, 添加了 {len(subs)} 条字幕。"
                )
            except Exception as e:
                logger.error(f"处理字幕文件 {shot.srt_path.name} 失败: {e}")

        cumulative_duration += duration

    if final_subtitles:
        final_srt_content = srt.compose(final_subtitles)
        output_srt_path.write_text(final_srt_content, encoding="utf-8")
        logger.info(f"✅ 字幕文件合并成功，保存至: {output_srt_path}")
    else:
        logger.info("没有找到可合并的字幕文件。")


async def _post_process_subtitles(book_path: Path, merged_srt: Path) -> Path:
    """
    ① 调用 restore_punct.py   →  merged_srt.punct.srt
    ② 调用 merge_srt.py       →  merged_srt.sentence.srt
    ③ 返回句级 SRT 的路径
    所有中间文件就地保留。
    """
    full_txt = book_path / "full_text.txt"
    if not full_txt.exists():
        logger.error("full_text.txt 不存在，无法恢复标点。")
        return merged_srt  # 回退到原始字幕

    # ------- 1. restore_punct.py -------
    cmd_restore = [
        sys.executable, "-m", "app.restore_punct",
        str(merged_srt),
        str(full_txt)
    ]
    logger.info("Running restore_punct.py …")
    proc = await asyncio.create_subprocess_exec(
        *cmd_restore, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    logger.debug(out.decode())
    if proc.returncode not in (0, 100):  # 100 == partial success
        logger.error(f"restore_punct failed ({proc.returncode}). Stderr:\n{err.decode()}")
        return merged_srt
    punct_srt = merged_srt.with_suffix(".punct.srt")

    # ------- 2. merge_srt.py -------
    cmd_merge = [
        sys.executable, "-m", "app.merge_srt",
        str(punct_srt)
    ]
    logger.info("Running merge_srt.py …")
    proc = await asyncio.create_subprocess_exec(
        *cmd_merge, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    logger.debug(out.decode())
    if proc.returncode != 0:
        logger.error(f"merge_srt failed ({proc.returncode}). Stderr:\n{err.decode()}")
        return punct_srt
    sentence_srt = punct_srt.with_suffix(".sentence.srt")
    return sentence_srt


async def merge_video_clips(book_id: str, shots: list[Shot]):
    """
    使用ffmpeg将所有视频片段合并成最终的视频文件。
    """
    book_path = settings.paths.get_book_path(book_id)
    final_video_path = book_path / f"{book_id}.mp4"
    final_srt_path = book_path / f"{book_id}.srt"
    concat_list_path = book_path / "concat_list.txt"

    # 确保镜头按章节和ID排序
    sorted_shots = sorted(shots, key=lambda s: (s.chapter_index, s.shot_id))

    valid_clips = [
        shot.video_clip_path
        for shot in sorted_shots
        if shot.video_clip_path and shot.video_clip_path.exists()
    ]

    if not valid_clips:
        logger.error("没有有效的视频片段可供合并。")
        return

    logger.info(f"准备合并 {len(valid_clips)} 个视频片段...")

    # 创建 ffmpeg 的 concat 文件列表
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for clip_path in valid_clips:
            # ffmpeg concat demuxer 需要对特殊字符进行转义
            # 但更安全的方式是使用相对路径并在安全的工作目录中运行
            safe_path = clip_path.resolve().as_posix()
            f.write(f"file '{safe_path}'\n")

    # 1) 合并 word‑level 字幕
    await _merge_srt_files(sorted_shots, final_srt_path)

    # 2) 恢复标点并句级合并
    sentence_srt_path = await _post_process_subtitles(book_path, final_srt_path)

    # 3) 备用：如果出错仍使用最初的 word‑level SRT
    if not sentence_srt_path.exists():
        logger.warning("Sentence‑level SRT 生成失败，继续使用合并后的原始 SRT。")
        sentence_srt_path = final_srt_path

    # ---------- Step A  Concatenate video streams ----------
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_path),
        "-c", "copy",
        str(book_path / "intermediate.mp4"),
    ]
    logger.info("FFmpeg concat …")
    proc1 = await asyncio.create_subprocess_exec(
        *concat_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err1 = await proc1.communicate()
    if proc1.returncode != 0:
        logger.error(f"Concat failed:\n{err1.decode()}")
        return

    # ---------- Step B  Burn subtitles with style ----------
    # ASS/SSA style: Alignment=2 (bottom‑centre) + margin, outline, shadow etc.
    style = (
        "fontname=SourceHanSansSC,fontsize=42,"
        "PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=1,Outline=2,Shadow=0,"
        "Alignment=2,MarginV=80"
    )
    burn_cmd = [
        "ffmpeg", "-y",
        "-i", str(book_path / "intermediate.mp4"),
        "-vf", f"subtitles='{sentence_srt_path.as_posix()}':force_style='{style}'",
        "-c:a", "copy",       # don't re‑encode audio
        str(final_video_path),
    ]
    logger.info("FFmpeg burn‑in subtitles …")
    proc2 = await asyncio.create_subprocess_exec(
        *burn_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, err2 = await proc2.communicate()
    if proc2.returncode == 0:
        logger.info(f"🎉 视频已生成并烧录字幕: {final_video_path}")
    else:
        logger.error(f"Burn‑in failed:\n{err2.decode()}")

    # 清理临时的 concat 文件
    concat_list_path.unlink(missing_ok=True)
