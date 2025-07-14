# run.py
import asyncio
import argparse
from pathlib import Path
import os
import sys
import aiohttp
from openai import AsyncOpenAI

from loguru import logger

from app.config import settings
from app.llm_client import test_llm_connections
from app.pipeline import Pipeline
from app.services.image_provider import (
    PollinationsImageGenerator,
    OpenAIImageGenerator,
    FallbackImageGenerator,
)
from app.services.audio_provider import EdgeTTSAudioGenerator


async def main():
    """主异步函数，协调整个工作流"""
    # --- Loguru Configuration ---
    logger.remove()
    log_level = "DEBUG" if os.getenv("VERBOSE_LOGGING", "true").lower() == "true" else "INFO"
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        colorize=True,
    )
    # --- End Loguru Configuration ---

    parser = argparse.ArgumentParser(
        description="TaleStreamAI - 自动化小说转视频工作流"
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=settings.book_source,
        help=f"书籍来源：可以是起点ID或本地.txt文件路径 (默认为: {settings.book_source})",
    )
    parser.add_argument(
        "--book_id",
        default=settings.custom_book_id,
        help="为本地文件指定一个自定义的书籍ID (默认为文件名)",
    )
    parser.add_argument(
        "--test-connections",
        action="store_true",
        help="仅运行API连接测试后退出",
    )

    args = parser.parse_args()

    if args.test_connections:
        await test_llm_connections()
        return

    # 使用命令行参数来确定 book_id
    final_book_id = args.book_id
    if not final_book_id:
        if args.source.endswith(".txt"):
            final_book_id = Path(args.source).stem
        else:
            final_book_id = args.source

    logger.info(f"🚀 工作流启动，书籍ID: {final_book_id}")

    # 使用依赖注入模式创建服务实例
    async with aiohttp.ClientSession() as session:
        # --- Image generators & fallback chain ---
        openai_client = AsyncOpenAI(
            api_key=settings.openai_image_api_key,
            base_url=settings.openai_image_api_url,
            timeout=settings.storyboard_llm.timeout,
        )

        # 创建各自带有专用并发控制的生成器
        primary_gen = OpenAIImageGenerator(
            client=openai_client,
            model=settings.openai_image_model,
            # 不传递semaphore，让构造器使用专用配置
        )

        secondary_gen = PollinationsImageGenerator(
            session=session,
            # 不传递max_concurrent，让构造器使用专用配置
        )

        image_generator = FallbackImageGenerator(primary_gen, secondary_gen)
        audio_generator = EdgeTTSAudioGenerator()

        # 初始化并运行流水线，注入所有依赖
        pipeline = Pipeline(
            book_id=final_book_id,
            source_file=args.source if args.source.endswith(".txt") else None,
            session=session,
            image_generator=image_generator,
            audio_generator=audio_generator,
        )

        try:
            await pipeline.run()
        except Exception as e:
            logger.exception(f"工作流执行过程中发生未捕获的严重错误: {e}")
        else:
            # This 'else' block only runs if the 'try' block completes without any exceptions
            logger.info("🎉 工作流全部阶段成功完成！")


if __name__ == "__main__":
    asyncio.run(main())
