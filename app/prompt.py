from openai import OpenAI
import json
import os
import re
import time
import concurrent.futures
import threading
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from .llm_client import get_prompt_client
from .logger import (log_step_start, log_step_complete, log_progress, log_info, 
                    log_error, log_debug, log_api_start, log_api_success, log_api_error)

load_dotenv()


# 用于线程安全的打印
print_lock = threading.Lock()


def safe_print(message):
    with print_lock:
        print(message)


prompt = """
StableDiffusion是一款利用深度学习的文生图模型，支持通过使用提示词来产生新的图像，描述要包含或省略的元素。
我在这里引入StableDiffusion算法中的Prompt概念，又被称为提示符。
下面的prompt是用来指导AI绘画模型创作图像的。它们包含了图像的各种细节，如人物的外观、背景、颜色和光线效果，以及图像的主题和风格。这些prompt的格式经常包含括号内的加权数字，用于指定某些细节的重要性或强调。例如，"(masterpiece:1.5)"表示作品质量是非常重要的，多个括号也有类似作用。此外，如果使用中括号，如"{blue hair:white hair:0.3}"，这代表将蓝发和白发加以融合，蓝发占比为0.3。
以下是用prompt帮助AI模型生成图像的例子：masterpiece,(bestquality),highlydetailed,ultra-detailed,cold,solo,(1girl),(detailedeyes),(shinegoldeneyes),(longliverhair),expressionless,(long sleeves),(puffy sleeves),(white wings),shinehalo,(heavymetal:1.2),(metaljewelry),cross-lacedfootwear (chain),(Whitedoves:1.2)
需要多增加一些漫画风格以及漫画的细节的关键词进来

仿照例子，给出一套详细描述以下内容的prompt。直接开始给出prompt不需要用自然语言描述不要出现人名不要使用中文：
"""


# 创建OpenAI客户端
def create_client():
    try:
        return get_prompt_client()
    except Exception as e:
        print(f"❌ 提示詞模型客戶端初始化失敗: {str(e)}")
        raise


# 润色提示词
def refine_prompt(text: str, board_info: str, client=None, use_stream=True) -> str:
    """
    使用LLM優化圖片生成提示詞
    
    Args:
        text: 分鏡文字內容
        board_info: 分鏡關鍵字
        client: LLM客戶端
        use_stream: 是否使用流式響應
        
    Returns:
        優化後的提示詞
    """
    global prompt
    if client is None:
        client = create_client()

    _text = f"""
        以下是小说分镜音频文案：{text}
        以下是小说分镜关键字：{board_info}
        这是一本漫画小说
    """

    try:
        if use_stream:
            log_api_start("PROMPT_REFINE_STREAM", details="流式生成圖片提示詞")
            
            # 使用流式請求
            response_stream = client.chat_completion_stream(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": _text},
                ],
            )
            
            # 收集流式響應
            full_content = ""
            for chunk in response_stream:
                if chunk.choices[0].delta.content is not None:
                    chunk_content = chunk.choices[0].delta.content
                    full_content += chunk_content
            
            log_api_success("PROMPT_REFINE_STREAM", details=f"生成提示詞長度: {len(full_content)} 字符")
            return full_content
        else:
            log_api_start("PROMPT_REFINE", details="生成圖片提示詞")
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": _text},
                ],
            )
            content = response.choices[0].message.content
            log_api_success("PROMPT_REFINE", details=f"生成提示詞長度: {len(content)} 字符")
            return content
    except Exception as e:
        log_api_error("PROMPT_REFINE", str(e))
        raise


# 处理分镜文本的异常
def handle_board_text_exception(text: str) -> str:
    # 如果text中包含\n，则将\n替换为空
    text = text.replace("\n", "")
    # 如果text中包含\r，则将\r替换为空
    text = text.replace("\r", "")
    # 如果text中包含\t，则将\t替换为空
    text = text.replace("\t", "")
    # 如果text中包含多个连续空格，则将多个空格替换为空
    text = re.sub(r"\s+", "", text)
    return text


# 处理单个分镜对象
def process_single_item(item, client):
    """
    處理單個分鏡對象，將 lensLanguage_en 優化為 lensLanguage_end
    
    Args:
        item: 分鏡對象
        client: LLM客戶端
        
    Returns:
        tuple: (處理後的對象, 狀態)
    """
    item_id = item.get("id", "未知")

    # 检查是否已处理过（已有lensLanguage_end字段）
    if "lensLanguage_end" in item and item["lensLanguage_end"]:
        log_debug(f"跳過已處理的分鏡ID: {item_id}")
        return item, "skipped"

    # 预处理文本
    original_text = item.get("text", "")
    processed_text = handle_board_text_exception(original_text)
    item["text"] = processed_text

    # 生成优化的提示词
    try:
        log_debug(f"開始處理分鏡ID: {item_id}")
        lens_language = refine_prompt(processed_text, processed_text, client, use_stream=False)
        item["lensLanguage_end"] = lens_language
        log_debug(f"分鏡ID: {item_id} 處理成功，生成提示詞長度: {len(lens_language)} 字符")
        return item, "success"
    except Exception as e:
        # 处理失败时，使用lensLanguage_en的值作为备选
        if "lensLanguage_en" in item and item["lensLanguage_en"]:
            item["lensLanguage_end"] = item["lensLanguage_en"]
            log_error(f"分鏡ID: {item_id} 處理失敗，使用lensLanguage_en作為備選: {str(e)}")
            return item, "fallback"
        else:
            log_error(f"分鏡ID: {item_id} 處理失敗，且無可用的lensLanguage_en: {str(e)}")
            return item, "error"


