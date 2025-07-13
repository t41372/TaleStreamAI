# TaleStreamAI - Edge TTS 版本更新文檔

## v0.2.1 - 詳細日誌和異步並發優化

### 核心改進

1. **移除 requirements.txt**
   - 現在使用 `pyproject.toml` 作為唯一的依賴管理來源
   - 支持 `uv sync` 和 `uv run` 的標準 Python 工作流
   - 清理了冗餘依賴，只保留必要的包

2. **詳細日誌系統**
   - 新增統一的日誌記錄模塊 `app/logger.py`
   - 支持詳細和簡潔兩種日誌模式
   - 通過 `VERBOSE_LOGGING=true` 開啟詳細日誌
   - 實時進度追蹤，用戶可清楚了解每個步驟的狀態

3. **異步 LLM 並發支持**
   - LLM 客戶端支持同步和異步調用
   - 通過信號量控制並發數量，避免 API 限制
   - 可通過 `LLM_THREADS` 環境變量調整並發數
   - 完善的錯誤處理和重試機制

4. **增強的 API 調用追蹤**
   - 每次 LLM 調用都有詳細的開始/成功/失敗日誌
   - 包含調用時間、重試次數、錯誤詳情
   - 支持批量異步調用和進度監控

### 新增環境變量

```bash
# LLM 並發配置
LLM_THREADS=3                           # LLM API 最大並發數
LLM_TIMEOUT=120                         # LLM API 請求超時時間(秒)
LLM_RETRY_ATTEMPTS=3                    # LLM API 重試次數
VERBOSE_LOGGING=true                    # 是否開啟詳細日誌
```

### 使用方式更新

#### 標準 uv 工作流

```bash
# 安裝依賴（推薦方式）
uv sync

# 運行應用
uv run main.py

# 運行測試
uv run pytest
```

#### 詳細日誌模式

```bash
# 開啟詳細日誌
VERBOSE_LOGGING=true uv run main.py novel.txt

# 調整並發設置
LLM_THREADS=5 AUDIO_THREADS=10 uv run main.py novel.txt
```

### 日誌輸出示例

#### 簡潔模式（默認）
```
INFO | 🚀 TaleStreamAI 開始運行...
INFO | 📖 處理書籍ID: test_novel
INFO | 🚀 開始執行: 生成章節分鏡
INFO | ✅ 完成: 生成章節分鏡 | 耗時: 15.3s | 生成 8 個分鏡項目
```

#### 詳細模式（VERBOSE_LOGGING=true）
```
15:23:45 | TaleStreamAI | INFO | 🚀 TaleStreamAI 開始運行...
15:23:45 | TaleStreamAI | INFO | 📖 處理書籍ID: test_novel
15:23:45 | TaleStreamAI | DEBUG | 初始化 storyboard 客戶端 | model=gemini-2.0-flash
15:23:45 | TaleStreamAI | INFO | 🔄 開始調用 STORYBOARD_LLM API | 模型: gemini-2.0-flash
15:23:47 | TaleStreamAI | INFO | ✅ STORYBOARD_LLM API 調用成功 | 耗時: 2.1s | 嘗試次數: 1
15:23:47 | TaleStreamAI | DEBUG | 收到API響應，內容長度: 1234 字符
15:23:47 | TaleStreamAI | DEBUG | 開始清理和解析響應內容...
15:23:47 | TaleStreamAI | INFO | ✅ 完成: 生成章節分鏡 | 耗時: 2.5s | 生成 8 個分鏡項目
```

### 異步並發示例

新的 LLM 客戶端支持批量異步調用：

```python
from app.llm_client import get_storyboard_client, batch_async_chat_completion

# 批量處理多個章節
client = get_storyboard_client()
messages_list = [
    [{"role": "user", "content": f"處理章節 {i}"}] 
    for i in range(10)
]

# 異步批量調用，自動控制並發數
results = await batch_async_chat_completion(
    client=client,
    messages_list=messages_list,
    worker_prefix="chapter"
)
```

### 錯誤處理改進

- **自動重試**: LLM 調用失敗時自動重試，支持指數退避
- **詳細錯誤信息**: 記錄完整的錯誤堆棧和上下文
- **優雅降級**: 部分組件失敗不會影響整體流程
- **資源清理**: 異常情況下正確釋放信號量和連接

### 性能優化

1. **並發控制**: 通過信號量避免過度並發導致的 API 限制
2. **連接復用**: 同步和異步客戶端分別管理，避免重複建立連接
3. **內存管理**: 大文本處理時及時釋放內存
4. **批處理**: 支持批量 API 調用，減少網絡開銷

### 向後兼容性

- 保持所有原有 API 接口不變
- 支持舊的環境變量配置
- 可通過環境變量禁用新功能
- 現有的數據格式和工作流程完全兼容

### 測試覆蓋

- 新增異步 LLM 調用測試
- 日誌系統功能測試
- 並發控制測試
- 錯誤處理和重試機制測試

這次更新大幅提升了用戶體驗，讓整個處理過程更加透明和可控。用戶可以實時了解每個步驟的進度，並根據需要調整並發設置以優化性能。