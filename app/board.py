import os
import json
import time
import asyncio
from pathlib import Path
from openai import OpenAI
import re
from tqdm import tqdm
from dotenv import load_dotenv
import tiktoken
from .llm_client import (
    get_storyboard_client,
    async_chat_with_semaphore,
    batch_async_chat_completion,
)
from .logger import (
    log_step_start,
    log_step_complete,
    log_progress,
    log_info,
    log_error,
    log_debug,
    log_api_start,
    log_api_success,
    log_api_error,
    log_warning,
)


load_dotenv(override=True)


prompt = """
你是一个资深的剧本编辑。你的任务是根据我输入的小说内容，生成详细的分镜脚本。
请遵循以下规则：
1.  **高密度分镜**: 为每2到4句话（特别是对话或关键动作描述）创建一个独立的分镜。确保充分捕捉场景的动态变化和人物的情感交流。不要遗漏任何情节。
2.  **完整内容**: `text` 字段必须包含原始的小说文本，不要进行任何形式的概括或提炼。
3.  **镜头语言**: `lensLanguage_cn` 和 `lensLanguage_en` 需要详细描述镜头，包含以下元素：
    -   **角色**: 年龄、性别、外观、角色类型（如：年轻男子, 憔悴的拳手）。不要使用人名。
    -   **动作**: 角色的具体动作或表情（如：揪住衣领, 疲惫地喘气, 愤怒地呐喊）。
    -   **场景**: 故事发生的地点或背景（如：昏暗的地下拳台角落, 明亮的医院病房）。
    -   **情绪**: 场景的氛围或角色的情感基调（如：紧张, 绝望, 痛苦, 狂喜）。
    -   **风格**: 图像的艺术风格，固定为 **动漫风格, 细节丰富, 插画感**。
    -   **镜头角度**: 摄像机的视角或构图（如：特写, 中景, 过肩镜头, 俯视）。
    -   **灯光与环境**: 光线条件或环境氛围（如：刺眼的顶光, 窗外的月光, 闪烁的灯光）。
4.  **镜头语言格式**: 必须是逗号分隔的关键词组合，例如：`年轻男子, 揪着李哥的领子, 拳台角落, 绝望, 动漫风格, 特写, 顶光`。

请严格按照以下JSON格式返回，不要添加任何其他文字或解释，只返回有效的JSON数组：
[
    {
        "id": "1",
        "text": "鼻骨断了？我一下揪住了蚊子的衣服，说：「我还要打！你想办法！」",
        "lensLanguage_cn": "年轻拳手, 揪住衣服, 拳台, 愤怒、急切, 动漫风格, 插画感, 中景, 强光",
        "lensLanguage_en": "young boxer, grabbing clothes, boxing ring, angry, urgent, anime style, detailed, illustration, medium shot, strong light"
    },
    {
        "id": "2",
        "text": "「别打了！西毒，再打下去你真就没命了！」李哥死死的握着我的手说：「认输吧，我对裁判说我们认输！」",
        "lensLanguage_cn": "中年男子, 紧握主角的手, 拳台边, 焦急、担心, 动漫风格, 插画感, 特写, 阴影",
        "lensLanguage_en": "middle-aged man, holding protagonist's hand tightly, ringside, anxious, worried, anime style, detailed, illustration, close-up, shadow"
    }
]

重要：
- 确保输出是完整的、格式正确的JSON数组。
- 每个分镜对象都必须包含 `id`, `text`, `lensLanguage_cn`, `lensLanguage_en` 四个字段。
"""


