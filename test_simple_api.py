#!/usr/bin/env python3
"""
簡單的API測試
"""

import sys
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.llm_client import get_storyboard_client

def main():
    print("開始簡單API測試...")
    
    try:
        client = get_storyboard_client()
        print(f"客戶端配置: {client.base_url}")
        print(f"模型: {client.model}")
        
        # 簡單測試
        print("發送簡單請求...")
        response = client.chat_completion(
            messages=[
                {"role": "user", "content": "請回覆：你好"}
            ]
        )
        
        content = response.choices[0].message.content
        print(f"響應: {content}")
        print("✅ 簡單測試成功!")
        
    except Exception as e:
        print(f"❌ 測試失敗: {str(e)}")

if __name__ == "__main__":
    main()
