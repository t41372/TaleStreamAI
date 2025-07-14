# app/config.py
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# 在模块加载时，第一时间加载环境变量
load_dotenv(override=True)


def _get_bool_env(var_name: str, default: bool = False) -> bool:
    """Helper to get boolean value from environment variables."""
    value = os.getenv(var_name, str(default)).lower()
    return value in ("true", "1", "t", "yes", "y")


def _get_int_env(var_name: str, default: int) -> int:
    """Helper to get integer value from environment variables."""
    value = os.getenv(var_name, str(default))
    return int(value.split("#")[0].strip())


def _get_str_env(var_name: str, default: str) -> str:
    """Helper to get a cleaned string value from environment variables."""
    value = os.getenv(var_name, default)
    return value.split("#")[0].strip()


@dataclass(frozen=True)
class LLMConfig:
    """配置用于 LLM 客户端"""

    api_key: str
    base_url: str
    model: str
    max_tokens: int
    timeout: int = _get_int_env("LLM_TIMEOUT", 120)
    retry_attempts: int = _get_int_env("LLM_RETRY_ATTEMPTS", 3)


@dataclass(frozen=True)
class PathConfig:
    """统一管理项目中的所有路径"""

    data_dir: Path = Path("data")
    cache_dir: Path = data_dir / "cache"
    book_dir: Path = data_dir / "book"

    # 缓存子目录 (用于通用、可丢弃的缓存)
    cache_llm: Path = cache_dir / "llm"
    cache_image: Path = cache_dir / "image"
    cache_audio: Path = cache_dir / "audio"

    def get_book_path(self, book_id: str) -> Path:
        book_path = self.book_dir / book_id
        # 在这里动态创建LLM资产目录
        (book_path / "llm").mkdir(parents=True, exist_ok=True)
        return book_path

    def __post_init__(self):
        """初始化后创建所有必要的目录"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.book_dir.mkdir(parents=True, exist_ok=True)
        self.cache_llm.mkdir(parents=True, exist_ok=True)
        self.cache_image.mkdir(parents=True, exist_ok=True)
        self.cache_audio.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    """全局应用配置"""

    # 书籍配置
    book_source: str = _get_str_env("BOOK_SOURCE", "test_novel.txt")
    custom_book_id: str | None = os.getenv(
        "CUSTOM_BOOK_ID"
    )  # os.getenv is ok for optional values
    cookie: str = _get_str_env("COOKIE", "")  # 用于需要登录才能访问的网站

    # LLM 配置
    storyboard_llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(
            api_key=_get_str_env("STORYBOARD_API_KEY", ""),
            base_url=_get_str_env("STORYBOARD_API_URL", ""),
            model=_get_str_env("STORYBOARD_MODEL", "gemini-1.5-flash-latest"),
            max_tokens=_get_int_env("STORYBOARD_MAX_TOKENS", 8000),
        )
    )
    prompt_llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(
            api_key=_get_str_env("PROMPT_API_KEY", ""),
            base_url=_get_str_env("PROMPT_API_URL", ""),
            model=_get_str_env("PROMPT_MODEL", "deepseek-v2"),
            max_tokens=_get_int_env("PROMPT_MAX_TOKENS", 8000),
        )
    )
    # +++ 新增 JSON 修复器 LLM 配置 +++
    json_repair_llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(
            # 默认情况下，可以复用storyboard的配置，但最好用独立的环境变量
            api_key=_get_str_env("JSON_REPAIR_API_KEY", _get_str_env("STORYBOARD_API_KEY", "")),
            base_url=_get_str_env("JSON_REPAIR_API_URL", _get_str_env("STORYBOARD_API_URL", "")),
            model=_get_str_env("JSON_REPAIR_MODEL", "gemini-1.5-flash-latest"),
            max_tokens=_get_int_env("JSON_REPAIR_MAX_TOKENS", 2048), # 修复任务通常不需要很长的上下文
        )
    )
    # +++ 结束新增部分 +++

    # 图像生成配置
    image_width: int = _get_int_env("IMAGE_WIDTH", 1024)
    image_height: int = _get_int_env("IMAGE_HEIGHT", 1024)
    image_style_prompt: str = _get_str_env(
        "IMAGE_STYLE_PROMPT",
        "cinematic, dramatic lighting, detailed, illustration, anime style, 8k",
    )
    image_threads: int = _get_int_env("IMAGE_THREADS", 1)

    # 音频生成配置
    edge_tts_voice: str = _get_str_env("EDGE_TTS_VOICE", "zh-CN-YunxiNeural")
    audio_threads: int = _get_int_env("AUDIO_THREADS", 5)

    # 视频生成配置
    video_threads: int = _get_int_env("VIDEO_THREADS", 4)
    video_width: int = _get_int_env("VIDEO_WIDTH", 750)
    video_height: int = _get_int_env("VIDEO_HEIGHT", 1280)

    # 性能与流程控制
    max_llm_threads: int = _get_int_env("LLM_THREADS", 3)
    verbose_logging: bool = _get_bool_env("VERBOSE_LOGGING", True)

    # 路径配置
    paths: PathConfig = field(default_factory=PathConfig)

    @property
    def book_id(self) -> str:
        if self.custom_book_id:
            return self.custom_book_id
        if self.book_source.endswith(".txt"):
            return Path(self.book_source).stem
        return self.book_source


# 创建一个全局单例配置对象
settings = Settings()
