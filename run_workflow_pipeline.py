# run_workflow_pipeline.py
import os
import time
import json
from pathlib import Path
from multiprocessing import Process, JoinableQueue, cpu_count
from tqdm import tqdm

# 从 app 模块导入所有必要的函数和类
from app.main import get_book_content, extract_free_chapters, get_chapter_content
from app.board import generate_board_json, split_content_by_tokens, get_storyboard_client
from app.prompt import refine_prompt, create_client as create_prompt_client
from app.image import create_Image, save_image_data
from app.audio import generate_audio_async
from app.video import create_video_with_moving_image
from app.video_end import save_output_video
from app.logger import log_info, log_error, log_step_start, log_step_complete, log_warning, log_debug
from dotenv import load_dotenv

# ==============================================================================
# 运行配置中心
# ==============================================================================
class WorkflowConfig:
    BOOK_SOURCE: str = "test_novel.txt"
    CUSTOM_BOOK_ID: str = "test2"
    MAX_CHUNK_TOKENS: int = 16000
    IMAGE_WIDTH: int = 1440  # 竖屏视频宽度 9:16
    IMAGE_HEIGHT: int = 768 # 竖屏视频高度
    IMAGE_STYLE_PROMPT: str = "cinematic, dramatic lighting, detailed, illustration, anime style, 8k"
    
    # --- 流水线工作进程数量配置 ---
    # 建议 PROMPT_WORKERS = CPU核心数 / 2
    PROMPT_WORKERS: int = max(1, cpu_count() // 2)
    # 图片生成API不支持并发，固定为1
    IMAGE_WORKERS: int = 1
    # 音频生成是IO密集型，可以设置多一些
    AUDIO_WORKERS: int = max(2, cpu_count())
    # 视频合成是CPU/GPU密集型，建议等于CPU核心数
    VIDEO_WORKERS: int = max(1, cpu_count() // 2)
    
# Sentinel object to signal the end of the queue
POISON_PILL = None

# ==============================================================================
# 工作进程定义 (Producers and Consumers)
# ==============================================================================

def prompt_worker(config: WorkflowConfig, book_id: str, chapter_files: list, prompt_queue: JoinableQueue):
    """
    Worker 1: 读取章节文本, 生成分镜和提示词, 放入 prompt_queue.
    """
    try:
        log_info(f"[PromptWorker-{os.getpid()}] 启动...")
        storyboard_client = get_storyboard_client()
        prompt_client = create_prompt_client()

        for chapter_file in chapter_files:
            try:
                chapter_index = chapter_file.stem
                log_info(f"[PromptWorker-{os.getpid()}] 正在处理章节 {chapter_index}")
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                chunks = split_content_by_tokens(content, storyboard_client.model, config.MAX_CHUNK_TOKENS)
                
                for i, chunk in enumerate(chunks):
                    board_json_list = generate_board_json(chunk, use_stream=True)
                    if not board_json_list:
                        log_warning(f"章节 {chapter_index} 的块 {i} 未能生成分镜。")
                        continue

                    for board_item in board_json_list:
                        try:
                            refined = refine_prompt(
                                board_item["text"],
                                board_item["lensLanguage_en"],
                                prompt_client,
                                use_stream=False, # 在多进程中，流式输出会混乱，用非流式
                                style_prompt=config.IMAGE_STYLE_PROMPT,
                            )
                            board_item['lensLanguage_end'] = refined
                            task = {
                                'book_id': book_id,
                                'chapter_index': chapter_index,
                                'item': board_item
                            }
                            prompt_queue.put(task)
                        except Exception as e:
                            log_error(f"提示词优化失败于章节 {chapter_index}, ID {board_item.get('id')}: {e}")
            except Exception as e:
                log_error(f"[PromptWorker-{os.getpid()}] 处理章节 {chapter_file.name} 失败: {e}")
        log_info(f"[PromptWorker-{os.getpid()}] 完成所有任务, 退出。")
    except Exception as e:
        log_error(f"[PromptWorker-{os.getpid()}] 发生未捕获异常: {e}")


def image_worker(config: WorkflowConfig, prompt_queue: JoinableQueue, image_queue: JoinableQueue):
    """
    Worker 2: 从 prompt_queue 获取任务, 生成图片, 放入 image_queue.
    """
    try:
        log_info(f"[ImageWorker-{os.getpid()}] 启动...")
        while True:
            task = prompt_queue.get()
            if task is POISON_PILL:
                prompt_queue.task_done()
                log_info(f"[ImageWorker-{os.getpid()}] 收到毒丸, 退出。")
                break
            
            try:
                book_id = task['book_id']
                chapter_index = task['chapter_index']
                item = task['item']
                item_id = item['id']
                prompt = item['lensLanguage_end']

                image_path = Path(f"data/book/{book_id}/images/{chapter_index}/{item_id}.jpg")
                image_path.parent.mkdir(parents=True, exist_ok=True)

                log_debug(f"[ImageWorker] 正在生成图片: 章节 {chapter_index}, ID {item_id}")
                image_data = create_Image(prompt, config.IMAGE_WIDTH, config.IMAGE_HEIGHT)
                save_image_data(image_data, str(image_path))
                
                task['image_path'] = str(image_path)
                image_queue.put(task)
            except Exception as e:
                log_error(f"[ImageWorker] 图片生成失败: 章节 {task.get('chapter_index')}, ID {task.get('item', {}).get('id')}: {e}")
            finally:
                prompt_queue.task_done()
    except Exception as e:
        log_error(f"[ImageWorker-{os.getpid()}] 发生未捕获异常: {e}")

def audio_worker(config: WorkflowConfig, image_queue: JoinableQueue, audio_queue: JoinableQueue):
    """
    Worker 3: 从 image_queue 获取任务, 生成音频, 放入 audio_queue.
    """
    import asyncio
    try:
        log_info(f"[AudioWorker-{os.getpid()}] 启动...")

        async def process_task(task):
            try:
                book_id = task['book_id']
                chapter_index = task['chapter_index']
                item = task['item']
                item_id = item['id']
                text = item['text']

                audio_path = Path(f"data/book/{book_id}/audio/{chapter_index}/{item_id}.mp3")
                audio_path.parent.mkdir(parents=True, exist_ok=True)
                
                log_debug(f"[AudioWorker] 正在生成音频: 章节 {chapter_index}, ID {item_id}")
                success = await generate_audio_async(text, str(audio_path), text)
                
                if success:
                    task['audio_path'] = str(audio_path)
                    task['srt_path'] = str(audio_path.with_suffix('.srt'))
                    audio_queue.put(task)
                else:
                    raise Exception("EdgeTTS 生成失败")

            except Exception as e:
                log_error(f"[AudioWorker] 音频生成失败: 章节 {task.get('chapter_index')}, ID {task.get('item', {}).get('id')}: {e}")
            finally:
                image_queue.task_done()

        async def main_loop():
            while True:
                task = image_queue.get()
                if task is POISON_PILL:
                    log_info(f"[AudioWorker-{os.getpid()}] 收到毒丸, 退出。")
                    break
                await process_task(task)

        asyncio.run(main_loop())
    except Exception as e:
        log_error(f"[AudioWorker-{os.getpid()}] 发生未捕获异常: {e}")


def video_worker(config: WorkflowConfig, audio_queue: JoinableQueue, video_queue: JoinableQueue):
    """
    Worker 4: 从 audio_queue 获取任务, 合成视频分片, 放入 video_queue.
    """
    try:
        log_info(f"[VideoWorker-{os.getpid()}] 启动...")
        
        while True:
            task = audio_queue.get()
            if task is POISON_PILL:
                audio_queue.task_done()
                log_info(f"[VideoWorker-{os.getpid()}] 收到毒丸, 退出。")
                break
            
            try:
                book_id = task['book_id']
                chapter_index = task['chapter_index']
                item = task['item']
                item_id = item['id']
                
                video_path = Path(f"data/book/{book_id}/video/{chapter_index}/{item_id}.mp4")
                video_path.parent.mkdir(parents=True, exist_ok=True)

                log_debug(f"[VideoWorker] 正在合成视频: 章节 {chapter_index}, ID {item_id}")
                
                create_video_with_moving_image(
                    image_path=task['image_path'],
                    audio_path=task['audio_path'],
                    output_path=str(video_path),
                    video_width=config.IMAGE_WIDTH,
                    video_height=config.IMAGE_HEIGHT,
                    portrait_mode=True, # 竖屏模式
                )

                task['video_path'] = str(video_path)
                video_queue.put(task)

            except Exception as e:
                log_error(f"[VideoWorker] 视频分片合成失败: 章节 {task.get('chapter_index')}, ID {task.get('item', {}).get('id')}: {e}")
            finally:
                audio_queue.task_done()
    except Exception as e:
        log_error(f"[VideoWorker-{os.getpid()}] 发生未捕获异常: {e}")

# ==============================================================================
# 主工作流函数
# ==============================================================================
def main(config: WorkflowConfig):
    start_time = time.time()
    log_info("🚀 TaleStreamAI 流水线工作流启动...")
    
    # 确定 book_id 和 local_file
    if config.BOOK_SOURCE.endswith(".txt"):
        local_file = config.BOOK_SOURCE
        book_id = config.CUSTOM_BOOK_ID or Path(local_file).stem
    else:
        local_file = None
        book_id = config.BOOK_SOURCE
    log_info(f"处理书籍: {book_id}")

    # --- 步骤 1: 内容获取 (同步执行) ---
    log_step_start("1. 内容获取")
    book_path_obj = Path(f"data/book/{book_id}/{book_id}.json")
    if not book_path_obj.exists():
        book = get_book_content(book_id, local_file)
        if book:
            if not local_file:
                extract_free_chapters(book, book_id)
            get_chapter_content(book_id, from_local=bool(local_file))
        else:
            log_error("获取书籍内容失败，工作流终止。")
            return
    else:
        log_info("内容已存在，跳过获取。")
    log_step_complete("1. 内容获取")
    
    chapter_dir = Path(f"data/book/{book_id}/list")
    chapter_files = sorted(list(chapter_dir.glob("*.txt")), key=lambda x: int(x.stem))
    total_chapters = len(chapter_files)
    
    if total_chapters == 0:
        log_error("未找到任何章节文件，无法继续。")
        return

    # --- 步骤 2: 初始化队列和工作进程 ---
    log_step_start("2. 初始化流水线")
    prompt_queue = JoinableQueue()
    image_queue = JoinableQueue()
    audio_queue = JoinableQueue()
    video_queue = JoinableQueue()

    # 将章节文件分发给 Prompt Workers
    worker_chapter_files = [[] for _ in range(config.PROMPT_WORKERS)]
    for i, chapter_file in enumerate(chapter_files):
        worker_chapter_files[i % config.PROMPT_WORKERS].append(chapter_file)
    
    processes = []
    
    # 启动 Prompt Workers
    for i in range(config.PROMPT_WORKERS):
        p = Process(target=prompt_worker, args=(config, book_id, worker_chapter_files[i], prompt_queue))
        processes.append(p)
        p.start()

    # 启动 Image Workers
    for _ in range(config.IMAGE_WORKERS):
        p = Process(target=image_worker, args=(config, prompt_queue, image_queue))
        processes.append(p)
        p.start()
        
    # 启动 Audio Workers
    for _ in range(config.AUDIO_WORKERS):
        p = Process(target=audio_worker, args=(config, image_queue, audio_queue))
        processes.append(p)
        p.start()

    # 启动 Video Workers
    for _ in range(config.VIDEO_WORKERS):
        p = Process(target=video_worker, args=(config, audio_queue, video_queue))
        processes.append(p)
        p.start()
        
    log_info(f"已启动 {len(processes)} 个工作进程。")
    log_step_complete("2. 初始化流水线")

    # --- 步骤 3: 监控和结果收集 ---
    log_step_start("3. 流水线处理与监控")
    
    # 估算总任务数（不精确，但可用于进度条）
    # 这是一个非常粗略的估算，假设每章20个分镜
    estimated_tasks = total_chapters * 20 

    pbar = tqdm(total=estimated_tasks, desc="流水线总进度", unit="分镜")
    
    processed_count = 0
    while True:
        # 非阻塞地检查结果
        if not video_queue.empty():
            result_task = video_queue.get()
            video_queue.task_done()
            pbar.update(1)
            processed_count += 1
        
        # 检查所有进程是否还在运行
        active_processes = [p for p in processes if p.is_alive()]
        if not active_processes and video_queue.empty():
            log_info("所有工作进程已结束且队列为空，退出监控循环。")
            break
            
        time.sleep(1) # 避免CPU空转

    pbar.close()
    log_step_complete("3. 流水线处理与监控")

    # --- 步骤 4: 优雅地关闭流水线 ---
    log_step_start("4. 关闭流水线")
    # 放入"毒丸"来信号worker退出
    for _ in range(config.PROMPT_WORKERS): 
        prompt_queue.put(POISON_PILL)
    for _ in range(config.IMAGE_WORKERS): 
        image_queue.put(POISON_PILL)
    for _ in range(config.AUDIO_WORKERS): 
        audio_queue.put(POISON_PILL)
    for _ in range(config.VIDEO_WORKERS): 
        video_queue.put(POISON_PILL)
    
    # 等待所有进程终止
    for p in processes:
        p.join(timeout=30) # 等待30秒
        if p.is_alive():
            log_warning(f"进程 {p.pid} 未能在30秒内正常退出，将强制终止。")
            p.terminate()

    log_step_complete("4. 关闭流水线")

    # --- 步骤 5: 合成最终视频 ---
    log_step_start("5. 最终视频合成")
    try:
        save_output_video(book_id) # save_output_video 内部会重新扫描文件
        log_step_complete("5. 最终视频合成")
    except Exception as e:
        log_error(f"最终视频合成失败: {e}")

    total_duration = time.time() - start_time
    log_info(f"🎉 全部流程处理完成，总耗时: {total_duration:.2f} 秒。")

if __name__ == "__main__":
    load_dotenv()
    config = WorkflowConfig()
    main(config) 