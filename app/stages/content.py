# app/stages/content.py
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional, List

import aiohttp
from bs4 import BeautifulSoup
from tqdm import tqdm

from ..config import settings
from ..logger import log_info, log_error, log_warning
from ..models import Chapter

async def _fetch_url(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    """异步获取URL内容。"""
    headers = {
        "Cookie": os.getenv("COOKIE", ""),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        log_error(f"网络请求失败: {url}, 错误: {e}")
        return None

def _parse_chapters_from_html(html_content: str) -> list[dict]:
    """从目录页HTML中解析章节列表。"""
    soup = BeautifulSoup(html_content, "html.parser")
    volume_chapters = soup.find("ul", class_="volume-chapters")
    if not volume_chapters:
        return []

    chapters = []
    for item in volume_chapters.find_all("li", class_="chapter-item"):
        link = item.find("a", class_="chapter-name")
        if link and (href := link.get("href")):
            title = re.sub(r'\\s+', ' ', link.get_text(strip=True))
            # 提取章节ID和名称
            match = re.search(r"^(第\\d+章)", title)
            chapter_id = match.group(1) if match else ""
            chapter_name = title[len(chapter_id):].strip()

            chapters.append({
                "id": chapter_id,
                "name": chapter_name or title,
                "url": "https:" + href if href.startswith("//") else href
            })
    return chapters

async def _get_remote_chapters(book_id: str, book_path: Path) -> list[Chapter]:
    """从网络获取小说内容。"""
    catalog_url = f"https://www.qidian.com/book/{book_id}/"
    chapters_json_path = book_path / f"{book_id}.json"
    chapters_list_dir = book_path / "list"
    chapters_list_dir.mkdir(exist_ok=True)

    async with aiohttp.ClientSession() as session:
        catalog_html = await _fetch_url(session, catalog_url)
        if not catalog_html:
            return []

        chapter_infos = _parse_chapters_from_html(catalog_html)
        with open(chapters_json_path, "w", encoding="utf-8") as f:
            json.dump(chapter_infos, f, ensure_ascii=False, indent=2)

        tasks = []
        for i, info in enumerate(chapter_infos):
            chapter_file = chapters_list_dir / f"{i}.txt"
            if not chapter_file.exists():
                tasks.append(_fetch_and_save_chapter(session, info['url'], chapter_file))

        results = await asyncio.gather(*tasks)

        chapters = []
        for i, content in enumerate(results):
            if content:
                chapters.append(Chapter(index=i, content=content))

    return chapters

async def _fetch_and_save_chapter(session: aiohttp.ClientSession, url: str, path: Path):
    """获取单个章节内容并保存。"""
    html = await _fetch_url(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    main_content = soup.find("div", class_="read-content")
    if not main_content:
        return None

    paragraphs = [p.get_text(strip=True) for p in main_content.find_all("p")]
    content = "\\n".join(filter(None, paragraphs))

    path.write_text(content, encoding="utf-8")
    return content


def _get_local_chapters(source_file: str, book_path: Path) -> list[Chapter]:
    """从本地TXT文件加载章节。"""
    source_path = Path(source_file)
    if not source_path.exists():
        log_error(f"本地文件不存在: {source_file}")
        return []

    chapters_list_dir = book_path / "list"
    chapters_list_dir.mkdir(exist_ok=True)

    content = source_path.read_text(encoding="utf-8")
    # 按 "第X章" 分割，保留分隔符
    raw_chunks = re.split(r'(第\\d+章.*)', content)

    chapters = []
    chapter_index = 0

    # 第一个块是标题前的任何内容，通常忽略
    # 从索引1开始，步长为2，来获取 (标题, 内容) 对
    for i in range(1, len(raw_chunks), 2):
        title = raw_chunks[i].strip()
        text = raw_chunks[i+1].strip()
        if text:
            chapter = Chapter(index=chapter_index, content=text)
            chapters.append(chapter)
            # 将分割好的章节内容写入文件，以便后续步骤可以统一处理
            (chapters_list_dir / f"{chapter_index}.txt").write_text(text, encoding="utf-8")
            chapter_index += 1

    if not chapters: # 如果没有匹配到 "第X章"，则将整个文件视为一章
        log_warning("未在文件中找到 '第X章' 格式的章节标题，将整个文件视为一个章节。")
        chapter = Chapter(index=0, content=content)
        chapters.append(chapter)
        (chapters_list_dir / f"0.txt").write_text(content, encoding="utf-8")

    return chapters

async def get_chapters(book_id: str, source_file: Optional[str] = None) -> list[Chapter]:
    """
    内容获取阶段的主函数。
    根据输入源（网络或本地）获取所有章节内容。
    """
    book_path = settings.paths.get_book_path(book_id)
    book_path.mkdir(exist_ok=True)

    if source_file:
        log_info(f"从本地文件加载: {source_file}")
        return _get_local_chapters(source_file, book_path)
    else:
        log_info(f"从网络获取书籍ID: {book_id}")
        return await _get_remote_chapters(book_id, book_path) 