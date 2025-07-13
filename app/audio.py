import asyncio
from dotenv import load_dotenv
import os
import json
from tqdm import tqdm
import concurrent.futures
import time
import threading
from .edge import generate_audio_with_edge_tts, DEFAULT_VOICE
from .logger import (log_step_start, log_step_complete, log_progress, log_info,
                    log_error, log_debug, log_concurrent, log_file_operation)

# 加载环境变量
load_dotenv(override=True)

# 线程锁字典，用于防止同时写入同一个JSON文件
json_locks = {}


# 使用Edge TTS生成音频
async def generate_audio_async(text: str, audio_path: str, original_text: str = None) -> bool:
    """
    Use Edge TTS to generate audio asynchronously.
    
    Args:
        text: Text to convert to speech
        audio_path: Path to save audio file
        original_text: Original text with punctuation for subtitle restoration
        
    Returns:
        bool: Success status
    """
    try:
        # Get voice from environment or use default
        voice = os.getenv("EDGE_TTS_VOICE", DEFAULT_VOICE)
        
        log_debug(f"開始生成音頻: {os.path.basename(audio_path)} | 語音: {voice}")
        start_time = time.time()
        
        # Generate audio and subtitles
        subtitle_path = os.path.splitext(audio_path)[0] + ".srt"
        success, _ = await generate_audio_with_edge_tts(
            text=text,
            audio_path=audio_path,
            voice=voice,
            subtitle_path=subtitle_path,
            original_text=original_text
        )
        
        duration = time.time() - start_time
        if success:
            log_file_operation("音頻生成成功", audio_path)
            log_debug(f"音頻生成耗時: {duration:.2f}s")
        else:
            log_error(f"音頻生成失敗: {os.path.basename(audio_path)}")
        
        return success
    except Exception as e:
        log_error(f"Edge TTS 生成失敗: {str(e)}")
        return False


def generate_audio(text: str, audio_path: str, original_text: str = None) -> bool:
    """
    Synchronous wrapper for Edge TTS audio generation.
    
    Args:
        text: Text to convert to speech  
        audio_path: Path to save audio file
        original_text: Original text with punctuation for subtitle restoration
        
    Returns:
        bool: Success status
    """
    return asyncio.run(generate_audio_async(text, audio_path, original_text))


# 更新JSON文件中的数据
def update_json_with_audio_path(chapter_file_path, item_id, audio_path):
    # 获取或创建该文件的锁
    if chapter_file_path not in json_locks:
        json_locks[chapter_file_path] = threading.Lock()

    # 使用锁确保线程安全
    with json_locks[chapter_file_path]:
        try:
            log_debug(f"更新JSON文件: {os.path.basename(chapter_file_path)} | ID: {item_id}")
            
            # 读取JSON文件
            with open(chapter_file_path, "r", encoding="utf-8") as f:
                chapter_data = json.load(f)

            # 查找对应的项并更新
            updated = False
            for item in chapter_data:
                if item["id"] == item_id:
                    item["audio_path"] = audio_path
                    updated = True
                    break

            if not updated:
                log_error(f"未找到ID為 {item_id} 的項目")
                return False

            # 写回JSON文件
            with open(chapter_file_path, "w", encoding="utf-8") as f:
                json.dump(chapter_data, f, ensure_ascii=False, indent=4)

            log_debug(f"JSON文件更新成功: {os.path.basename(chapter_file_path)}")
            return True
        except Exception as e:
            log_error(f"更新JSON文件失敗：{str(e)}")
            return False


# 处理单个条目
async def process_item_async(item, book_id, chapter_file_path, pbar, semaphore):
    async with semaphore:
        item_id = item["id"]
        text = item["text"]

        # 构建保存路径
        chapter_name = os.path.basename(chapter_file_path).split(".")[0]
        audio_dir = f"data/book/{book_id}/audio/{chapter_name}"
        audio_path = f"{audio_dir}/{item_id}.mp3"

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

        # 使用Edge TTS生成音频
        success = await generate_audio_async(text, audio_path, text)

        # 检查是否生成成功
        if not success:
            logger.error(f"处理项目 {chapter_name}/{item_id} 失败，跳过")
            pbar.update(1)  # 更新进度条
            return False

        try:
            # 更新JSON文件，添加audio_path字段
            relative_audio_path = f"/data/book/{book_id}/audio/{chapter_name}/{item_id}.mp3"
            update_json_with_audio_path(chapter_file_path, item_id, relative_audio_path)
        except Exception as e:
            logger.error(f"保存音频文件失败：{str(e)}")
            pbar.update(1)
            return False

        pbar.update(1)  # 更新进度条
        return True


