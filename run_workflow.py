# run_workflow.py
import os
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from app.main import get_book_content, extract_free_chapters, get_chapter_content
from app.board import generate_board
from app.image import get_book_images, generate_book_images
from app.audio import create_book_audio
from app.tts import create_tts
from app.video import create_book_video
from app.video_end import save_output_video
from app.logger import log_info, log_error, log_step_start, log_step_complete


# ==============================================================================
# 运行配置中心 (在这里修改所有参数)
# ==============================================================================
class WorkflowConfig:
    # --- 基本配置 ---
    # 书籍ID或本地文件名。
    # 如果是起点ID (如 "1043294775")，程序会从网络获取。
    # 如果是本地文件路径 (如 "test_novel.txt")，程序会读取本地文件。
    BOOK_SOURCE: str = "test_novel.txt"

    # 如果 BOOK_SOURCE 是本地文件名，可以为它指定一个ID。
    # 如果留空，将使用文件名作为ID。
    CUSTOM_BOOK_ID: str = ""

    # --- 分镜生成配置 ---
    MAX_CHUNK_TOKENS: int = 16000  # 每个LLM调用块的最大输入token数

    # --- 图像生成配置 ---
    IMAGE_WIDTH: int = 1440  # 横版视频宽度
    IMAGE_HEIGHT: int = 1080  # 横版视频高度

    # 用户自定义的全局风格提示词，会附加到每个图片生成提示词的末尾
    # 例如: "cinematic, hyper-detailed, photorealistic, 8k"
    # 或者: "anime style, studio ghibli, vibrant colors, hand-drawn"
    IMAGE_STYLE_PROMPT: str = (
        "anime style, dramatic lighting, detailed, illustration, japanese style"
    )

    # --- 视频生成配置 ---
    VIDEO_THREADS: int = 4  # 视频分段生成时的并发线程数

    # --- 性能与流程控制 ---
    # 设置为 True 以跳过已成功生成的步骤，实现断点续传
    SKIP_COMPLETED_STEPS: bool = True

    # 设置为 True 以启用基于章节的并行处理
    ENABLE_PARALLEL_PROCESSING: bool = True

    # 并行处理的最大进程数
    MAX_PARALLEL_CHAPTERS: int = 3

    # 定义要运行的流程阶段
    STEPS_TO_RUN = [
        "content",  # 1. 获取和处理小说内容
        "board",  # 2. 生成分镜
        "prompt",  # 3. 优化提示词
        "image",  # 4. 生成图片
        "audio",  # 5. 生成音频和字幕
        "video_clips",  # 6. 生成视频分片
        "final_video",  # 7. 合并最终视频和字幕
    ]


