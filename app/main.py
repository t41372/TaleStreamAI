import requests
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
import json
import os
import re
from .tool import clean_text, extract_chapter_id_and_name
from tqdm import tqdm
import time

load_dotenv()


import requests
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
import json
import os
import re
from .tool import clean_text, extract_chapter_id_and_name
from tqdm import tqdm
import time
from pathlib import Path

load_dotenv()


def load_local_txt_file(file_path: str, book_id: str) -> bool:
    """
    Load a local txt file and process it as a novel.

    Args:
        file_path: Path to the local txt file
        book_id: ID to use for the book

    Returns:
        bool: Success status
    """
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"文件不存在: {file_path}")
            return False

        # 创建书籍目录
        book_dir = f"data/book/{book_id}"
        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(f"{book_dir}/list", exist_ok=True)

        # 读取文本文件
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 按章节分割文本（假设章节以"第X章"开头）
        chapter_pattern = r"(第\d+章[^\n]*)"
        chapters = re.split(chapter_pattern, content)

        # 处理章节数据
        chapter_list = []
        chapter_index = 0

        for i in range(1, len(chapters), 2):  # 跳过空的分割部分
            if i + 1 < len(chapters):
                chapter_title = chapters[i].strip()
                chapter_content = chapters[i + 1].strip()

                if chapter_content:  # 只有有内容的章节才处理
                    # 提取章节编号和名称
                    chapter_id, chapter_name = extract_chapter_id_and_name(
                        chapter_title
                    )

                    # 保存章节内容到文件
                    chapter_file = f"{book_dir}/list/{chapter_index}.txt"
                    with open(chapter_file, "w", encoding="utf-8") as f:
                        # 按段落分割并保存
                        paragraphs = chapter_content.split("\n")
                        for paragraph in paragraphs:
                            paragraph = paragraph.strip()
                            if paragraph:
                                f.write(paragraph + "\n")

                    # 添加到章节列表
                    chapter_list.append(
                        {
                            "id": chapter_id
                            if chapter_id
                            else f"第{chapter_index + 1}章",
                            "name": chapter_name if chapter_name else chapter_title,
                            "url": "",  # 本地文件没有URL
                        }
                    )

                    chapter_index += 1

        # 如果没有找到章节分割，将整个文件作为一章
        if not chapter_list:
            with open(f"{book_dir}/list/0.txt", "w", encoding="utf-8") as f:
                paragraphs = content.split("\n")
                for paragraph in paragraphs:
                    paragraph = paragraph.strip()
                    if paragraph:
                        f.write(paragraph + "\n")

            chapter_list.append(
                {
                    "id": "第1章",
                    "name": file_path.stem,  # 使用文件名作为章节名
                    "url": "",
                }
            )

        # 保存章节信息到JSON
        with open(f"{book_dir}/{book_id}.json", "w", encoding="utf-8") as f:
            json.dump(chapter_list, f, ensure_ascii=False, indent=4)

        print(f"成功加载本地文件，共 {len(chapter_list)} 章")
        return True

    except Exception as e:
        print(f"加载本地文件失败: {e}")
        return False


