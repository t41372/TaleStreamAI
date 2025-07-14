# app/stages/content.py
from pathlib import Path
from typing import Optional

from loguru import logger

from ..config import settings
from ..models import TextChunk
from ..chunker import chunk_text


def _load_local_content(source_file: str) -> str:
    """从本地TXT文件加载全部内容。"""
    source_path = Path(source_file)
    if not source_path.exists():
        logger.error(f"本地文件不存在: {source_file}")
        # 在健壮的系统中，这里应该抛出异常而不是返回空字符串
        raise FileNotFoundError(f"Source file not found at {source_path.resolve()}")

    logger.info(f"从 {source_path.resolve()} 读取完整文本内容...")
    return source_path.read_text(encoding="utf-8")


# 注意：函数名已更改，以准确反映其新职责和返回值
def load_and_chunk_content(
    book_id: str, source_file: Optional[str] = None
) -> list[TextChunk]:
    """
    内容获取与分块阶段的主函数。

    Args:
        book_id: 书籍的唯一标识符。
        source_file: 本地文本文件的路径。

    Returns:
        一个 TextChunk 对象的列表，代表了分割好的、准备送入下一阶段的文本块。
    """
    # 确保本书的工作目录存在
    book_path = settings.paths.get_book_path(book_id)
    book_path.mkdir(exist_ok=True)

    if source_file:
        logger.info(f"从本地文件加载: {source_file}")
        full_text = _load_local_content(source_file)
    else:
        # 当前重构专注于本地文件。网络逻辑可以作为未来的增强功能。
        # raise NotImplementedError("网络内容获取功能当前未激活。")
        logger.error("未提供源文件，且网络获取功能未激活。")
        return []

    # 委托给重构后的 chunker 模块进行分块
    storyboard_config = settings.storyboard_llm
    logger.info(f"开始使用 {storyboard_config.model} 的 token 限制 ({storyboard_config.max_tokens}) 进行文本分块...")
    # 新的 chunk_text 函数返回我们需要的 List[TextChunk]
    return chunk_text(
        full_text,
        token_limit=storyboard_config.max_tokens,
        # o200k_base 是一个适用于最新模型的通用编码器
        encoding_name="o200k_base",
    )
