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

    # 生成的数据
    storyboard_prompt_cn: Optional[str] = None
    storyboard_prompt_en: Optional[str] = None
    image_prompt: Optional[str] = None

    # 生成的资产路径
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