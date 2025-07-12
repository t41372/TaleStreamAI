# TaleStreamAI - Edge TTS版本

AI驱动的小说转视频生成流水线，使用Edge TTS和Flux进行语音合成和图像生成。

## 主要变更

### v0.2.0 - Edge TTS重构版

1. **语音合成替换**: 从CosyVoice API替换为Microsoft Edge TTS
   - 更稳定的语音合成服务
   - 内置字幕生成功能
   - 支持多种中文语音
   - 增加异步并发处理

2. **图像生成升级**: 从Stable Diffusion替换为Flux API
   - 使用Pollinations.ai的Flux API
   - 更简单的API调用，无需本地部署
   - 更高质量的图像生成

3. **字幕生成优化**: 使用Edge TTS原生字幕功能
   - 自动标点符号恢复
   - 更准确的时间同步
   - 移除对Whisper的依赖

4. **本地文件支持**: 增加本地TXT文件处理功能
   - 支持本地小说文件作为输入
   - 自动章节分割
   - 灵活的文件处理

## 安装和使用

### 环境要求

- Python ≥ 3.12
- 网络连接（用于Edge TTS和Flux API）

### 安装依赖

```bash
pip install -r requirements.txt
# 或使用 uv
uv add -r requirements.txt
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并配置以下参数：

```bash
# Edge TTS 配置
EDGE_TTS_VOICE=zh-CN-XiaoyiNeural     # Edge TTS 语音
AUDIO_THREADS=5                       # 音频生成最大并发数
USE_ASYNC_AUDIO=true                  # 是否使用异步音频生成

# Flux 图像生成配置
FLUX_WIDTH=1024
FLUX_HEIGHT=1024
FLUX_MODEL=flux
FLUX_ENHANCE=false

# 其他配置...
```

### 使用方法

#### 1. 处理网络小说（起点中文网）

```bash
python main.py 1043294775
```

#### 2. 处理本地TXT文件

```bash
# 使用文件名作为书籍ID
python main.py novel.txt

# 指定自定义书籍ID
python main.py novel.txt my_book_id
```

#### 3. 分步处理

```bash
# 1. 获取/解析小说内容
python -m app.main novel.txt

# 2. 生成分镜
python -m app.board my_book_id

# 3. 生成图片
python -m app.image my_book_id

# 4. 生成音频和字幕
python -m app.audio my_book_id

# 5. 验证字幕
python -m app.tts my_book_id

# 6. 生成视频
python -m app.video my_book_id
python -m app.video_end my_book_id
```

## 新功能详解

### Edge TTS集成

Edge TTS提供高质量的中文语音合成：

- **多种语音选择**: 支持多种中文语音角色
- **异步并发**: 使用asyncio和semaphore进行并发处理
- **字幕同步**: 自动生成时间同步的SRT字幕文件
- **标点恢复**: 智能恢复原文中的标点符号

### Flux图像生成

使用Pollinations.ai的Flux API：

- **无需本地部署**: 直接调用云端API
- **高质量输出**: Flux模型提供更好的图像质量
- **灵活配置**: 支持多种参数调节

### 本地文件支持

新增本地TXT文件处理：

- **自动章节分割**: 基于"第X章"模式自动分割
- **灵活命名**: 支持自定义书籍ID
- **标准流程**: 与网络小说使用相同的处理流程

## 测试

运行测试套件：

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_edge_tts.py -v

# 运行测试并显示覆盖率
pytest tests/ --cov=app
```

## 性能优化

### 并发处理

- **音频生成**: 使用asyncio进行并发音频生成
- **可配置并发数**: 通过`AUDIO_THREADS`环境变量调节
- **信号量控制**: 防止过多并发请求

### 资源管理

- **内存优化**: 及时释放大型对象
- **错误处理**: 完善的错误处理和重试机制
- **进度跟踪**: 使用tqdm显示处理进度

## 故障排除

### 常见问题

1. **网络连接问题**
   - Edge TTS需要访问speech.platform.bing.com
   - Flux API需要访问image.pollinations.ai
   - 检查网络连接和防火墙设置

2. **语音生成失败**
   - 检查EDGE_TTS_VOICE配置
   - 尝试降低AUDIO_THREADS并发数
   - 查看错误日志获取详细信息

3. **图像生成问题**
   - 检查FLUX_*环境变量配置
   - 验证网络连接到Pollinations.ai
   - 尝试简化提示词

### 日志和调试

- 错误日志保存在对应的.txt文件中
- 使用`-v`参数运行pytest获取详细测试信息
- 检查生成的中间文件确认处理状态

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 许可证

本项目采用原项目相同的许可证。