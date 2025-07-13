# app/stages/storyboard.py
import re
import json
import asyncio
from typing import Coroutine

import tiktoken
from ..config import settings
from ..llm_client import storyboard_client, prompt_client
from ..logger import log_info, log_error, log_warning, log_debug
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
    content: str, model_name: str, max_tokens: int
) -> list[str]:
    """按token数量将文本分割成块。"""
    log_debug(f"Splitting content by tokens, max_tokens={max_tokens}")
    try:
        encoding = tiktoken.encoding_for_model("gpt-4o")
    except KeyError:
        log_warning(
            f"Model '{model_name}' not found for tiktoken, using 'cl100k_base'."
        )
        encoding = tiktoken.get_encoding("cl100k_base")

    paragraphs = content.split("\n")
    chunks, current_chunk_paragraphs, current_chunk_tokens = [], [], 0

    for p in paragraphs:
        if not p.strip():
            continue
        p_tokens = len(encoding.encode(p))

        if p_tokens > max_tokens:
            log_warning(
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

    log_info(f"Content split into {len(chunks)} chunks.")
    return chunks


async def _refine_shot_prompt(shot: Shot) -> Shot:
    """为单个Shot对象优化生成图像的提示词"""
    if not shot.storyboard_prompt_en:
        shot.error = "Missing storyboard_prompt_en for refinement."
        log_warning(
            f"Skipping prompt refinement for shot {shot.get_full_id()}: No English storyboard prompt."
        )
        return shot

    messages = [{"role": "user", "content": shot.storyboard_prompt_en}]
    refined_prompt = await prompt_client.chat_completion(
        messages, system=PROMPT_REFINE_SYSTEM_PROMPT
    )

    if "ERROR" in refined_prompt:
        shot.error = f"Prompt refinement failed: {refined_prompt}"
        log_error(
            f"Failed to refine prompt for shot {shot.get_full_id()}: {refined_prompt}"
        )
        # Fallback: use the original EN prompt and add the global style
        shot.image_prompt = (
            f"{shot.storyboard_prompt_en}, {settings.image_style_prompt}"
        )
    else:
        shot.image_prompt = f"{refined_prompt}, {settings.image_style_prompt}"

    return shot


async def _process_chapter_content(chapter: Chapter) -> list[Shot]:
    """处理单个章节的完整内容，生成带有优化提示词的Shots列表"""
    model_name = settings.storyboard_llm.model
    # 根据模型上下文调整块大小，留出余量给prompt和输出
    max_tokens = 30000 if "flash" in model_name else 8000

    content_chunks = _split_content_by_tokens(chapter.content, model_name, max_tokens)

    all_shots: list[Shot] = []
    shot_id_counter = 1

    for i, chunk in enumerate(content_chunks):
        log_info(
            f"Processing chunk {i + 1}/{len(content_chunks)} for chapter {chapter.index}..."
        )
        messages = [{"role": "user", "content": chunk}]
        response_json_str = await storyboard_client.chat_completion(
            messages, system=STORYBOARD_SYSTEM_PROMPT
        )

        if "ERROR" in response_json_str:
            log_error(
                f"Storyboard generation failed for chunk {i + 1} of chapter {chapter.index}: {response_json_str}"
            )
            continue

        try:
            # Clean up the JSON string before parsing
            response_json_str = re.sub(
                r"```json\s*|\s*```", "", response_json_str
            ).strip()
            storyboard_data = json.loads(response_json_str)
            if not isinstance(storyboard_data, list):
                # Try to find a list within a dictionary if the LLM wrapped it
                if isinstance(storyboard_data, dict):
                    found_list = False
                    for key, value in storyboard_data.items():
                        if isinstance(value, list):
                            storyboard_data = value
                            found_list = True
                            log_warning(
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

            proto_shots = []
            for item in storyboard_data:
                shot = Shot(
                    shot_id=shot_id_counter,
                    chapter_index=chapter.index,
                    original_text=item.get("text", ""),
                    storyboard_prompt_cn=item.get("lensLanguage_cn", ""),
                    storyboard_prompt_en=item.get("lensLanguage_en", ""),
                )
                proto_shots.append(shot)
                shot_id_counter += 1

            # 并发优化所有这些新生成shot的提示词
            refinement_tasks = [_refine_shot_prompt(s) for s in proto_shots]
            refined_shots = await asyncio.gather(*refinement_tasks)
            all_shots.extend(refined_shots)

        except json.JSONDecodeError as e:
            log_error(
                f"JSON parsing failed for chunk {i + 1} of chapter {chapter.index}: {e}"
            )
            log_debug(f"Problematic JSON string: {response_json_str[:500]}...")

    return all_shots


async def create_storyboard_for_chapters(chapters: list[Chapter]) -> list[Shot]:
    """
    并发处理所有章节，为它们创建完整的分镜和提示词。
    """
    tasks: list[Coroutine[any, any, list[Shot]]] = []
    for chapter in chapters:
        tasks.append(_process_chapter_content(chapter))

    results_per_chapter = await asyncio.gather(*tasks)

    # 将所有章节的shots列表扁平化为一个列表
    all_shots: list[Shot] = [
        shot for chapter_shots in results_per_chapter for shot in chapter_shots
    ]

    log_info(
        f"Storyboard and prompting stage complete. Total shots created: {len(all_shots)}"
    )
    return all_shots
