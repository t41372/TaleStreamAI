# app/stages/storyboard.py
import re
import json
import asyncio
from typing import Coroutine, Any
from pathlib import Path

from chonkie import SentenceChunker
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


def _create_semantic_chunks(content: str, max_tokens: int, model_name: str = "gpt-4o") -> list[str]:
    """使用 chonkie.SentenceChunker 将文本分割成语义完整的块。"""
    logger.debug(f"Creating semantic chunks, max_tokens={max_tokens}")
    
    # 将模型名称映射到 tiktoken 编码器名称
    tokenizer_name = "cl100k_base"  # 适用于 gpt-4, gpt-4o, gpt-3.5-turbo 等
    if "gpt-3.5" in model_name.lower():
        tokenizer_name = "cl100k_base"
    elif "gpt-4" in model_name.lower():
        tokenizer_name = "cl100k_base"
    
    chunker = SentenceChunker(
        tokenizer_or_token_counter=tokenizer_name,
        chunk_size=max_tokens,
        chunk_overlap=min(100, max_tokens // 4),  # 确保重叠不超过块大小的1/4
        min_sentences_per_chunk=1
    )
    chunk_objects = chunker(content)
    chunks = [chunk.text for chunk in chunk_objects]
    logger.info(f"内容被分割为 {len(chunks)} 个语义块。")
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
        messages, system=PROMPT_REFINE_SYSTEM_PROMPT, output_path=refined_prompt_asset_path, expect_json=False
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
) -> list[Shot] | None:
    """处理单个文本块，生成原始Shots列表。所有复杂性都已移至LLM客户端。"""
    logger.info(
        f"Processing chunk {chunk_index + 1}/{num_chunks} for chapter {chapter_index}..."
    )
    messages = [{"role": "user", "content": chunk}]
    
    storyboard_asset_path = book_path / "llm" / f"storyboard_ch{chapter_index}_chunk{chunk_index}.json"

    # 客户端现在负责缓存、重试和修复。我们只需一次调用。
    response_str = await storyboard_client.chat_completion(
        messages, system=STORYBOARD_SYSTEM_PROMPT, output_path=storyboard_asset_path, expect_json=True
    )

    if "ERROR" in response_str:
        logger.error(
            f"Storyboard generation failed for chunk {chunk_index + 1} of chapter {chapter_index} after all retries and repairs: {response_str}"
        )
        # 返回 None 表示此块彻底失败
        return None

    try:
        # 此时的 response_str 应该是一个有效的 JSON 字符串
        storyboard_data = json.loads(response_str)

        # (处理嵌套列表的逻辑可以保留，作为最后一道防线)
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
                         response_str,
                         0,
                     )
             else:
                 raise json.JSONDecodeError(
                     "Response is not a list", response_str, 0
                 )

        proto_shots = []
        for item in storyboard_data:
            shot = Shot(
                shot_id=-1,
                chapter_index=chapter_index,
                original_text=item.get("text", ""),
                storyboard_path=storyboard_asset_path,
            )
            shot.temp_lens_language_en = item.get("lensLanguage_en", "")
            proto_shots.append(shot)
        
        return proto_shots

    except json.JSONDecodeError as e:
        # 这理论上不应该发生，因为客户端应该已经修复了它。
        # 但作为防御性编程，我们记录这个意外情况。
        logger.critical(
            f"FATAL: LLM client returned a non-JSON string that it claimed was valid. This should not happen. Content: {response_str[:200]}... Error: {e}"
        )
        # 将其视为彻底失败
        return None


async def _process_chapter_content(chapter: Chapter, book_path: Path) -> list[Shot]:
    """处理单个章节的完整内容，并发生成所有Shots并优化提示词。"""
    storyboard_config = settings.storyboard_llm
    content_chunks = _create_semantic_chunks(
        chapter.content,
        max_tokens=storyboard_config.max_tokens,
        model_name=storyboard_config.model,
    )

    # Step 1: Concurrently create storyboards for all chunks (Scatter)
    # 传递 book_path
    chunk_processing_tasks = [
        _process_single_chunk(chunk, chapter.index, i, len(content_chunks), book_path)
        for i, chunk in enumerate(content_chunks)
    ]
    results_per_chunk = await asyncio.gather(*chunk_processing_tasks)

    # -- 新增的健壮性检查 --
    proto_shots: list[Shot] = []
    for i, chunk_result in enumerate(results_per_chunk):
        if chunk_result is None:
            # 失败不再静默！
            logger.critical(
                f"FATAL: Chapter {chapter.index}, chunk {i} failed to process after all retries. "
                f"This chapter will be incomplete. Please check LLM API or network status."
            )
            # 你可以在这里决定是继续生成不完整的视频，还是抛出异常中止整个流程
            # raise RuntimeError(f"Failed to process chunk {i} of chapter {chapter.index}")
        else:
            proto_shots.extend(chunk_result)

    if not proto_shots:
        logger.error(f"No shots could be generated for chapter {chapter.index}.")
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
