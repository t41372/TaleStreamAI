#!/usr/bin/env python3
"""
測試分鏡生成功能
"""

import sys
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.board import generate_board

def main():
    print("開始測試分鏡生成...")
    success = generate_board("test_novel")
    if success:
        print("✅ 分鏡生成成功!")
    else:
        print("❌ 分鏡生成失敗!")

if __name__ == "__main__":
    main()
