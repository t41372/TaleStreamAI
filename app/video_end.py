import os
import subprocess
import srt
from moviepy.editor import VideoFileClip
from datetime import timedelta
from app.logger import log_info, log_warning, log_error, log_debug


def save_output_video(book_id):
    # 使用os.path.join合并路径
    video_dir = os.path.join(os.getcwd(), "data", "book", str(book_id), "video")
    # 设置最终保存位置
    output_file = os.path.join(
        os.getcwd(), "data", "book", str(book_id), str(book_id) + ".mp4"
    )
    output_srt_file = os.path.join(
        os.getcwd(), "data", "book", str(book_id), f"{book_id}.srt"
    )  # 新增
    # 递归遍历这个目录下的所有视频
    video_paths = []
    for root, dirs, files in os.walk(video_dir):
        for file in files:
            if file.endswith(".mp4"):
                # 使用os.path.join合并完整路径
                video_paths.append(os.path.join(root, file))

    # 对视频路径进行排序
    def sort_key(path):
        # 从路径中提取文件夹编号和文件编号
        parts = path.replace("\\", "/").split("/")
        folder_num = int(parts[-2])  # 倒数第二个部分是文件夹编号
        file_num = int(
            parts[-1].split(".")[0]
        )  # 最后一个部分是文件名，去掉.mp4后转为数字
        return (folder_num, file_num)

    video_paths.sort(key=sort_key)

    # 新增：调用字幕合并函数
    merge_srt_files(video_paths, output_srt_file)

    # 获取concat_list.txt的完整路径
    concat_list_path = os.path.join(os.getcwd(), "concat_list.txt")

    # 如果文件存在，先删除
    if os.path.exists(concat_list_path):
        os.remove(concat_list_path)

    # 将视频路径写入文件，每行前面加上"file "
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for path in video_paths:
            # 将路径转换为正确的格式：
            # 1. 替换所有反斜杠为正斜杠
            # 2. 在路径两边加上单引号，以处理可能包含空格的路径
            formatted_path = path.replace("\\", "/")
            f.write(f"file '{formatted_path}'\n")
    # 添加内存优化参数
    result = subprocess.call(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat_list.txt",
            "-c",
            "copy",
            "-max_muxing_queue_size",
            "9999",  # 增加复用队列大小
            "-threads",
            "1",  # 减少线程数以降低内存
            output_file,
        ]
    )
    if result == 0:
        print(f"视频合并成功，保存位置: {output_file}")
        # 新增：提示字幕文件位置
        if os.path.exists(output_srt_file):
            print(f"字幕文件生成成功，保存位置: {output_srt_file}")
    else:
        print(f"视频合并失败，错误码: {result}")


def merge_srt_files(video_paths: list[str], output_srt_path: str):
    """
    合并多个 SRT 文件，并根据视频时长调整时间码。

    Args:
        video_paths (list[str]): 已排序的视频文件路径列表。
        output_srt_path (str): 最终合并的 SRT 文件输出路径。
    """
    log_info("🚀 开始合并SRT字幕文件...")
    final_subtitles = []
    cumulative_duration = timedelta(seconds=0)
    subtitle_index = 1

    for video_path in video_paths:
        srt_path = os.path.splitext(video_path)[0] + ".srt"

        if not os.path.exists(srt_path):
            log_warning(f"字幕文件未找到，跳过: {srt_path}")
            # 即使没有字幕，也要加上视频时长
            try:
                with VideoFileClip(video_path) as clip:
                    cumulative_duration += timedelta(seconds=clip.duration)
            except Exception as e:
                log_error(f"获取视频 {video_path} 时长失败: {e}")
            continue

        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                subs = list(srt.parse(f.read()))

            for sub in subs:
                # 调整时间码
                sub.start += cumulative_duration
                sub.end += cumulative_duration
                sub.index = subtitle_index
                final_subtitles.append(sub)
                subtitle_index += 1

            log_debug(
                f"已处理字幕文件: {os.path.basename(srt_path)}, 添加了 {len(subs)} 条字幕。"
            )

            # 获取视频时长并累加
            with VideoFileClip(video_path) as clip:
                cumulative_duration += timedelta(seconds=clip.duration)

        except Exception as e:
            log_error(f"处理字幕文件 {srt_path} 失败: {e}")
            # 即使失败，也要尝试获取视频时长
            try:
                with VideoFileClip(video_path) as clip:
                    cumulative_duration += timedelta(seconds=clip.duration)
            except Exception as ve:
                log_error(f"获取视频 {video_path} 时长失败: {ve}")

    if final_subtitles:
        final_srt_content = srt.compose(final_subtitles)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(final_srt_content)
        log_info(f"✅ 字幕文件合并成功，保存至: {output_srt_path}")
    else:
        log_info("没有找到可合并的字幕文件。")


if __name__ == "__main__":
    save_output_video("1043294775")
