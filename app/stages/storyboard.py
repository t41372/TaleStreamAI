# app/stages/storyboard.py
import asyncio
import json
import re
from typing import List

from app.config import settings
from app.logger import log_info, log_error, log_debug
from app.llm_client import storyboard_client, prompt_client
from app.models import Chapter, Shot
from .prompts import STORYBOARD_PROMPT, REFINE_PROMPT # 将Prompt移到单独文件

async def _create_shots_for_single_chapter(chapter: Chapter) -> List[Shot]:
    """为单个章节生成所有分镜和提示词"""
    log_debug(f"开始为章节 {chapter.index} 生成分镜...")
    
    # 1. 生成分镜脚本
    storyboard_json_str = await storyboard_client.chat_completion(
        messages=[{"role": "user", "content": chapter.content}],
        system=STORYBOARD_PROMPT
    )
    if "ERROR" in storyboard_json_str:
        log_error(f"章节 {chapter.index} 分镜生成失败: {storyboard_json_str}")
        return []
        
    try:
        # 清理和解析JSON
        storyboard_data = json.loads(re.sub(r"```json\\n?|\\n?```", "", storyboard_json_str).strip())
    except json.JSONDecodeError:
        log_error(f"无法解析章节 {chapter.index} 的分镜JSON")
        return []

    # 2. 并发优化每个分镜的图像提示词
    async def refine_shot_prompt(item):
        text = item.get('text', '')
        lens_en = item.get('lensLanguage_en', '')
        user_content = f"分镜音频文案：{text}\\n分镜关键字：{lens_en}"
        
        refined_prompt = await prompt_client.chat_completion(
            messages=[{"role": "user", "content": user_content}],
            system=REFINE_PROMPT
        )
        # 拼接全局风格
        if "ERROR" not in refined_prompt:
            return f"{refined_prompt.strip()}, {settings.image_style_prompt}"
        return f"{lens_en}, {settings.image_style_prompt}" # Fallback

    tasks = [refine_shot_prompt(item) for item in storyboard_data]
    refined_prompts = await asyncio.gather(*tasks)

    # 3. 创建Shot对象
    shots = []
    for i, item in enumerate(storyboard_data):
        shot = Shot(
            shot_id=int(item.get('id', i + 1)),
            chapter_index=chapter.index,
            original_text=item.get('text', ''),
            storyboard_prompt_cn=item.get('lensLanguage_cn', ''),
            storyboard_prompt_en=item.get('lensLanguage_en', ''),
            image_prompt=refined_prompts[i]
        )
        shots.append(shot)
        
    log_info(f"章节 {chapter.index} 完成，生成 {len(shots)} 个分镜。")
    return shots

async def create_storyboard_for_chapters(chapters: List[Chapter]) -> List[Shot]:
    """并发处理所有章节，生成全书分镜列表"""
    tasks = [_create_shots_for_single_chapter(chap) for chap in chapters]
    results_per_chapter = await asyncio.gather(*tasks)
    
    # 将各章节的shots列表合并为一个总列表
    all_shots = [shot for chapter_shots in results_per_chapter for shot in chapter_shots]
    
    # 重新编号，确保全局ID连续
    for i, shot in enumerate(all_shots):
        shot.shot_id = i + 1
        
    return all_shots 