def generate_board_json(
    chapter_content: str, max_retries=3, retry_delay=2, use_stream=True
):
    """
    生成分鏡JSON，包含詳細的進度日誌記錄

    Args:
        chapter_content: 章節内容
        max_retries: 最大重試次數
        retry_delay: 重試延遲時間
        use_stream: 是否使用流式響應

    Returns:
        分鏡列表
    """
    step_name = "生成章節分鏡JSON"
    log_step_start(step_name, f"內容長度: {len(chapter_content)} 字符")
    start_time = time.time()

    try:
        client = get_storyboard_client()
        log_info("分鏡模型客戶端初始化成功")
    except Exception as e:
        log_error(f"分鏡模型客戶端初始化失敗: {str(e)}")
        return []

    for attempt in range(max_retries):
        try:
            log_info(f"開始第 {attempt + 1}/{max_retries} 次分鏡生成嘗試")

            if use_stream:
                # 使用流式請求
                log_api_start("STORYBOARD_STREAM", model=client.model)
                response_stream = client.chat_completion_stream(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": chapter_content},
                    ],
                    temperature=0.5,
                )

                # 收集流式響應
                full_content = ""
                log_debug("開始收集流式響應內容...")

                for chunk in response_stream:
                    if chunk.choices[0].delta.content is not None:
                        chunk_content = chunk.choices[0].delta.content
                        full_content += chunk_content

                content = full_content
                log_api_success(
                    "STORYBOARD_STREAM", details=f"內容長度: {len(content)} 字符"
                )
            else:
                # 使用非流式請求
                response = client.chat_completion(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": chapter_content},
                    ],
                    temperature=0.5,
                )
                content = response.choices[0].message.content
                log_debug(f"收到API響應，內容長度: {len(content)} 字符")

            # 清理響應內容
            log_debug("開始清理和解析響應內容...")
            content = re.sub(r"```json\n?|\n?```", "", content)
            content = content.strip()

            log_debug(f"清理後內容長度: {len(content)} 字符")

            try:
                log_debug("嘗試解析JSON格式...")
                result = json.loads(content)
                # 验证结果非空
                if result and isinstance(result, list) and len(result) > 0:
                    duration = time.time() - start_time
                    log_step_complete(
                        step_name, duration, f"生成 {len(result)} 個分鏡項目"
                    )

                    # 顯示生成的分鏡摘要
                    log_info(f"分鏡生成詳情:")
                    for i, item in enumerate(result[:3]):  # 只顯示前3個
                        text_preview = (
                            item.get("text", "")[:30] + "..."
                            if len(item.get("text", "")) > 30
                            else item.get("text", "")
                        )
                        log_info(
                            f"  分鏡 {i + 1}: ID={item.get('id')}, 文字='{text_preview}'"
                        )
                    if len(result) > 3:
                        log_info(f"  ...還有 {len(result) - 3} 個分鏡項目")

                    return result
                else:
                    log_error(f"API返回空結果或格式錯誤，第 {attempt + 1} 次嘗試")
                    log_debug(f"原始內容預覽: {content[:200]}...")
                    if attempt < max_retries - 1:
                        log_info(f"等待 {retry_delay}s 後重試...")
                        time.sleep(retry_delay)
                    continue

            except json.JSONDecodeError as e:
                log_error(f"JSON解析失敗，第 {attempt + 1} 次嘗試")
                log_error(f"JSON錯誤: {str(e)} (行 {e.lineno}, 列 {e.colno})")
                log_debug(f"原始內容: {content[:500]}...")

                # 尝试修复常见的JSON问题
                if attempt == max_retries - 1:  # 最后一次尝试时才进行修复
                    log_info("嘗試修復JSON格式...")
                    fixed_content = fix_json_format(content)
                    if fixed_content:
                        try:
                            result = json.loads(fixed_content)
                            if result and isinstance(result, list) and len(result) > 0:
                                log_info("JSON修復成功!")
                                duration = time.time() - start_time
                                log_step_complete(
                                    step_name,
                                    duration,
                                    f"修復後生成 {len(result)} 個分鏡項目",
                                )
                                return result
                        except json.JSONDecodeError:
                            log_error("JSON修復失敗")

                if attempt < max_retries - 1:
                    log_info(f"等待 {retry_delay}s 後重試...")
                    time.sleep(retry_delay)
                continue

        except Exception as e:
            log_api_error("STORYBOARD_REQUEST", str(e), retry_count=attempt + 1)
            if "timeout" in str(e).lower():
                log_error("請求超時，可能是因為內容太長或服務器忙碌")
            if attempt < max_retries - 1:
                log_info(f"等待 {retry_delay}s 後重試...")
                time.sleep(retry_delay)
            continue

    duration = time.time() - start_time
    log_error(f"所有重試嘗試都失敗，返回空列表")
    log_step_complete(step_name, duration, "失敗")
    return []


