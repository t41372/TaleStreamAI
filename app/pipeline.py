# app/pipeline.py
import asyncio
import concurrent.futures
import pickle
from typing import Optional
import aiohttp

from .config import settings
from .stages import storyboard, assets, finalizer
from .stages.content import load_and_chunk_content # 直接导入新函数
from .services.image_provider import PollinationsImageGenerator
from .services.audio_provider import EdgeTTSAudioGenerator
from loguru import logger


class Pipeline:
    """
    异步流水线控制器，负责编排整个视频生成过程。
    """

    def __init__(
        self,
        book_id: str,
        source_file: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
        image_generator: Optional[PollinationsImageGenerator] = None,
        audio_generator: Optional[EdgeTTSAudioGenerator] = None,
    ):
        self.book_id = book_id
        self.source_file = source_file
        self.book_path = settings.paths.get_book_path(book_id)
        self.state_file_path = self.book_path / "progress.pkl"
        
        # 依赖注入：接受外部传入的服务实例
        self.session = session
        self.image_generator = image_generator
        self.audio_generator = audio_generator

        # 为CPU密集型任务创建一个进程池执行器
        self.process_executor = concurrent.futures.ProcessPoolExecutor()

    def _save_state(self, shots: list):
        """将当前的所有Shots状态序列化到文件。"""
        try:
            with open(self.state_file_path, "wb") as f:
                pickle.dump(shots, f)
            logger.info(f"💾 流水线状态已保存至: {self.state_file_path}")
        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    def _load_state(self) -> Optional[list]:
        """从文件加载并反序列化Shots状态。"""
        if not self.state_file_path.exists():
            return None
        try:
            with open(self.state_file_path, "rb") as f:
                shots = pickle.load(f)
            logger.info(f"✅ 成功从 {self.state_file_path} 加载状态，即将恢复运行...")
            return shots
        except (pickle.UnpicklingError, EOFError, FileNotFoundError) as e:
            logger.warning(f"无法加载状态文件 (可能已损坏或为空)，将重新开始: {e}")
            self.state_file_path.unlink(missing_ok=True) # 删除损坏的文件
            return None

    def _reset_failed_assets(self, shots: list) -> list:
        """重置之前失败的资产状态，以便重试。"""
        logger.info("正在检查并重置失败的资产状态以便重试...")
        reset_count = 0
        for shot in shots:
            if shot.error:
                logger.debug(f"重置分镜 {shot.get_full_id()} 的失败状态 (原因: {shot.error})")
                shot.error = None
                # 清除所有资产路径，以便重新生成
                shot.image_path = None
                shot.audio_path = None
                shot.video_clip_path = None
                shot.srt_path = None
                reset_count += 1
        if reset_count > 0:
            logger.info(f"已重置 {reset_count} 个失败分镜的状态，将在本次运行中重试。")
        else:
            logger.info("未发现失败的资产，所有内容均已是最新状态。")
        return shots
            
    def _cleanup_state_file(self):
        """在流水线成功完成后清理状态文件。"""
        self.state_file_path.unlink(missing_ok=True)
        logger.info("🧹 状态文件已清理。")

    async def run(self):
        """按顺序执行流水线的各个阶段"""
        start_time = asyncio.get_event_loop().time()

        # --- 尝试加载状态，实现断点续传 ---
        processed_shots = self._load_state()

        if processed_shots is None:
            logger.info("🔄 未找到有效状态文件，开始全新运行...")

            # --- 阶段 1: 内容获取与分块 ---
            logger.info("🚀 开始执行: 阶段 1: 内容加载与分块")
            # 调用重构后的同步函数
            text_chunks = load_and_chunk_content(self.book_id, self.source_file)
            if not text_chunks:
                logger.error("内容加载或分块失败，流水线终止。")
                return
            logger.info(f"✅ 完成: 阶段 1 | 内容被加载并分割为 {len(text_chunks)} 个文本块")

            # --- 阶段 2: 分镜与提示词生成 (并发) ---
            logger.info("🚀 开始执行: 阶段 2: 生成分镜与提示词")
            # 调用新的分镜生成函数，传入 text_chunks
            all_shots = await storyboard.create_storyboard_from_chunks(text_chunks, self.book_path)
            if not all_shots:
                logger.error("分镜生成失败，流水线终止。")
                return
            logger.info(
                f"✅ 完成: 阶段 2: 生成分镜与提示词 | 共生成 {len(all_shots)} 个分镜"
            )
            
            # 第一个检查点：在LLM密集型任务后保存状态
            self._save_state(all_shots)
            processed_shots = all_shots
        else:
            logger.info(f"✅ 成功恢复运行，已加载 {len(processed_shots)} 个镜头的先前状态。")
            # 在恢复后，重置任何之前失败的资产
            processed_shots = self._reset_failed_assets(processed_shots)

        # --- 阶段 3: 资产生成 (图片、音频、视频片段) ---
        logger.info("🚀 开始执行: 阶段 3: 并行生成所有资产")
        # 传递已处理或已加载的shots和注入的服务
        shots_after_assets = await assets.generate_all_assets(
            processed_shots, self.book_path, self.image_generator, self.audio_generator, self.process_executor
        )
        # 第二个检查点：在媒体资产生成后更新状态
        self._save_state(shots_after_assets)
        
        successful_shots = [shot for shot in shots_after_assets if not shot.error]
        if not successful_shots:
            logger.error("所有资产生成失败，流水线终止。")
            return
        logger.info(
            f"✅ 完成: 阶段 3: 并行生成所有资产 | 成功处理 {len(successful_shots)}/{len(shots_after_assets)} 个镜头"
        )

        # --- 阶段 4: 最终合成 ---
        logger.info("🚀 开始执行: 阶段 4: 合成最终视频")
        await finalizer.merge_video_clips(self.book_id, successful_shots)
        logger.info("✅ 完成: 阶段 4: 合成最终视频")

        end_time = asyncio.get_event_loop().time()
        logger.info(f"流水线总耗时: {end_time - start_time:.2f} 秒")

        # --- 清理 ---
        self._cleanup_state_file()
        # 优雅地关闭进程池
        self.process_executor.shutdown()
