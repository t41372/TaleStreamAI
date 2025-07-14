# app/stages/storyboard.py
import re
import json
import asyncio
from typing import Coroutine, Any
from pathlib import Path

from ..config import settings
from ..llm_client import storyboard_client, prompt_client
from loguru import logger
from ..models import TextChunk, Shot

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
    chunk: TextChunk, book_path: Path, total_chunks: int
) -> list[Shot] | None:
    """处理单个文本块，生成原始Shots列表。所有复杂性都已移至LLM客户端。"""
    logger.info(
        f"正在处理文本块 {chunk.chunk_id + 1}/{total_chunks}..."
    )

    messages = [{"role": "user", "content": chunk.text}]
    storyboard_asset_path = book_path / "llm" / f"storyboard_chunk_{chunk.chunk_id}.json"

    # 客户端现在负责缓存、重试和修复。我们只需一次调用。
    response_str = await storyboard_client.chat_completion(
        messages, system=STORYBOARD_SYSTEM_PROMPT, output_path=storyboard_asset_path, expect_json=True
    )

    if "ERROR" in response_str:
        logger.error(
            f"分镜生成失败，块ID: {chunk.chunk_id}。错误: {response_str}"
        )
        # 返回 None 表示此块彻底失败
        return None

    try:
        storyboard_data = json.loads(response_str)
        if not isinstance(storyboard_data, list):
            raise json.JSONDecodeError("Response is not a list", response_str, 0)
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to decode storyboard JSON for chunk {chunk.chunk_id}: {e}\nContent: {response_str}"
        )
        return None

    proto_shots = []
    for item in storyboard_data:
        shot = Shot(
            shot_id=-1,
            # 我们将块的ID用作原先的章节索引，以保持数据模型的一致性
            chapter_index=chunk.chunk_id,
            original_text=item.get("text", ""),
            storyboard_path=storyboard_asset_path,
        )
        # 恢复对 temp_lens_language_en 的赋值，这是下游步骤需要的关键数据
        shot.temp_lens_language_en = item.get("lensLanguage_en", "")
        proto_shots.append(shot)

    if not proto_shots:
        logger.warning(f"No shots generated for chunk {chunk.chunk_id}.")
        return None

    return proto_shots


async def create_storyboard_from_chunks(
    chunks: list[TextChunk], book_path: Path
) -> list[Shot]:
    """
    并发处理所有文本块，为它们创建完整的分镜和提示词。
    """
    logger.info(f"开始为 {len(chunks)} 个文本块并发生成分镜...")

    # 步骤 1: 并发为所有块生成分镜脚本 (生成 proto-shots)
    storyboard_tasks = [
        _process_single_chunk(chunk, book_path, total_chunks=len(chunks)) for chunk in chunks
    ]
    results_per_chunk = await asyncio.gather(*storyboard_tasks)

    # 步骤 2: 收集所有成功生成的 proto-shots，并处理失败的块
    proto_shots: list[Shot] = []
    for i, chunk_result in enumerate(results_per_chunk):
        if chunk_result is None:
            logger.critical(
                f"致命错误: 块 {i} 在所有重试后仍然处理失败。最终的视频将缺少这部分内容。"
            )
        else:
            proto_shots.extend(chunk_result)

    if not proto_shots:
        logger.error("未能为任何文本块生成任何分镜。流水线终止。")
        return []

    # 步骤 3: 为所有收集到的 shots 统一且唯一地编号
    logger.debug(f"正在为 {len(proto_shots)} 个分镜进行统一编号...")
    for i, shot in enumerate(proto_shots):
        shot.shot_id = i + 1

    # 步骤 4: 并发为所有已编号的 shots 优化提示词
    logger.info(f"正在为 {len(proto_shots)} 个分镜并发优化图像提示词...")
    refinement_tasks = [_refine_shot_prompt(s, book_path) for s in proto_shots]
    all_shots = await asyncio.gather(*refinement_tasks)

    # Flatten the list of lists of shots into a single list
    # (This is no longer needed as we flattened it in step 2)
    all_shots_list: list[Shot] = list(all_shots)
    logger.info(
        f"分镜和提示词阶段完成。总共成功创建 {len(all_shots_list)} 个分镜。"
    )
    return all_shots_list