def split_content_by_tokens(
    content: str, model_name: str = "gpt-4", max_tokens: int = 32000
) -> list[str]:
    """
    将文本内容按token数量分割成块。
    这能更好地利用LLM的上下文窗口，同时避免超出限制。

    Args:
        content (str): 要分割的完整文本内容。
        model_name (str): 用于计算token的编码器所对应的模型名。
        max_tokens (int): 每个块的最大token数。

    Returns:
        list[str]: 分割后的文本块列表。
    """
    log_info(f"开始按token分割内容，每块最大 {max_tokens} tokens...")
    try:
        # tiktoken.encoding_for_model 会为指定的模型获取正确的编码器
        # 它会自动下载和缓存编码器定义，非常高效
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        # 如果模型不在tiktoken的已知模型中，使用一个通用的编码器
        log_warning(f"模型 '{model_name}' 未找到，使用 'cl100k_base' 作为备用编码器。")
        encoding = tiktoken.get_encoding("cl100k_base")

    # 按段落分割，这样可以保持语义完整性
    paragraphs = content.split("\n")

    chunks = []
    current_chunk_paragraphs = []
    current_chunk_tokens = 0

    for p in paragraphs:
        p_tokens = len(encoding.encode(p))

        if p_tokens == 0:
            continue

        # 如果当前段落自身就超过了最大值，需要强制分割
        if p_tokens > max_tokens:
            log_warning(
                f"一个段落的token数({p_tokens})超过了最大值({max_tokens})，将进行强制分割。"
            )
            sub_p_encoded = encoding.encode(p)
            for i in range(0, len(sub_p_encoded), max_tokens):
                sub_chunk_encoded = sub_p_encoded[i : i + max_tokens]
                chunks.append(encoding.decode(sub_chunk_encoded))
            continue

        if current_chunk_tokens + p_tokens <= max_tokens:
            current_chunk_paragraphs.append(p)
            current_chunk_tokens += p_tokens
        else:
            chunks.append("\n".join(current_chunk_paragraphs))
            current_chunk_paragraphs = [p]
            current_chunk_tokens = p_tokens

    if current_chunk_paragraphs:
        chunks.append("\n".join(current_chunk_paragraphs))

    log_info(f"内容成功分割为 {len(chunks)} 块。")
    return chunks


def split_content_into_chunks(content, chunk_size=100):
    """
    将内容按行分割成多个块 (已弃用，保留向后兼容)

    Args:
        content (str): 要分割的内容
        chunk_size (int): 每个块的最大行数

    Returns:
        list: 分割后的内容块列表
    """
    lines = content.splitlines()
    chunks = []

    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i : i + chunk_size])
        chunks.append(chunk)

    return chunks


def merge_json_results(results_list):
    """
    合并多个JSON结果列表为一个列表

    Args:
        results_list (list): 包含多个JSON结果列表的列表

    Returns:
        list: 合并后的JSON结果列表
    """
    merged_results = []
    id_counter = 1

    for results in results_list:
        for item in results:
            # 更新ID以确保连续性
            item["id"] = str(id_counter)
            merged_results.append(item)
            id_counter += 1

    return merged_results


