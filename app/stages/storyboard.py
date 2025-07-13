# app/stages/storyboard.py
import re
import json
import asyncio
from typing import Coroutine, Any
from pathlib import Path

import tiktoken
from ..config import settings
from ..llm_client import storyboard_client, prompt_client
from loguru import logger
from ..models import Chapter, Shot

# --- Prompts ---
STORYBOARD_SYSTEM_PROMPT = """
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
    }
]
"""

PROMPT_REFINE_SYSTEM_PROMPT = """
你是一位专业的AI绘画提示词工程师。你的任务是基于给定的场景描述，生成一段高质量、细节丰富的英文提示词，用于动漫风格的图像生成。
请遵循以下规则：
1.  **核心要素**: 提示词必须以 `masterpiece, best quality, highres` 开头。
2.  **风格统一**: 必须包含 `anime style, detailed illustration, vibrant colors` 来确保画风一致。
3.  **细节丰富**: 将中文描述（角色、动作、场景、情绪、灯光）转化为具体、生动的英文关键词。使用括号 `()` 来强调重要元素，例如 `(red eyes:1.2)`。
4.  **格式**: 所有关键词用逗号 `,` 分隔。
5.  **简洁**: 不要添加任何解释或无关的文字，直接输出提示词。

例如，如果输入是 "年轻男子, 愤怒地呐喊, 雨中的街道, 绝望, 霓虹灯光, 特写"，一个好的输出是：
masterpiece, best quality, highres, anime style, detailed illustration, vibrant colors, 1boy, young man, (screaming in anger:1.3), close-up shot, rain, wet clothes, desperate expression, neon lights reflection, dramatic lighting
"""


def _split_content_by_tokens(
    content: str, max_tokens: int, tokenzer_model_name: str = "gpt-4o"
) -> list[str]:
    """按token数量将文本分割成块。"""
    logger.debug(f"Splitting content by tokens, max_tokens={max_tokens}")
    try:
        encoding = tiktoken.encoding_for_model(tokenzer_model_name)
    except KeyError:
        logger.warning(f"Model '{tokenzer_model_name}' not found for tiktoken, using 'cl100k_base'.")
        encoding = tiktoken.get_encoding("cl100k_base")

    paragraphs = content.split("\n")
    chunks, current_chunk_paragraphs, current_chunk_tokens = [], [], 0

    for p in paragraphs:
        if not p.strip():
            continue
        p_tokens = len(encoding.encode(p))

        if p_tokens > max_tokens:
            logger.warning(
                f"Paragraph with {p_tokens} tokens exceeds max_tokens {max_tokens}, force splitting."
            )
            encoded_p = encoding.encode(p)
            for i in range(0, len(encoded_p), max_tokens):
                chunks.append(encoding.decode(encoded_p[i : i + max_tokens]))
            continue

        if current_chunk_tokens + p_tokens > max_tokens:
            chunks.append("\n".join(current_chunk_paragraphs))
            current_chunk_paragraphs = [p]
            current_chunk_tokens = p_tokens
        else:
            current_chunk_paragraphs.append(p)
            current_chunk_tokens += p_tokens

    if current_chunk_paragraphs:
        chunks.append("\n".join(current_chunk_paragraphs))

    logger.info(f"Content split into {len(chunks)} chunks.")
    return chunks


async def _refine_shot_prompt(shot: Shot, book_path: Path) -> Shot:
    """为单个Shot对象优化生成图像的提示词"""
    # 从上一步传递的临时字段中获取英文提示词
    if not hasattr(shot, 'temp_lens_language_en') or not shot.temp_lens_language_en:
        shot.error = "Missing English storyboard prompt for refinement."
        logger.warning(
            f"Skipping prompt refinement for shot {shot.get_full_id()}: No source prompt."
        )
        return shot

    # 1. 构造资产路径
    refined_prompt_asset_path = book_path / "llm" / f"refined_prompt_{shot.get_full_id()}.txt"
    shot.refined_prompt_path = refined_prompt_asset_path  # 无论如何都先记录路径

    messages = [{"role": "user", "content": shot.temp_lens_language_en}]
    
    # 2. 调用新的 LLM 客户端方法
    refined_prompt = await prompt_client.chat_completion(
        messages, system=PROMPT_REFINE_SYSTEM_PROMPT, output_path=refined_prompt_asset_path
    )

    if "ERROR" in refined_prompt:
        shot.error = f"Prompt refinement failed: {refined_prompt}"
        logger.error(f"Failed to refine prompt for shot {shot.get_full_id()}: {refined_prompt}")
        shot.image_prompt = f"{shot.temp_lens_language_en}, {settings.image_style_prompt}"
    else:
        shot.image_prompt = f"{refined_prompt}, {settings.image_style_prompt}"
    
    # 清理临时字段
    del shot.temp_lens_language_en
    
    return shot


