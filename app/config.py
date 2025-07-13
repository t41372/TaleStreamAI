# app/config.py
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# 在模块加载时，第一时间加载环境变量
load_dotenv()


def _get_bool_env(var_name: str, default: bool = False) -> bool:
    """Helper to get boolean value from environment variables."""
    value = os.getenv(var_name, str(default)).lower()
    return value in ("true", "1", "t", "yes", "y")


def _get_int_env(var_name: str, default: int) -> int:
    """Helper to get integer value from environment variables."""
    value = os.getenv(var_name, str(default))
    return int(value.split("#")[0].strip())


@dataclass(frozen=True)
class LLMConfig:
    """配置用于 LLM 客户端"""

    api_key: str
    base_url: str
    model: str
    timeout: int = _get_int_env("LLM_TIMEOUT", 120)
    retry_attempts: int = _get_int_env("LLM_RETRY_ATTEMPTS", 3)


@dataclass(frozen=True)
class PathConfig:
    """统一管理项目中的所有路径"""

    data_dir: Path = Path("data")
    cache_dir: Path = data_dir / "cache"
    book_dir: Path = data_dir / "book"

    # 缓存子目录
    cache_llm: Path = cache_dir / "llm"
    cache_image: Path = cache_dir / "image"
    cache_audio: Path = cache_dir / "audio"

    def get_book_path(self, book_id: str) -> Path:
        return self.book_dir / book_id

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
    book_source: str = os.getenv("BOOK_SOURCE", "test_novel.txt")
    custom_book_id: str | None = os.getenv("CUSTOM_BOOK_ID")
    cookie: str = os.getenv("COOKIE", "")  # 用于需要登录才能访问的网站

    # LLM 配置
    storyboard_llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(
            api_key=os.getenv("STORYBOARD_API_KEY", ""),
            base_url=os.getenv("STORYBOARD_API_URL", ""),
            model=os.getenv("STORYBOARD_MODEL", "gemini-1.5-flash-latest"),
        )
    )
    prompt_llm: LLMConfig = field(
        default_factory=lambda: LLMConfig(
            api_key=os.getenv("PROMPT_API_KEY", ""),
            base_url=os.getenv("PROMPT_API_URL", ""),
            model=os.getenv("PROMPT_MODEL", "deepseek-v2"),
        )
    )

    # 图像生成配置
    image_width: int = _get_int_env("IMAGE_WIDTH", 1024)
    image_height: int = _get_int_env("IMAGE_HEIGHT", 1024)
    image_style_prompt: str = os.getenv(
        "IMAGE_STYLE_PROMPT",
        "cinematic, dramatic lighting, detailed, illustration, anime style, 8k",
    )

    # 音频生成配置
    edge_tts_voice: str = os.getenv("EDGE_TTS_VOICE", "zh-CN-YunxiNeural")
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
