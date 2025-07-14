# app/models.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Shot:
    """
    表示一个独立的分镜（或镜头）。
    这是我们流水线中处理的基本工作单元。
    """

    # 核心内容
    shot_id: int
    chapter_index: int
    original_text: str

    # 生成的数据 (最终使用的提示词)
    image_prompt: Optional[str] = None

    # 生成的资产路径
    storyboard_path: Optional[Path] = None  # 指向分镜脚本JSON文件的路径
    refined_prompt_path: Optional[Path] = None  # 指向优化后的提示词TXT文件的路径
    image_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    srt_path: Optional[Path] = None
    video_clip_path: Optional[Path] = None

    # 状态
    error: Optional[str] = None

    def get_full_id(self) -> str:
        """返回唯一的镜头ID，格式为 '章节-镜头'"""
        return f"{self.chapter_index}-{self.shot_id}"


@dataclass
class Chapter:
    """表示一个完整的章节，包含多个分镜。"""

    index: int
    content: str
    shots: list[Shot] = field(default_factory=list)


@dataclass
class TextChunk:
    """表示一个经过语义分割的文本块，是送入LLM进行处理的基本单元。"""

    chunk_id: int  # 块的顺序ID
    text: str  # 块的文本内容
    char_start_index: int  # 在原始全文中的起始字符索引
    char_end_index: int  # 在原始全文中的结束字符索引

    def __len__(self) -> int:
        return len(self.text)
