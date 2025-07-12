# AI 小说推文自动化工作流

[成片-6小时](https://www.bilibili.com/video/BV1mmQvYEEwb/)
[爱发电](https://afdian.com/a/dmzw1918)

## 项目结构

```
.
├── app
├── data
│   │─ book
├── README.md
└── requirements.txt
```

## 项目使用到的大模型

-   DeepSeek-V3
-   gemini-2.0-flash
-   Edge TTS
-   flux 文生图 API

## 项目流程

| 文件名       | 功能           | 模型/库                  |
| ------------ | -------------- | ------------------------ |
| main.py      | 获取书籍内容   | 无                       |
| board.py     | 生成章节分镜   | gemini-2.0-flash         |
| prompt.py    | 润色分镜提示词 | deepseek-v3              |
| image.py     | 生成图片       | flux API                |
| audio.py     | 生成音频/字幕  | Edge TTS                |
| video.py     | 生成视频       | ffmpeg-gpu 加速版        |
| video_end.py | 生成完整视频   | ffmpeg-gpu 加速版        |

## 本地运行

> 本项目使用的是`uv`来管理依赖,建议 python 版本`>=3.12`

1. 安装`uv`

```shell
pip install uv
```

2. 创建虚拟环境

```shell
uv venv --python 3.12
```

```sh
    .\.venv\Scripts\activate
```

3. 安装包

```shell
uv add -r requirements.txt
```

4. 安装 torch 环境
    > torch 环境请根据你系统的 cuda 版本来安装 [torch 官网](https://pytorch.org/)

```sh
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

可以通过`nvidia-smi`来查询你的显卡支持的最高`cuda`版本

```sh
nvidia-smi
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 560.94                 Driver Version: 560.94         CUDA Version: 12.6     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 4070 Ti   WDDM  |   00000000:01:00.0  On |                  N/A |
|  0%   28C    P8              4W /  285W |    2157MiB /  12282MiB |      2%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

通过 `nvcc` 来查询你电脑已安装的`cuda`版本

> 其实是你环境变量中配置的版本而已，一个电脑上可以安装多个 cuda

```sh
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2022 NVIDIA Corporation
Built on Wed_Sep_21_10:41:10_Pacific_Daylight_Time_2022
Cuda compilation tools, release 11.8, V11.8.89
Build cuda_11.8.r11.8/compiler.31833905_0
```

## 环境配置

复制 `.env.example` 文件，改名为 `.env`  
配置其缺少的 APIKey  
其中 `AUDIO_API_KEY` 是可以支持多 Key 轮询的，用`,`分割  
(做到这一步我才意识到可以多 Key 支持高并发 😂 如果需 Gemini 需要高并发的话，可能需要手动去 copy 多 key 的处理的代码到`board.py`中了)   
配置`起点达人中心`的 Cookie 用来抓取小说 [起点达人中心](https://koc.yuewen.com/home)  
安装`ffmpeg`最好安装GPU加速版，否则生成的很慢(好像新一点的版本都已经支持gpu加速了) [Github](https://github.com/BtbN/FFmpeg-Builds/releases)  
使用 `ffmpeg -hwaccels` 来列出硬件加速选项
```sh
Hardware acceleration methods:
cuda
vaapi
dxva2
qsv
d3d11va
opencl
vulkan
```

## 运行项目

我是直接按照项目流程来逐个运行文件的 

```sh
uv run app/main.py     # 获取小说内容
uv run board.py    # 生成分镜
uv run prompt.py   # 优化提示词
uv run image.py    # 生成图片
uv run audio.py    # 合成音频  
uv run tts.py      # 生成字幕
uv run video.py    # 制作分镜视频
uv run video_end.py # 最终合成
```

如果你想要直接运行 也可以直接运行 main.py
```sh
uv run main.py
```

