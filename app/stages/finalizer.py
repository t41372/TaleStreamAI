# app/stages/finalizer.py
import asyncio
from datetime import timedelta
from pathlib import Path

import srt
from moviepy.editor import VideoFileClip

from ..config import settings
from ..logger import log_info, log_error, log_debug, log_warning
from ..models import Shot


async def _merge_srt_files(sorted_shots: list[Shot], output_srt_path: Path):
    """异步合并所有SRT文件，并校正时间戳。"""
    log_info("🚀 开始合并SRT字幕文件...")
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
            log_warning(
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
                log_debug(
                    f"已处理字幕 {shot.srt_path.name}, 添加了 {len(subs)} 条字幕。"
                )
            except Exception as e:
                log_error(f"处理字幕文件 {shot.srt_path.name} 失败: {e}")

        cumulative_duration += duration

    if final_subtitles:
        final_srt_content = srt.compose(final_subtitles)
        output_srt_path.write_text(final_srt_content, encoding="utf-8")
        log_info(f"✅ 字幕文件合并成功，保存至: {output_srt_path}")
    else:
        log_info("没有找到可合并的字幕文件。")


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
        log_error("没有有效的视频片段可供合并。")
        return

    log_info(f"准备合并 {len(valid_clips)} 个视频片段...")

    # 创建 ffmpeg 的 concat 文件列表
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for clip_path in valid_clips:
            # ffmpeg concat demuxer 需要对特殊字符进行转义
            # 但更安全的方式是使用相对路径并在安全的工作目录中运行
            safe_path = clip_path.resolve().as_posix()
            f.write(f"file '{safe_path}'\\n")

    # 合并字幕
    await _merge_srt_files(sorted_shots, final_srt_path)

    # 异步执行 ffmpeg 命令
    command = [
        "ffmpeg",
        "-y",  # 覆盖输出文件
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",  # 直接复制流，速度最快
        str(final_video_path),
    ]

    log_info(f"执行ffmpeg命令: {' '.join(command)}")
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        log_info(f"🎉 最终视频合成成功! 文件保存在: {final_video_path}")
    else:
        log_error(f"ffmpeg 合并失败。返回码: {process.returncode}")
        log_error(f"ffmpeg STDOUT:\\n{stdout.decode('utf-8', errors='ignore')}")
        log_error(f"ffmpeg STDERR:\\n{stderr.decode('utf-8', errors='ignore')}")

    # 清理临时的 concat 文件
    concat_list_path.unlink(missing_ok=True)
