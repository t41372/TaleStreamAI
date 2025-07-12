import asyncio
from dotenv import load_dotenv
import os
import json
from tqdm import tqdm
import time
import logging
import threading
from typing import List, Tuple
from .edge_tts_impl import EdgeTTSService, generate_audio_batch

# 设置日志 - 仅记录错误
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv(override=True)

# 线程锁字典，用于防止同时写入同一个JSON文件
json_locks = {}


# 使用Edge-TTS生成音频的异步函数
async def generate_audio_edge_tts(text: str, audio_path: str, subtitle_path: str = None) -> bool:
    """
    使用Edge-TTS生成音频和字幕
    
    Args:
        text: 要转换的文本
        audio_path: 音频文件保存路径
        subtitle_path: 字幕文件保存路径（可选）
        
    Returns:
        bool: 生成是否成功
    """
    try:
        # 获取语音设置
        voice = os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
        rate = os.getenv("EDGE_TTS_RATE", "+0%")
        pitch = os.getenv("EDGE_TTS_PITCH", "+0Hz")
        
        tts_service = EdgeTTSService(voice=voice, rate=rate, pitch=pitch)
        success, _ = await tts_service.generate_audio_with_subtitles(
            text, audio_path, subtitle_path
        )
        
        return success
        
    except Exception as e:
        logger.error(f"Edge-TTS生成音频出错：{str(e)}")
        return False


# 更新JSON文件中的数据
def update_json_with_audio_path(chapter_file_path, item_id, audio_path):
    # 获取或创建该文件的锁
    if chapter_file_path not in json_locks:
        json_locks[chapter_file_path] = threading.Lock()

    # 使用锁确保线程安全
    with json_locks[chapter_file_path]:
        try:
            # 读取JSON文件
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)

            # 查找对应的项并更新
            for item in chapter_data:
                if item["id"] == item_id:
                    item["audio_path"] = audio_path
                    break

            # 写回JSON文件
            with open(chapter_file_path, "w", encoding="utf-8") as f:
                json.dump(chapter_data, f, ensure_ascii=False, indent=4)

            return True
        except Exception as e:
            logger.error(f"更新JSON文件失败：{str(e)}")
            return False


# 处理单个条目（异步版本）
async def process_item_async(item, book_id, chapter_file_path, pbar):
    item_id = item["id"]
    text = item["text"]

    # 构建保存路径
    chapter_name = os.path.basename(chapter_file_path).split(".")[0]
    audio_dir = f"data/book/{book_id}/audio/{chapter_name}"
    audio_path = f"{audio_dir}/{item_id}.mp3"
    subtitle_path = f"{audio_dir}/{item_id}.srt"

    # 确保目录存在
    os.makedirs(audio_dir, exist_ok=True)

    # 检查文件是否已存在
    if os.path.exists(audio_path):
        # 检查JSON是否已更新过
        if "audio_path" not in item:
            # 文件存在但JSON未更新，更新JSON
            relative_audio_path = f"audio/{chapter_name}/{item_id}.mp3"
            update_json_with_audio_path(chapter_file_path, item_id, relative_audio_path)
        pbar.update(1)  # 更新进度条
        return True

    # 使用Edge-TTS生成音频和字幕
    success = await generate_audio_edge_tts(text, audio_path, subtitle_path)

    # 检查是否生成成功
    if not success:
        logger.error(f"处理项目 {chapter_name}/{item_id} 失败，跳过")
        pbar.update(1)  # 更新进度条
        return False

    # 更新JSON文件，添加audio_path字段
    relative_audio_path = f"audio/{chapter_name}/{item_id}.mp3"
    update_json_with_audio_path(chapter_file_path, item_id, relative_audio_path)

    pbar.update(1)  # 更新进度条
    return True


def create_book_audio(book_id: str):
    """
    使用Edge-TTS创建图书音频，支持异步并发处理
    """
    # 从环境变量获取并发数
    try:
        max_concurrent = int(os.getenv("EDGE_TTS_CONCURRENT", "4"))
    except ValueError:
        max_concurrent = 4  # 默认使用4个并发

    # 获取 data/book/{book_id}/storyboard 目录下的所有json
    storyboard_dir = f"data/book/{book_id}/storyboard"

    if not os.path.exists(storyboard_dir):
        logger.error(f"小说信息不存在{storyboard_dir}")
        return

    try:
        chapter_files = os.listdir(storyboard_dir)
        chapter_files.sort(key=lambda x: int(x.split(".")[0]))
        chapter_file_paths = [os.path.join(storyboard_dir, f) for f in chapter_files]
    except Exception as e:
        logger.error(f"读取章节文件失败：{str(e)}")
        return

    # 计算总进度
    total_items = 0
    try:
        for chapter_file_path in chapter_file_paths:
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)
                total_items += len(chapter_data)
    except Exception as e:
        logger.error(f"计算总进度失败：{str(e)}")
        return

    # 异步处理函数
    async def process_all_chapters():
        # 创建总进度条
        with tqdm(total=total_items, desc="生成音频", unit="项") as pbar:
            # 处理每个章节文件
            for chapter_file_path in chapter_file_paths:
                try:
                    # 读取章节数据
                    with open(chapter_file_path, "r", encoding="utf-8") as f:
                        chapter_data = json.load(f)

                    # 准备异步任务
                    tasks = []
                    for item in chapter_data:
                        task = process_item_async(item, book_id, chapter_file_path, pbar)
                        tasks.append(task)

                    # 限制并发数并执行任务
                    semaphore = asyncio.Semaphore(max_concurrent)
                    
                    async def limited_task(task):
                        async with semaphore:
                            return await task
                    
                    limited_tasks = [limited_task(task) for task in tasks]
                    await asyncio.gather(*limited_tasks, return_exceptions=True)
                    
                except Exception as e:
                    logger.error(f"处理章节 {chapter_file_path} 失败：{str(e)}")

    # 运行异步处理
    try:
        asyncio.run(process_all_chapters())
    except Exception as e:
        logger.error(f"异步音频生成失败：{str(e)}")
        # 回退到原始同步方法的简化版本
        logger.info("回退到同步处理...")
        _create_book_audio_sync_fallback(book_id, chapter_file_paths, total_items)


def _create_book_audio_sync_fallback(book_id: str, chapter_file_paths: List[str], total_items: int):
    """
    同步回退方法（在异步失败时使用）
    """
    with tqdm(total=total_items, desc="生成音频(同步)", unit="项") as pbar:
        for chapter_file_path in chapter_file_paths:
            try:
                with open(chapter_file_path, "r", encoding="utf-8") as f:
                    chapter_data = json.load(f)
                
                for item in chapter_data:
                    # 使用同步方式处理，但仍然调用异步Edge-TTS
                    try:
                        result = asyncio.run(process_item_async(item, book_id, chapter_file_path, pbar))
                    except Exception as e:
                        logger.error(f"同步回退处理项目失败：{str(e)}")
                        pbar.update(1)
                        
            except Exception as e:
                logger.error(f"同步回退处理章节失败：{str(e)}")


if __name__ == "__main__":
    create_book_audio("1043294775")
