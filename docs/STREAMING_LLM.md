# 流式大語言模型實現說明

## 🌊 概述
TaleStreamAI 現在支持流式請求大語言模型，可以實時查看模型的推理過程和輸出，大大提升了用戶體驗和調試效率。

## ✨ 實現的功能

### 1. 分鏡生成流式輸出
- **實時推理過程**：可以看到模型如何逐步分析小說內容並生成分鏡
- **視覺化進度**：每個處理塊都有詳細的狀態報告
- **JSON解析監控**：實時顯示JSON生成和解析過程

### 2. 提示詞生成流式輸出
- **圖片提示詞實時生成**：看到模型如何將文本轉換為圖片描述
- **推理過程可視化**：觀察模型的創作思路

### 3. 增強的錯誤處理
- **詳細錯誤信息**：包含行號、列號等詳細JSON解析錯誤
- **智能重試機制**：失敗時自動重試並顯示進度
- **JSON修復功能**：自動嘗試修復常見的JSON格式問題

## 🔧 技術實現

### LLM客戶端更新
```python
# 支持流式和非流式請求
client.chat_completion_stream(messages, model)
client.chat_completion(messages, model, stream=True)
```

### 流式響應處理
```python
for chunk in response_stream:
    if chunk.choices[0].delta.content is not None:
        chunk_content = chunk.choices[0].delta.content
        print(chunk_content, end='', flush=True)
        full_content += chunk_content
```

## 📊 用戶體驗改進

### 進度可視化
```
============================================================
第 1 次嘗試生成分鏡...
============================================================
🚀 開始流式生成分鏡...

📝 模型推理過程和輸出:
----------------------------------------
[實時JSON內容生成...]
----------------------------------------
✅ 流式響應完成

🔧 處理響應內容...
🔍 嘗試解析JSON...
✅ 分鏡生成成功！第1次嘗試
📊 生成了 6 個分鏡項目
```

### 詳細狀態報告
- 📝 內容長度統計
- 🔄 分塊處理進度
- ✅ 成功/失敗狀態
- 📊 生成結果摘要

## 🎯 適用場景

### 1. 開發調試
- **API問題診斷**：實時查看API響應狀態
- **內容分析**：了解模型如何理解和處理文本
- **性能監控**：觀察處理速度和效率

### 2. 用戶體驗
- **進度反饋**：用戶知道系統正在工作
- **透明度**：可以看到AI的思考過程
- **信任建立**：增加對AI處理結果的信心

### 3. 內容創作
- **創作靈感**：觀察AI的創作思路
- **質量控制**：實時評估生成內容的質量
- **過程理解**：學習AI如何進行創意工作

## 🔧 配置選項

### 啟用/禁用流式模式
```python
# 分鏡生成
generate_board_json(content, use_stream=True)  # 流式
generate_board_json(content, use_stream=False) # 非流式

# 提示詞生成
refine_prompt(text, board_info, client, use_stream=True)  # 流式
refine_prompt(text, board_info, client, use_stream=False) # 非流式
```

### 環境變量配置
所有支持OpenAI兼容的API都可以使用流式功能：
- Gemini API
- 阿里雲通義千問
- DeepSeek API
- OpenAI API
- 其他兼容服務

## 🚀 使用示例

### 測試流式功能
```bash
# 測試流式分鏡生成
python test_stream.py

# 測試完整流程
python test_board.py

# 查看API配置
uv run config_llm.py show

# 測試API連接
uv run main.py --test-api
```

## 🎉 效果展示

### 流式分鏡生成示例
```
🚀 開始流式生成分鏡...
📝 模型推理過程和輸出:
----------------------------------------
[
    {
        "id": "1",
        "text": "鼻骨断了？我一下揪住了蚊子的衣服，说：「我还要打！你想办法！」",
        "lensLanguage_cn": "年轻男子，揪衣服、说话，格斗场馆，急切、愤怒，写实，中景，明亮灯光",
        "lensLanguage_en": "young man, grabbing clothes, speaking..."
    },
    ...
]
----------------------------------------
✅ 流式響應完成
```

## 📈 性能優勢

1. **用戶體驗**：不再是黑盒等待，可以看到實時進度
2. **調試效率**：立即發現問題，無需等待完整響應
3. **透明度**：了解AI的工作原理和思考過程
4. **靈活性**：可以選擇使用流式或非流式模式

這個流式實現讓TaleStreamAI的AI處理過程變得完全透明和可觀察，大大提升了開發和使用體驗！