# 处理单个章节文件
def process_chapter_file(chapter_file_path, max_workers=10):
    """
    處理單個章節分鏡文件
    
    Args:
        chapter_file_path: 章節文件路徑
        max_workers: 最大並發數
        
    Returns:
        bool: 處理是否成功
    """
    chapter_name = Path(chapter_file_path).stem
    log_info(f"開始處理章節: {chapter_name}")
    
    try:
        # 读取文件内容
        with open(chapter_file_path, "r", encoding="utf-8") as f:
            board_info = json.load(f)

        # 创建客户端
        client = create_client()
        log_debug(f"章節 {chapter_name} 提示詞模型客戶端初始化成功")

        # 使用线程池处理每个对象
        processed_items = []
        result_stats = {"success": 0, "fallback": 0, "error": 0, "skipped": 0}
        total_items = len(board_info)
        
        log_info(f"章節 {chapter_name} 需要處理 {total_items} 個分鏡項目")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_item = {
                executor.submit(process_single_item, item, client): item
                for item in board_info
            }

            # 处理结果，使用tqdm显示进度
            for future in tqdm(
                concurrent.futures.as_completed(future_to_item),
                total=total_items,
                desc=f"處理 {chapter_name}",
                unit="項目",
            ):
                item_result, status = future.result()
                processed_items.append(item_result)
                result_stats[status] += 1

        # 写回文件
        with open(chapter_file_path, "w", encoding="utf-8") as f:
            json.dump(processed_items, f, ensure_ascii=False, indent=2)

        log_info(f"章節 {chapter_name} 處理完成")
        log_info(
            f"統計: 成功={result_stats['success']}, 使用備選={result_stats['fallback']}, "
            f"錯誤={result_stats['error']}, 跳過={result_stats['skipped']}"
        )
        return True
    except Exception as e:
        log_error(f"處理章節文件 {chapter_name} 時出錯: {e}")
        return False


# 多线程处理所有分镜文件
def process_board_files(book_id: str, file_threads=5, item_threads=10) -> None:
    """
    處理書籍的所有分鏡文件，將 lensLanguage_en 優化為 lensLanguage_end
    
    Args:
        book_id: 書籍ID
        file_threads: 文件級別線程數
        item_threads: 分鏡項目級別線程數
    """
    step_name = "分鏡提示詞處理"
    log_step_start(step_name, f"書籍ID: {book_id}")
    start_time = time.time()
    
    # 使用pathlib处理路径
    base_path = Path("data") / "book" / book_id
    storyboard_dir = base_path / "storyboard"
    
    if not storyboard_dir.exists():
        log_error(f"分鏡目錄不存在: {storyboard_dir}")
        return

    # 按文件名排序
    chapter_files = list(storyboard_dir.glob("*.json"))
    chapter_files.sort(key=lambda x: int(x.stem))
    
    log_info(f"發現 {len(chapter_files)} 個分鏡文件")

    # 使用线程池处理文件
    with concurrent.futures.ThreadPoolExecutor(max_workers=file_threads) as executor:
        # 提交所有任务
        futures = [
            executor.submit(process_chapter_file, str(chapter_file), item_threads)
            for chapter_file in chapter_files
        ]

        # 处理结果
        successful_files = 0
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            try:
                result = future.result()
                if result:
                    successful_files += 1
                    log_debug(f"成功處理文件 {i+1}/{len(chapter_files)}")
                else:
                    log_error(f"處理文件失敗 {i+1}/{len(chapter_files)}")
            except Exception as e:
                log_error(f"處理文件時發生異常: {e}")
    
    duration = time.time() - start_time
    log_step_complete(step_name, duration, f"成功處理 {successful_files}/{len(chapter_files)} 個文件")
    log_info(f"分鏡提示詞處理完成，成功 {successful_files}/{len(chapter_files)} 個文件")


if __name__ == "__main__":
    book_id = "1043294775"  # 可以作为参数传入
    # 设置文件级别的线程数和处理每个文件内分镜的线程数
    file_threads = 2  # 同时处理的文件数
    item_threads = 10  # 每个文件内同时处理的分镜对象数
    process_board_files(book_id, file_threads, item_threads)
