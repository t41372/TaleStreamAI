# AI 小说推文自动化工作流

[成片-6小时](https://www.bilibili.com/video/BV1mmQvYEEwb/)
[爱发电](https://afdian.com/a/dmzw1918)

## 项目结构

```
.
├── app/                    # 应用核心模块
├── data/
│   └── book/              # 书籍数据
├── docs/                  # 文档
├── tests/                 # 测试
├── pyproject.toml         # 项目配置（唯一依赖管理来源）
└── README.md
```

## 项目使用到的技术

- **语音合成**: Microsoft Edge TTS (替代 CosyVoice)
- **图像生成**: Flux API via Pollinations.ai (替代 Stable Diffusion)
- **大模型**: DeepSeek-V3, Gemini-2.0-flash
- **视频处理**: FFmpeg GPU 加速版

## 项目流程

| 文件名       | 功能           | 技术栈                   |
| ------------ | -------------- | ------------------------ |
| main.py      | 获取书籍内容   | 爬虫 + 本地文件支持      |
| board.py     | 生成章节分镜   | Gemini-2.0-flash         |
| prompt.py    | 润色分镜提示词 | DeepSeek-v3              |
| image.py     | 生成图片       | Flux API                 |
| audio.py     | 生成音频       | Edge TTS + 异步并发      |
| tts.py       | 生成字幕       | Edge TTS 原生字幕        |
| video.py     | 生成视频       | FFmpeg GPU 加速版        |
| video_end.py | 生成完整视频   | FFmpeg GPU 加速版        |

## 本地运行

> 本项目使用 **uv** 来管理依赖，建议 Python 版本 `>=3.12`

### 1. 安装 uv

```shell
# 通过 pip 安装
pip install uv

# 或通过官方安装脚本（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆项目并设置环境

```shell
git clone https://github.com/t41372/TaleStreamAI.git
cd TaleStreamAI

# 创建虚拟环境并安装依赖（一步完成）
uv sync
```

### 3. 激活虚拟环境

```shell
# Windows
.venv\Scripts\activate

# macOS/Linux  
source .venv/bin/activate
```

### 4. 环境配置

复制 `.env.example` 文件，改名为 `.env` 并配置API密钥：

```bash
# 大模型配置
STORYBOARD_API_KEY=your_gemini_api_key      # 分镜生成
PROMPT_API_KEY=your_deepseek_api_key        # 提示词优化

# LLM 并发配置
LLM_THREADS=3                               # LLM API 最大并发数
VERBOSE_LOGGING=true                        # 开启详细日志

# Edge TTS 配置  
EDGE_TTS_VOICE=zh-CN-YunxiNeural           # 中文语音
AUDIO_THREADS=5                             # 音频生成并发数

# Flux 图像生成配置
FLUX_WIDTH=1024
FLUX_HEIGHT=1024
FLUX_ENHANCE=false                          # 默认关闭图像增强
```

**关于起点小说**: 如需抓取起点小说，请配置 `COOKIE` 为起点达人中心的Cookie [起点达人中心](https://koc.yuewen.com/home)

### 5. 安装 FFmpeg（可选，用于视频生成）

推荐安装GPU加速版 FFmpeg: [Github Releases](https://github.com/BtbN/FFmpeg-Builds/releases)

检查硬件加速支持:
```shell
ffmpeg -hwaccels
```

## 运行项目

### 快速开始（推荐）

```shell
# 在线小说处理
uv run main.py 1043294775

# 本地小说文件处理  
uv run main.py novel.txt

# 指定自定义书籍ID
uv run main.py novel.txt my_book_id
```

### 分步执行

```shell
# 逐步执行各个阶段
uv run python app/main.py      # 获取小说内容
uv run python board.py         # 生成分镜
uv run python prompt.py        # 优化提示词
uv run python image.py         # 生成图片
uv run python audio.py         # 合成音频  
uv run python tts.py           # 生成字幕
uv run python video.py         # 制作分镜视频
uv run python video_end.py     # 最终合成
```

### API 连接测试

```shell
# 测试所有API连接
uv run main.py --test-api
```

## 核心优势

### v0.2.0 重大更新

1. **无需复杂部署**: 
   - 移除 Stable Diffusion 本地部署需求
   - 移除 Whisper 模型下载需求
   - 使用云端 API 服务，开箱即用

2. **更高性能**:
   - 异步并发处理，大幅提升速度
   - Edge TTS 原生字幕，准确性更高
   - 环境变量控制并发数，适应不同硬件

3. **更稳定可靠**:
   - Microsoft Edge TTS 服务稳定
   - 完善的错误处理和重试机制
   - 详细的日志记录，便于调试

4. **灵活易用**:
   - 支持本地 TXT 文件处理
   - 自动章节分割
   - 向后兼容原有工作流

## 开发指南

### 添加新依赖

```shell
# 添加生产依赖
uv add package_name

# 添加开发依赖  
uv add --dev package_name
```

### 运行测试

```shell
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_edge_tts.py -v
```

### 代码格式化

```shell
# 格式化代码
uv run black .
```

## 故障排除

### 常见问题

1. **Edge TTS 连接失败**
   - 检查网络连接
   - 确认防火墙设置
   - 尝试更换语音模型

2. **LLM API 调用失败**  
   - 验证 API 密钥正确性
   - 检查 API 额度和限制
   - 调整并发数 `LLM_THREADS`

3. **内存不足**
   - 降低并发数 `AUDIO_THREADS` 和 `LLM_THREADS`
   - 减少批处理大小
   - 考虑分批处理长文本

### 日志调试

开启详细日志以获得更多调试信息：

```bash
VERBOSE_LOGGING=true uv run main.py novel.txt
```

## 许可证

[License 信息]

## 贡献

欢迎提交 Issue 和 Pull Request！