def process_chapter_pipeline(book_id: str, chapter_index: int, config: WorkflowConfig):
    """
    处理单个章节的完整流水线（用于并行处理）。
    这个函数将在一个独立的进程中运行。
    """
    try:
        # 在子进程中重新导入必要的模块
        from app.board import generate_board_json
        from app.prompt import process_chapter_file
        from app.llm_client import get_storyboard_client
        from app.board import split_content_by_tokens
        from dotenv import load_dotenv
        import json

        # 重新加载环境变量
        load_dotenv()

        log_info(f"▶️ 开始处理章节 {chapter_index} 流水线...")

        chapter_file = Path(f"data/book/{book_id}/list/{chapter_index}.txt")
        storyboard_file = Path(f"data/book/{book_id}/storyboard/{chapter_index}.json")

        # 检查章节文件是否存在
        if not chapter_file.exists():
            raise Exception(f"章节文件不存在: {chapter_file}")

        # 1. 分镜生成
        board_success = False
        if not storyboard_file.exists():
            try:
                with open(chapter_file, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.strip():
                    raise Exception("章节内容为空")

                # 设置环境变量
                os.environ["MAX_CHUNK_TOKENS"] = str(config.MAX_CHUNK_TOKENS)

                # 使用优化的分镜生成逻辑
                content_size = len(content)
                if content_size > 500:  # 使用分块处理
                    log_info(f"章节 {chapter_index} 内容较长，使用分块处理...")
                    client = get_storyboard_client()
                    client_model_name = client.model
                    chunks = split_content_by_tokens(
                        content,
                        model_name=client_model_name,
                        max_tokens=config.MAX_CHUNK_TOKENS,
                    )

                    chunk_results = []
                    for i, chunk in enumerate(chunks):
                        try:
                            chunk_json = generate_board_json(chunk, use_stream=True)
                            if chunk_json:
                                chunk_results.append(chunk_json)
                        except Exception as e:
                            log_error(f"章节 {chapter_index} 块 {i+1} 处理失败: {e}")
                            continue

                    # 合并结果
                    if chunk_results:
                        from app.board import merge_json_results

                        board_json = merge_json_results(chunk_results)
                    else:
                        board_json = []
                else:
                    board_json = generate_board_json(content, use_stream=True)

                if not board_json:
                    raise Exception("分镜生成失败 - 无有效结果")

                # 确保目录存在
                storyboard_file.parent.mkdir(parents=True, exist_ok=True)
                with open(storyboard_file, "w", encoding="utf-8") as f:
                    json.dump(board_json, f, ensure_ascii=False, indent=2)
                board_success = True

            except Exception as e:
                log_error(f"章节 {chapter_index} 分镜生成失败: {e}")
                return (chapter_index, f"Board generation failed: {e}")
        else:
            board_success = True
            log_info(f"章节 {chapter_index} 分镜文件已存在，跳过生成")

        # 2. 提示词优化
        prompt_success = False
        if board_success and storyboard_file.exists():
            try:
                process_chapter_file(
                    str(storyboard_file), style_prompt=config.IMAGE_STYLE_PROMPT
                )
                prompt_success = True
            except Exception as e:
                log_error(f"章节 {chapter_index} 提示词优化失败: {e}")
                return (chapter_index, f"Prompt optimization failed: {e}")

        if board_success and prompt_success:
            log_info(f"✅ 章节 {chapter_index} 流水线处理完成。")
            return (chapter_index, "Success")
        else:
            return (chapter_index, "Partial failure")

    except Exception as e:
        log_error(f"❌ 章节 {chapter_index} 流水线处理失败: {e}")
        return (chapter_index, f"Failed: {e}")


def parallel_process_chapters(book_id: str, config: WorkflowConfig):
    """
    并行处理所有章节的分镜生成和提示词优化
    """
    log_step_start("并行处理章节")

    # 获取所有需要处理的章节
    chapter_dir = Path(f"data/book/{book_id}/list")
    if not chapter_dir.exists():
        log_error(f"章节目录不存在: {chapter_dir}")
        return

    chapter_files = sorted(list(chapter_dir.glob("*.txt")), key=lambda x: int(x.stem))
    chapter_indices = [int(p.stem) for p in chapter_files]

    log_info(f"发现 {len(chapter_indices)} 个章节需要处理")

    # 使用进程池并行处理
    with ProcessPoolExecutor(max_workers=config.MAX_PARALLEL_CHAPTERS) as executor:
        # 提交所有章节任务
        future_to_chapter = {
            executor.submit(process_chapter_pipeline, book_id, index, config): index
            for index in chapter_indices
        }

        # 收集结果并显示进度
        with tqdm(
            total=len(chapter_indices), desc="章节并行处理进度", unit="章节"
        ) as pbar:
            for future in as_completed(future_to_chapter):
                try:
                    index, status = future.result()
                    log_info(f"章节 {index} 处理结果: {status}")
                    pbar.update(1)
                except Exception as e:
                    index = future_to_chapter[future]
                    log_error(f"章节 {index} 处理异常: {e}")
                    pbar.update(1)

    log_step_complete("并行处理章节")


def main(config: WorkflowConfig):
    """
    主工作流函数
    """
    start_time = time.time()
    log_info("🚀 TaleStreamAI 工作流启动...")
    log_info(
        f"配置: BOOK_SOURCE='{config.BOOK_SOURCE}', BOOK_ID='{config.CUSTOM_BOOK_ID or Path(config.BOOK_SOURCE).stem}'"
    )
    log_info(f"并行处理: {'启用' if config.ENABLE_PARALLEL_PROCESSING else '禁用'}")

    # 确定 book_id 和 local_file
    if config.BOOK_SOURCE.endswith(".txt"):
        local_file = config.BOOK_SOURCE
        book_id = config.CUSTOM_BOOK_ID or Path(local_file).stem
    else:
        local_file = None
        book_id = config.BOOK_SOURCE

    # --- 步骤 1: 获取内容 ---
    if "content" in config.STEPS_TO_RUN:
        log_step_start("1. 内容获取")
        book_path = f"data/book/{book_id}/{book_id}.json"
        if not (config.SKIP_COMPLETED_STEPS and Path(book_path).exists()):
            book = get_book_content(book_id, local_file)
            if book:
                if not local_file:
                    extract_free_chapters(book, book_id)
                get_chapter_content(book_id, from_local=bool(local_file))
                log_step_complete("1. 内容获取")
            else:
                log_error("获取书籍内容失败，工作流终止。")
                return
        else:
            log_info("内容已存在，跳过此步骤。")
            log_step_complete("1. 内容获取")

    # --- 步骤 2 & 3: 分镜生成与提示词优化 ---
    if (
        "board" in config.STEPS_TO_RUN or "prompt" in config.STEPS_TO_RUN
    ) and config.ENABLE_PARALLEL_PROCESSING:
        # 使用并行处理
        parallel_process_chapters(book_id, config)
    else:
        # 使用传统的串行处理
        if "board" in config.STEPS_TO_RUN:
            log_step_start("2. 分镜生成")
            os.environ["MAX_CHUNK_TOKENS"] = str(config.MAX_CHUNK_TOKENS)
            generate_board(book_id)
            log_step_complete("2. 分镜生成")

        if "prompt" in config.STEPS_TO_RUN:
            log_step_start("3. 提示词优化")
            from app.prompt import process_board_files

            process_board_files(book_id, style_prompt=config.IMAGE_STYLE_PROMPT)
            log_step_complete("3. 提示词优化")

    # --- 步骤 4: 生成图片 ---
    if "image" in config.STEPS_TO_RUN:
        log_step_start("4. 图片生成")
        try:
            generate_book_images(
                book_id, width=config.IMAGE_WIDTH, height=config.IMAGE_HEIGHT
            )
            get_book_images(book_id)  # 高清修复
            log_step_complete("4. 图片生成")
        except Exception as e:
            log_error(f"图片生成步骤失败: {e}")
            log_info("继续处理后续步骤...")

    # --- 步骤 5: 生成音频 ---
    if "audio" in config.STEPS_TO_RUN:
        log_step_start("5. 音频与字幕生成")
        try:
            create_book_audio(book_id)
            create_tts(book_id, os.getcwd())  # 验证字幕
            log_step_complete("5. 音频与字幕生成")
        except Exception as e:
            log_error(f"音频生成步骤失败: {e}")
            log_info("继续处理后续步骤...")

    # --- 步骤 6: 生成视频分片 ---
    if "video_clips" in config.STEPS_TO_RUN:
        log_step_start("6. 视频分片生成")
        try:
            # 把配置写入环境变量，因为 video.py 内部直接读取了环境变量
            os.environ["VIDEO_WIDTH"] = str(config.IMAGE_WIDTH)
            os.environ["VIDEO_HEIGHT"] = str(config.IMAGE_HEIGHT)
            os.environ["VIDEO_THREADS"] = str(config.VIDEO_THREADS)
            create_book_video(book_id)
            log_step_complete("6. 视频分片生成")
        except Exception as e:
            log_error(f"视频分片生成步骤失败: {e}")
            log_info("继续处理后续步骤...")

    # --- 步骤 7: 合成最终视频 ---
    if "final_video" in config.STEPS_TO_RUN:
        log_step_start("7. 最终视频合成")
        try:
            save_output_video(book_id)
            log_step_complete("7. 最终视频合成")
        except Exception as e:
            log_error(f"最终视频合成步骤失败: {e}")
            log_info("工作流程中存在失败步骤，请检查日志")

    total_duration = time.time() - start_time
    log_info(f"🎉 全部流程处理完成，总耗时: {total_duration:.2f} 秒。")


if __name__ == "__main__":
    # 加载.env文件中的环境变量，例如API密钥
    from dotenv import load_dotenv

    load_dotenv()

    # 实例化配置并运行主函数
    config = WorkflowConfig()
    main(config)