def get_book_content(book_id: str, local_file: str = None) -> str:
    """
    获取书籍内容

    Args:
        book_id: 书籍ID
        local_file: 本地文件路径（可选）

    Returns:
        str: 书籍文件路径或False
    """
    # 如果指定了本地文件，使用本地文件
    if local_file:
        if load_local_txt_file(local_file, book_id):
            return f"data/book/{book_id}/{book_id}.json"  # 返回JSON文件路径
        else:
            return False

    # 否则从网络获取
    try:
        url = f"https://www.qidian.com/book/{book_id}/"

        payload = {}
        headers = {
            "Cookie": os.getenv("COOKIE"),
            "accept": "*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        response = requests.request("GET", url, headers=headers, data=payload)

        # 将内容保存至 /data/book/{book_id}/{book_id}.html
        os.makedirs(f"data/book/{book_id}", exist_ok=True)
        with open(f"data/book/{book_id}/{book_id}.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        # 返回书籍文件路径
        return f"data/book/{book_id}/{book_id}.html"
    except Exception as e:
        print(e)
        return False


# 解析书籍章节
def extract_free_chapters(html_file: str, book_id: str) -> list:
    """
    从HTML文件中提取免费章节信息并转为JSON格式

    参数:
        html_file (str): HTML文件路径

    返回:
        list: 包含章节信息的列表，每个章节为一个字典
    """
    try:
        # 读取HTML文件
        with open(html_file, "r", encoding="utf-8") as file:
            html_content = file.read()
            # 解析HTML内容
        soup = BeautifulSoup(html_content, "html.parser")

        # 查找第一个类名为volume-chapters的ul元素
        volume_chapters = soup.find("ul", class_="volume-chapters")
        if not volume_chapters:
            return []

        chapters = []

        # 查找所有章节项
        chapter_items = volume_chapters.find_all("li", class_="chapter-item")
        for item in chapter_items:
            # 获取章节链接
            link = item.find("a", class_="chapter-name")
            if link:
                href = link.get("href")
                title = link.get_text(strip=True)

                # 清理标题中的换行符和多余空格
                title = clean_text(title)

                # 提取章节编号和名称
                chapter_id, chapter_name = extract_chapter_id_and_name(title)

                # 将相对URL转换为绝对URL
                if href and href.startswith("//"):
                    href = "https:" + href

                # 使用要求的字段名格式
                chapter_info = {"id": chapter_id, "name": chapter_name, "url": href}

                chapters.append(chapter_info)

        # 将章节信息转换为JSON格式
        chapters_json = json.dumps(chapters, ensure_ascii=False, indent=4)

        # 将内容保存至 /data/book/{book_id}/{book_id}.json
        os.makedirs(f"data/book/{book_id}", exist_ok=True)
        with open(f"data/book/{book_id}/{book_id}.json", "w", encoding="utf-8") as f:
            f.write(chapters_json)
        return True
    except Exception as e:
        print(e)
        return False


# 获取每一章的详细内容
def get_chapter_content(book_id: str, from_local: bool = False) -> str:
    """
    从HTML文本中提取小说内容并保存到文件

    Args:
        book_id: 书籍ID
        from_local: 是否来自本地文件（如果是，跳过网络获取）
    """
    try:
        # 如果是本地文件，内容已经在load_local_txt_file中处理了
        if from_local:
            return True

        # 读取章节信息List
        with open(f"data/book/{book_id}/{book_id}.json", "r", encoding="utf-8") as file:
            chapters = json.load(file)
        # 使用进度条
        for index, chapter in tqdm(enumerate(chapters), desc="获取章节内容"):
            if chapter["url"]:
                payload = {}
                headers = {
                    "Cookie": os.getenv("COOKIE"),
                    "accept": "*/*",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                response = requests.request(
                    "GET", chapter["url"], headers=headers, data=payload
                )
                # 创建BeautifulSoup对象解析HTML
                soup = BeautifulSoup(response.text, "html.parser")
                # 查找main标签 - 小说内容在main标签内
                main_content = soup.find("main", id=lambda x: x and x.startswith("c-"))
                if not main_content:
                    print("未找到小说内容")
                    return
                # 找到所有p标签 - 每个p标签包含一段小说内容
                paragraphs = main_content.find_all("p")
                # 提取每个p标签的文本
                novel_content = [p.get_text() for p in paragraphs]
                # 将内容保存到文件中
                try:
                    # 创建目录
                    os.makedirs(f"data/book/{book_id}/list", exist_ok=True)
                    output_filename = f"data/book/{book_id}/list/{index}.txt"
                    with open(output_filename, "w", encoding="utf-8") as file:
                        for line in novel_content:
                            file.write(line + "\n")
                except Exception as e:
                    print(f"保存文件时出错: {e}")
            time.sleep(0.5)
    except Exception as e:
        print(e)
        return False


if __name__ == "__main__":
    import sys

    # 支持命令行参数指定本地文件
    local_file = None
    book_id = "1043294775"  # 默认书籍ID

    if len(sys.argv) >= 2:
        if sys.argv[1].endswith(".txt"):
            local_file = sys.argv[1]
            if len(sys.argv) >= 3:
                book_id = sys.argv[2]
            else:
                # 使用文件名作为book_id
                book_id = Path(local_file).stem
        else:
            book_id = sys.argv[1]

    print(f"处理书籍ID: {book_id}")
    if local_file:
        print(f"使用本地文件: {local_file}")

    book = get_book_content(book_id, local_file)
    if book:
        if not local_file:  # 只有网络获取的才需要解析HTML
            extract_free_chapters(book, book_id)
        get_chapter_content(book_id, from_local=bool(local_file))
    else:
        print("获取书籍内容失败")
