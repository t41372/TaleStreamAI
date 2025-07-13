# run.py
import asyncio
import argparse
from pathlib import Path

from app.config import settings
from app.logger import log_info, log_error
from app.llm_client import test_llm_connections
from app.pipeline import Pipeline


async def main():
    """主异步函数，协调整个工作流"""
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

    # 更新配置以反映命令行参数
    # (dataclasses 是不可变的, 所以我们创建一个新的)
    # 技巧：使用 object.__setattr__ 来绕过 frozen=True 的限制进行修改
    # 但更清晰的方式是在启动时就决定好配置
    # 这里为了简单，我们假设 settings 已通过 .env 文件配置好，命令行仅用于临时覆盖
    # 实际生产中可能会用更复杂的配置加载逻辑

    # 使用命令行参数来确定 book_id
    final_book_id = args.book_id
    if not final_book_id:
        if args.source.endswith(".txt"):
            final_book_id = Path(args.source).stem
        else:
            final_book_id = args.source

    log_info(f"🚀 工作流启动，书籍ID: {final_book_id}")

    # 初始化并运行流水线
    pipeline = Pipeline(
        book_id=final_book_id,
        source_file=args.source if args.source.endswith(".txt") else None,
    )

    try:
        await pipeline.run()
        log_info("🎉 工作流全部阶段成功完成！")
    except Exception as e:
        log_error(f"工作流执行过程中发生未捕获的严重错误: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