def generate_board(book_id: str):
    """
    生成書籍的所有章節分鏡，包含詳細的進度追蹤
    """
    step_name = "生成書籍分鏡"
    log_step_start(step_name, f"書籍ID: {book_id}")
    start_time = time.time()

    # 首先测试API连接
    log_info("開始處理前先測試API連接...")
    if not test_api_connection():
        log_error("API連接失敗，請檢查環境變量設置")
        return False

    # 確保目標目錄存在 - 使用pathlib
    base_path = Path("data") / "book" / book_id
    storyboard_dir = base_path / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    log_info(f"確保分鏡目錄存在: {storyboard_dir}")

    # 獲取所有章節文件 - 使用pathlib
    chapter_dir = base_path / "list"
    if not chapter_dir.exists():
        log_error(f"章節目錄不存在: {chapter_dir}")
        return False

    chapter_files = list(chapter_dir.glob("*.txt"))
    # 按文件名排序
    chapter_files.sort(key=lambda x: int(x.stem))

    log_info(f"發現 {len(chapter_files)} 個章節文件")

    # 跟踪处理结果
    failed_chapters = []
    skipped_chapters = []
    processed_chapters = []

    for i, chapter_file in enumerate(chapter_files):
        # 獲取章節索引
        index = chapter_file.stem
        # 檢查目標文件是否已存在且有內容 - 使用pathlib
        target_file = storyboard_dir / f"{index}.json"

        log_progress("章節分鏡處理", i + 1, len(chapter_files), f"處理章節 {index}")

        # 文件存在性檢查
        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    existing_content = json.load(f)
                # 驗證內容有效（非空列表或字典）
                if existing_content and (
                    isinstance(existing_content, list) and len(existing_content) > 0
                ):
                    log_info(f"跳過章節 {chapter_file.name} - 文件已存在且內容有效")
                    skipped_chapters.append(chapter_file.name)
                    continue  # 跳過處理
            except (json.JSONDecodeError, IOError):
                # 如果文件存在但內容無效或不可讀，則重新處理
                log_warning(f"文件 {target_file} 存在但包含無效數據 - 重新處理")

        # 讀取章節內容
        with open(chapter_file, "r", encoding="utf-8") as file:
            chapter_content = file.read()

        # 檢查內容長度，如果太長則自動分塊處理
        lines = chapter_content.splitlines()
        line_count = len(lines)
        content_size = len(chapter_content)

        log_debug(f"章節 {chapter_file.name}: {line_count} 行, {content_size} 字符")

        # 从环境变量获取配置，提供默认值
        max_chunk_tokens = int(os.getenv("MAX_CHUNK_TOKENS", "32000"))

        # 如果内容较长，进行基于token的分块处理
        if content_size > 500:  # 仅对较长的内容进行切分
            log_info(f"章節 {chapter_file.name} 內容較長，將按 tokens 進行分塊處理...")
            # 获取LLM client的模型名以供tiktoken使用
            client = get_storyboard_client()
            client_model_name = client.model
            chunks = split_content_by_tokens(
                chapter_content,
                model_name=client_model_name,
                max_tokens=max_chunk_tokens,
            )
            chunk_results = []

            log_info(f"將章節分為 {len(chunks)} 個塊進行處理")
            for i, chunk in enumerate(chunks):
                log_debug(f"處理塊 {i + 1}/{len(chunks)}, 內容長度: {len(chunk)} 字符")
                chunk_json = generate_board_json(chunk, use_stream=True)

                if chunk_json:
                    chunk_results.append(chunk_json)
                    log_debug(f"塊 {i + 1} 處理成功，生成 {len(chunk_json)} 個分鏡")
                else:
                    log_error(f"無法為章節 {chapter_file.name} 的塊 {i + 1} 生成分鏡")

            if chunk_results:
                # 合并所有成功的块结果
                board_json = merge_json_results(chunk_results)
                log_info(
                    f"成功合併 {len(chunk_results)} 個塊的結果，共 {len(board_json)} 個分鏡項"
                )
            else:
                log_error(f"章節 {chapter_file.name} 的所有塊處理都失敗了")
                board_json = []
        else:
            # 直接處理完整章節
            log_debug(f"直接處理完整章節 {chapter_file.name}")
            board_json = generate_board_json(chapter_content, use_stream=True)

        # 处理空结果
        if not board_json:
            failed_chapters.append(chapter_file.name)
            log_error(f"無法為章節 {chapter_file.name} 生成分鏡")
            continue

        # 将JSON写入文件 - 使用pathlib
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(board_json, f, ensure_ascii=False, indent=2)

        processed_chapters.append(chapter_file.name)
        log_info(
            f"章節 {chapter_file.name} 分鏡生成完成，共 {len(board_json)} 個分鏡項"
        )

    # 报告处理结果
    if skipped_chapters:
        log_info(f"跳過了 {len(skipped_chapters)} 個章節（文件已存在且內容有效）")

    if failed_chapters:
        log_error(f"處理完成，但以下章節失敗: {', '.join(failed_chapters)}")
        duration = time.time() - start_time
        log_step_complete(step_name, duration, "部分失敗")
        return False
    else:
        processed_count = len(chapter_files) - len(skipped_chapters)
        log_info(
            f"所有章節處理成功。處理了 {processed_count} 個章節，跳過了 {len(skipped_chapters)} 個章節"
        )
        duration = time.time() - start_time
        log_step_complete(step_name, duration, f"成功處理 {processed_count} 個章節")
        return True


def fix_json_format(content):
    """
    尝试修复常见的JSON格式问题
    """
    try:
        # 移除markdown代码块标记
        content = re.sub(r"```json\n?|\n?```", "", content)

        # 如果内容被截断，尝试添加缺失的结构
        content = content.strip()

        # 确保以[开始
        if not content.startswith("["):
            content = "[" + content

        # 如果没有正确结束，尝试补全
        if not content.endswith("]"):
            # 寻找最后一个完整的对象
            last_brace = content.rfind("}")
            if last_brace != -1:
                content = content[: last_brace + 1] + "]"
            else:
                content = content + "]"

        # 尝试修复常见的引号问题
        content = re.sub(r"([{,]\s*)(\w+):", r'\1"\2":', content)  # 给键加引号

        return content
    except Exception as e:
        print(f"JSON修复过程中出错: {str(e)}")
        return None


def test_api_connection():
    """
    测试API连接是否正常
    """
    try:
        client = get_storyboard_client()
        print("正在测试分鏡生成API连接...")

        if client.test_connection():
            print("✅ 分鏡生成API连接测试成功!")
            return True
        else:
            print("❌ 分鏡生成API连接测试失败")
            return False

    except Exception as e:
        print(f"❌ 分鏡生成API连接测试失败: {str(e)}")
        return False


if __name__ == "__main__":
    success = generate_board("1043294775")
    if not success:
        print("部分章节处理失败。请检查并重试。")
