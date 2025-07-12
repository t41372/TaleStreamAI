# 大模型API配置說明

## 概述
TaleStreamAI 現在支持統一的 OpenAI 兼容 API 配置，可以靈活配置不同功能使用不同的大模型服務。

## 配置項說明

### 主要配置（推薦）

#### 分鏡生成模型配置
```env
STORYBOARD_API_KEY=your_api_key_here
STORYBOARD_API_URL=https://api.provider.com/v1
STORYBOARD_MODEL=model_name
```

#### 圖片提示詞生成模型配置
```env
PROMPT_API_KEY=your_api_key_here
PROMPT_API_URL=https://api.provider.com/v1
PROMPT_MODEL=model_name
```

### 備用配置
系統會自動回退到這些配置：
```env
# 阿里雲通義千問配置
AL_API_KEY=your_alibaba_api_key
AL_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# Gemini API配置
GEMINI_API_KEY=your_gemini_api_key
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

## 支持的API提供商

### 1. Google Gemini
```env
API_URL=https://generativelanguage.googleapis.com/v1beta/openai/
MODEL=gemini-2.0-flash
```

### 2. 阿里雲通義千問（兼容模式）
```env
API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL=deepseek-v3
```

### 3. OpenAI
```env
API_URL=https://api.openai.com/v1
MODEL=gpt-4
```

### 4. 其他 OpenAI 兼容服務
只要支持 OpenAI 格式的 API，都可以使用：
- Claude (通過代理)
- 國內各種代理服務
- 本地部署的模型（如 Ollama）

## 配置優先級

### 分鏡生成 (Storyboard)
1. `STORYBOARD_API_KEY` + `STORYBOARD_API_URL` + `STORYBOARD_MODEL`
2. `GEMINI_API_KEY` + `GEMINI_API_URL`
3. `AL_API_KEY` + `AL_API_URL`

### 提示詞生成 (Prompt)
1. `PROMPT_API_KEY` + `PROMPT_API_URL` + `PROMPT_MODEL`
2. `AL_API_KEY` + `AL_API_URL`
3. `GEMINI_API_KEY` + `GEMINI_API_URL`

## 自動模型選擇

系統會根據 API URL 自動選擇合適的模型：
- 如果 URL 包含 `dashscope.aliyuncs.com`，默認使用 `deepseek-v3`
- 如果 URL 包含 `generativelanguage.googleapis.com`，默認使用 `gemini-2.0-flash`
- 其他情況默認使用配置的模型或 `gemini-2.0-flash`

## 測試連接

可以使用以下命令測試所有API連接：
```bash
uv run main.py --test-api
```

## 配置示例

### 完整配置示例
```env
# 分鏡生成使用 Gemini
STORYBOARD_API_KEY=AIzaSy...
STORYBOARD_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/
STORYBOARD_MODEL=gemini-2.0-flash

# 提示詞生成使用阿里雲
PROMPT_API_KEY=sk-...
PROMPT_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PROMPT_MODEL=deepseek-v3

# 備用配置
AL_API_KEY=sk-...
AL_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
GEMINI_API_KEY=AIzaSy...
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta/openai/
```

### 簡化配置示例（使用同一個API）
```env
# 所有功能都使用同一個API
STORYBOARD_API_KEY=your_api_key
STORYBOARD_API_URL=https://your.api.provider.com/v1
STORYBOARD_MODEL=your_model

# 這些會自動回退到上面的配置
# PROMPT_API_KEY=
# PROMPT_API_URL=
# PROMPT_MODEL=
```

## 注意事項

1. **API Key 安全**：請勿將 API Key 提交到版本控制系統
2. **模型選擇**：不同模型對分鏡生成和提示詞生成的效果可能不同
3. **回退機制**：如果主要配置失敗，系統會自動嘗試備用配置
4. **成本考慮**：不同 API 提供商的定價不同，請合理選擇
