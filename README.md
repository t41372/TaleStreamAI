# TaleStreamAI v1.0 🚀

一个基于现代Python构建的、异步的、流水线驱动的AI小说转视频自动化工具。

[B站演示-6小时成片](https://www.bilibili.com/video/BV1mmQvYEEwb/) | [爱发电支持](https://afdian.com/a/dmzw1918)

---

## ✨ 核心特性

* **现代化架构**: 采用基于 `asyncio` 的异步流水线，将I/O密集型任务（API调用）与CPU密集型任务（视频处理）分离，最大化性能。
* **高度并发**: 充分利用异步I/O和多进程，同时处理内容获取、分镜生成、资产合成等多个环节。
* **健壮的缓存**: 内置基于参数哈希的缓存机制，昂贵的API调用（LLM、图像、音频）会被自动缓存，极大加速调试和重复运行。
* **配置驱动**: 所有关键参数通过 `.env` 文件集中管理，清晰易懂。
* **模块化设计**: 清晰的四阶段流水线 (`Content` -> `Storyboard` -> `Assets` -> `Finalizer`)，易于维护和扩展。

## 🛠️ 技术栈

* **核心框架**: Python 3.12+, Asyncio
* **LLM编排**: `openai` SDK (兼容所有OpenAI API格式的服务)
* **语音合成**: Microsoft Edge TTS (`edge-tts`)
* **图像生成**: 任何兼容的文生图API (默认为Flux)
* **视频处理**: `moviepy`, `ffmpeg`
* **依赖管理**: `uv`

---

## 🚀 快速开始

> 强烈建议使用 Python 3.12 或更高版本。

### 1. 安装 uv (如果尚未安装)
```shell
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows
pip install uv
```

### 2. 克隆并设置环境

```shell
git clone https://github.com/t41372/TaleStreamAI.git
cd TaleStreamAI

# 使用uv一键创建虚拟环境并安装所有依赖
uv sync
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，并填入你的API密钥等信息。

```bash
# .env
COOKIE= # 如果需要爬取起点，请填入Cookie
STORYBOARD_API_KEY=your_gemini_or_other_llm_api_key
STORYBOARD_API_URL=https://...
PROMPT_API_KEY=your_deepseek_or_other_llm_api_key
PROMPT_API_URL=https://...
```

### 4. 运行！

程序现在拥有唯一的入口 `run.py`。

```shell
# --- 处理来自本地文件的的小说 ---
# 使用 test_novel.txt，书籍ID将自动设为 "test_novel"
uv run run.py test_novel.txt

# 为本地文件指定一个自定义的书籍ID
uv run run.py your_novel.txt --book_id "my-epic-story"

# --- 处理来自网络的起点小说 ---
# 使用起点小说ID
uv run run.py 1043294775

# --- 仅测试API连接 ---
uv run run.py --test-connections
```

所有生成的数据，包括缓存和最终视频，都将保存在 `data/book/{book_id}/` 目录下。

-----

## 🏛️ 架构概览

TaleStreamAI 的核心是一个四阶段的异步流水线 (`app/pipeline.py`)：

1.  **Content Stage (`app/stages/content.py`)**:

      * 负责从网络或本地文件获取原始小说文本。
      * 将文本分割成章节 (`Chapter` 对象)。

2.  **Storyboard Stage (`app/stages/storyboard.py`)**:

      * 接收 `Chapter` 对象，通过LLM将其内容转化为分镜脚本。
      * 对每个分镜的描述进行二次LLM调用，优化为高质量的图像生成Prompt。
      * 输出包含完整视觉指令的 `Shot` 对象列表。

3.  **Assets Stage (`app/stages/assets.py`)**:

      * 接收 `Shot` 对象列表。
      * **并行处理**:
          * 使用 `asyncio` 并发调用TTS和图像API，生成音频和图片。
          * 使用 `ProcessPoolExecutor` 将CPU密集型的视频片段合成任务分发到不同进程，避免阻塞。
      * 输出被媒体文件路径填充了的 `Shot` 对象。

4.  **Finalizer Stage (`app/stages/finalizer.py`)**:

      * 接收已处理的 `Shot` 对象列表。
      * 使用 `ffmpeg` 高效地将所有视频片段合并为最终的MP4文件。
      * 同时合并所有字幕，生成一个与视频匹配的 `.srt` 文件。