async def _process_single_chunk(
    chunk: str, chapter_index: int, chunk_index: int, num_chunks: int, book_path: Path
) -> list[Shot]:
    """处理单个文本块，生成原始Shots列表，并增加重试逻辑。"""
    logger.info(
        f"Processing chunk {chunk_index + 1}/{num_chunks} for chapter {chapter_index}..."
    )
    messages = [{"role": "user", "content": chunk}]
    
    # 1. 构造资产路径
    storyboard_asset_path = book_path / "llm" / f"storyboard_ch{chapter_index}_chunk{chunk_index}.json"

    # 增加重试机制
    max_retries = 3
    for attempt in range(max_retries):
        logger.debug(f"Attempt {attempt + 1}/{max_retries} for chunk {chapter_index}-{chunk_index}")

        # 2. 调用新的 LLM 客户端方法
        response_json_str = await storyboard_client.chat_completion(
            messages, system=STORYBOARD_SYSTEM_PROMPT, output_path=storyboard_asset_path
        )

        if "ERROR" in response_json_str:
            logger.error(
                f"Storyboard generation API call failed for chunk {chunk_index + 1} of chapter {chapter_index}: {response_json_str}"
            )
            await asyncio.sleep(2)  # Wait before retrying
            continue  # Go to next attempt

        try:
            # llm_client现在会返回一个清理过的JSON字符串，无需额外清理
            storyboard_data = json.loads(response_json_str)
            
            # 处理嵌套列表的现有逻辑
            if not isinstance(storyboard_data, list):
                if isinstance(storyboard_data, dict):
                    found_list = False
                    for key, value in storyboard_data.items():
                        if isinstance(value, list):
                            storyboard_data = value
                            found_list = True
                            logger.warning(
                                f"LLM returned a dictionary, but a list was found and extracted from key '{key}'."
                            )
                            break
                    if not found_list:
                        raise json.JSONDecodeError(
                            "Response is not a list and no list found in dictionary values",
                            response_json_str,
                            0,
                        )
                else:
                    raise json.JSONDecodeError(
                        "Response is not a list", response_json_str, 0
                    )

            # 在成功解析后
            proto_shots = []
            for item in storyboard_data:
                shot = Shot(
                    shot_id=-1,  # Temporary ID, will be re-numbered later
                    chapter_index=chapter_index,
                    original_text=item.get("text", ""),
                    storyboard_path=storyboard_asset_path,
                )
                shot.temp_lens_language_en = item.get("lensLanguage_en", "")
                proto_shots.append(shot)
            
            return proto_shots  # Success, exit the retry loop and return the result

        except json.JSONDecodeError as e:
            logger.error(
                f"[Attempt {attempt + 1}] JSON parsing failed for chunk {chunk_index + 1}: {e}"
            )
            logger.debug(f"Problematic JSON string: {response_json_str[:500]}...")
            
            # 删除损坏的缓存文件，以便下次重试时能重新调用API
            storyboard_asset_path.unlink(missing_ok=True)
            logger.warning(f"Deleted corrupted asset file: {storyboard_asset_path}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))  # Exponential backoff
            else:
                logger.error(f"All {max_retries} retries failed for chunk {chunk_index + 1}. Skipping.")
                return []  # All retries failed, return empty list
    
    return []  # Should not be reached, but as a fallback


async def _process_chapter_content(chapter: Chapter, book_path: Path) -> list[Shot]:
    """处理单个章节的完整内容，并发生成所有Shots并优化提示词。"""
    storyboard_config = settings.storyboard_llm
    content_chunks = _split_content_by_tokens(
        chapter.content,
        max_tokens=storyboard_config.max_tokens,
    )

    # Step 1: Concurrently create storyboards for all chunks (Scatter)
    # 传递 book_path
    chunk_processing_tasks = [
        _process_single_chunk(chunk, chapter.index, i, len(content_chunks), book_path)
        for i, chunk in enumerate(content_chunks)
    ]
    results_per_chunk = await asyncio.gather(*chunk_processing_tasks)

    # Flatten the results from all chunks into a single list of shots
    proto_shots: list[Shot] = [
        shot for chunk_result in results_per_chunk for shot in chunk_result
    ]

    if not proto_shots:
        return []

    # Step 2: Re-number all shots FIRST to give them unique IDs (MOVED FROM STEP 3)
    # FIX: This must happen before concurrent refinement to avoid file name conflicts
    logger.debug(f"Re-numbering {len(proto_shots)} shots for chapter {chapter.index}...")
    for i, shot in enumerate(proto_shots):
        shot.shot_id = i + 1
    # Now all shots have a unique ID (1, 2, 3, ...) instead of -1.

    # Step 3: Concurrently refine prompts for all newly generated shots (Scatter)
    logger.info(f"Refining {len(proto_shots)} prompts for chapter {chapter.index}...")
    # Pass the re-numbered proto_shots to the refinement tasks
    refinement_tasks = [_refine_shot_prompt(s, book_path) for s in proto_shots]
    all_shots = await asyncio.gather(*refinement_tasks)

    # Step 4: Re-numbering is no longer needed here as it was done above.

    return all_shots


async def create_storyboard_for_chapters(chapters: list[Chapter], book_path: Path) -> list[Shot]:
    """
    并发处理所有章节，为它们创建完整的分镜和提示词。
    """
    logger.info(f"Creating storyboards for {len(chapters)} chapters concurrently...")
    # 传递 book_path
    tasks: list[Coroutine[Any, Any, list[Shot]]] = [
        _process_chapter_content(chapter, book_path) for chapter in chapters
    ]

    results_per_chapter = await asyncio.gather(*tasks)

    # Flatten the list of lists of shots into a single list
    all_shots: list[Shot] = [
        shot for chapter_shots in results_per_chapter for shot in chapter_shots
    ]

    logger.info(
        f"Storyboard and prompting stage complete. Total shots created: {len(all_shots)}"
    )
    return all_shots
