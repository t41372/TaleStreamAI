# app/pipeline.py
import asyncio
import concurrent.futures
from typing import Optional

from .config import settings
from .stages import content, storyboard, assets, finalizer
from .logger import log_info, log_error, log_step_start, log_step_complete


class Pipeline:
    """
    异步流水线控制器，负责编排整个视频生成过程。
    """

    def __init__(self, book_id: str, source_file: Optional[str] = None):
        self.book_id = book_id
        self.source_file = source_file
        self.book_path = settings.paths.get_book_path(book_id)

        # 为CPU密集型任务创建一个进程池执行器
        self.process_executor = concurrent.futures.ProcessPoolExecutor()

    async def run(self):
        """按顺序执行流水线的各个阶段"""
        start_time = asyncio.get_event_loop().time()

        # --- 阶段 1: 内容获取 ---
        log_step_start("阶段 1: 内容获取")
        chapters = await content.get_chapters(self.book_id, self.source_file)
        if not chapters:
            log_error("内容获取失败，流水线终止。")
            return
        log_step_complete("阶段 1: 内容获取", details=f"获取到 {len(chapters)} 个章节")

        # --- 阶段 2: 分镜与提示词生成 (并发) ---
        log_step_start("阶段 2: 生成分镜与提示词")
        all_shots = await storyboard.create_storyboard_for_chapters(chapters)
        if not all_shots:
            log_error("分镜生成失败，流水线终止。")
            return
        log_step_complete(
            "阶段 2: 生成分镜与提示词", details=f"共生成 {len(all_shots)} 个分镜"
        )

        # --- 阶段 3: 资产生成 (图片、音频、视频片段) ---
        log_step_start("阶段 3: 并行生成所有资产")
        processed_shots = await assets.generate_all_assets(
            all_shots, self.book_path, self.process_executor
        )
        successful_shots = [shot for shot in processed_shots if not shot.error]
        if not successful_shots:
            log_error("所有资产生成失败，流水线终止。")
            return
        log_step_complete(
            "阶段 3: 并行生成所有资产",
            details=f"成功处理 {len(successful_shots)}/{len(all_shots)} 个镜头",
        )

        # --- 阶段 4: 最终合成 ---
        log_step_start("阶段 4: 合成最终视频")
        await finalizer.merge_video_clips(self.book_id, successful_shots)
        log_step_complete("阶段 4: 合成最终视频")

        end_time = asyncio.get_event_loop().time()
        log_info(f"流水线总耗时: {end_time - start_time:.2f} 秒")

        # 优雅地关闭进程池
        self.process_executor.shutdown()
