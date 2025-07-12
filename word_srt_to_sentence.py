#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
一个用于将逐字SRT字幕合并为句子/短语字幕的CLI工具。
A command-line tool to group word-by-word SRT subtitles into sentence-like lines.
"""

import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import List, Iterator, Optional

# 第三方库导入 (Third-party imports)
try:
    import srt
    import typer
except ImportError:
    # 这是一个友好的提示，告诉用户如果缺少依赖该如何安装。
    # 对于一个要分发的工具来说，这种细节很重要。
    print("错误: 缺少必要的库。请运行 'pip install \"typer[all]\" srt'", file=sys.stderr)
    sys.exit(1)


# ==============================================================================
# 核心逻辑 (Core Logic) - 这部分与之前基本相同
# 我们把它封装得很好，可以被其他任何 Python 脚本导入和使用。
# ==============================================================================

@dataclass
class SubtitleWord:
    """Represents a single word with its timing and content."""
    start: timedelta
    end: timedelta
    content: str


def group_word_by_word_srt(
    words: Iterator[srt.Subtitle],
    max_line_length: int = 30,
    max_pause_seconds: float = 0.5,
) -> List[srt.Subtitle]:
    """
    Groups word-by-word subtitles into sentence-like lines.

    Args:
        words: An iterator of srt.Subtitle objects from a word-by-word SRT.
        max_line_length: The maximum number of characters for a single subtitle line.
        max_pause_seconds: The maximum pause between words to be considered in the same group.

    Returns:
        A list of new srt.Subtitle objects, representing the grouped lines.
    """
    final_subtitles: List[srt.Subtitle] = []
    current_group: List[SubtitleWord] = []
    max_pause_delta = timedelta(seconds=max_pause_seconds)

    def finalize_group(group: List[SubtitleWord]) -> srt.Subtitle:
        start_time = group[0].start
        end_time = group[-1].end
        content = "".join(w.content for w in group)
        return srt.Subtitle(index=0, start=start_time, end=end_time, content=content)

    for word_sub in words:
        current_word = SubtitleWord(
            start=word_sub.start,
            end=word_sub.end,
            content=word_sub.content.strip()
        )

        if not current_word.content:
            continue # 跳过空的字幕条目

        if not current_group:
            current_group.append(current_word)
            continue

        last_word_in_group = current_group[-1]

        pause_duration = current_word.start - last_word_in_group.end
        is_pause_too_long = pause_duration > max_pause_delta

        current_length = sum(len(w.content) for w in current_group)
        projected_length = current_length + len(current_word.content)
        is_length_exceeded = projected_length > max_line_length

        if is_pause_too_long or is_length_exceeded:
            final_subtitles.append(finalize_group(current_group))
            current_group = [current_word]
        else:
            current_group.append(current_word)

    if current_group:
        final_subtitles.append(finalize_group(current_group))
        
    for i, sub in enumerate(final_subtitles, 1):
        sub.index = i
        
    return final_subtitles


# ==============================================================================
# 命令行界面 (Command-Line Interface) - 这是我们新增的部分
# 使用 Typer 来构建。
# ==============================================================================

# 创建一个 Typer 应用实例
app = typer.Typer(
    name="srt-grouper",
    help="一个将逐字SRT字幕合并为可读长句的CLI工具。",
    add_completion=False, # 通常在简单脚本中可以禁用shell补全，让启动更快
)

@app.command()
def main(
    input_file: Path = typer.Argument(
        ...,  # '...' 表示这是一个必需参数
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="输入的逐字 SRT 文件路径。",
    ),
    output_file: Optional[Path] = typer.Option(
        None, # 默认值是 None，表示这是一个可选参数
        "--output", "-o",
        help="输出的文件路径。如果未提供，则在输入文件名后添加 '_grouped'。",
    ),
    max_length: int = typer.Option(
        30, "--max-length", "-l",
        min=1, # Typer 甚至可以帮你做这种范围检查！
        help="每行字幕的最大字符数。",
    ),
    max_pause: float = typer.Option(
        0.4, "--max-pause", "-p",
        min=0.0,
        help="被视为同一句话的最大单词间停顿时长（秒）。",
    ),
):
    """
    读取一个逐字的 SRT 文件，将其合并成句子，并输出到新文件。
    """
    typer.echo(f"🚀 开始处理文件: {input_file}")

    # 决定输出文件名
    if output_file is None:
        # pathlib 的强大之处：可以轻松地操作路径
        output_file = input_file.with_stem(f"{input_file.stem}_grouped")

    # 确保我们不会意外覆盖输入文件
    if input_file.resolve() == output_file.resolve():
        typer.secho("错误: 输出文件不能与输入文件相同。", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        # 读取和解析
        typer.echo("🔍 正在解析字幕...")
        with open(input_file, 'r', encoding='utf-8') as f:
            word_subs_iterator = srt.parse(f.read())

        # 调用核心逻辑
        typer.echo(f"🧠 正在以最大长度 {max_length} 和最大停顿 {max_pause}s 进行分组...")
        grouped_subs = group_word_by_word_srt(
            words=word_subs_iterator,
            max_line_length=max_length,
            max_pause_seconds=max_pause,
        )

        # 生成和写入
        final_srt_string = srt.compose(grouped_subs)
        output_file.write_text(final_srt_string, encoding='utf-8')

        # 使用 typer.secho 来输出带颜色的成功信息
        typer.secho(
            f"\n🎉 处理完成！成功生成 {len(grouped_subs)} 条字幕。",
            fg=typer.colors.GREEN, bold=True
        )
        typer.echo(f"💾 结果已保存至: {output_file}")

    except Exception as e:
        # 统一的错误处理
        typer.secho(f"处理过程中发生严重错误: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


# ==============================================================================
# 脚本入口 (Script Entrypoint)
# =================================================_============================
if __name__ == "__main__":
    # 当脚本被直接运行时，Typer 会接管 sys.argv 并执行上面定义的命令
    app()