# 处理单个条目 (同步版本)
def process_item(item, book_id, chapter_file_path, pbar):
    item_id = item["id"]
    text = item["text"]

    # 构建保存路径
    chapter_name = os.path.basename(chapter_file_path).split(".")[0]
    audio_dir = f"data/book/{book_id}/audio/{chapter_name}"
    audio_path = f"{audio_dir}/{item_id}.mp3"

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

    # 使用Edge TTS生成音频
    success = generate_audio(text, audio_path, text)

    # 检查是否生成成功
    if not success:
        logger.error(f"处理项目 {chapter_name}/{item_id} 失败，跳过")
        pbar.update(1)  # 更新进度条
        return False

    try:
        # 更新JSON文件，添加audio_path字段
        relative_audio_path = f"/data/book/{book_id}/audio/{chapter_name}/{item_id}.mp3"
        update_json_with_audio_path(chapter_file_path, item_id, relative_audio_path)
    except Exception as e:
        logger.error(f"保存音频文件失败：{str(e)}")
        pbar.update(1)
        return False

    pbar.update(1)  # 更新进度条
    return True


async def create_book_audio_async(book_id: str):
    """Async version of create_book_audio using Edge TTS with concurrency."""
    # 从环境变量获取线程数
    try:
        max_concurrent = int(os.getenv("AUDIO_THREADS", "5"))
    except ValueError:
        max_concurrent = 5  # 默认使用5个并发

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

    # 创建总进度条和信号量
    semaphore = asyncio.Semaphore(max_concurrent)
    
    with tqdm(total=total_items, desc="总进度", unit="音频") as pbar:
        # 收集所有任务
        tasks = []
        
        # 遍历每个章节文件
        for chapter_file_path in chapter_file_paths:
            try:
                # 读取章节数据
                with open(chapter_file_path, "r", encoding="utf-8") as f:
                    chapter_data = json.load(f)

                # 为每个项目创建异步任务
                for item in chapter_data:
                    task = process_item_async(item, book_id, chapter_file_path, pbar, semaphore)
                    tasks.append(task)
                    
            except Exception as e:
                logger.error(f"处理章节 {chapter_file_path} 失败：{str(e)}")

        # 并发执行所有任务
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def create_book_audio(book_id: str):
    """Main function to create book audio using Edge TTS."""
    # Check if we should use async version
    use_async = os.getenv("USE_ASYNC_AUDIO", "true").lower() == "true"
    
    if use_async:
        # Use async version with concurrency
        asyncio.run(create_book_audio_async(book_id))
    else:
        # Use original synchronous version with threading
        create_book_audio_sync(book_id)


def create_book_audio_sync(book_id: str):
    # 从环境变量获取线程数
    try:
        num_threads = int(os.getenv("AUDIO_THREADS", "1"))
    except ValueError:
        num_threads = 1  # 默认使用1个线程

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

    # 创建总进度条
    with tqdm(total=total_items, desc="总进度", unit="图") as pbar:
        # 使用线程池
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            # 遍历每个章节文件
            for chapter_file_path in chapter_file_paths:
                try:
                    # 读取章节数据
                    with open(chapter_file_path, "r", encoding="utf-8") as f:
                        chapter_data = json.load(f)

                    # 提交任务到线程池
                    futures = []
                    for item in chapter_data:
                        future = executor.submit(
                            process_item, item, book_id, chapter_file_path, pbar
                        )
                        futures.append(future)

                    # 等待所有任务完成
                    concurrent.futures.wait(futures)
                except Exception as e:
                    logger.error(f"处理章节 {chapter_file_path} 失败：{str(e)}")


if __name__ == "__main__":
    create_book_audio("1043294775")
