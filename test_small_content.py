#!/usr/bin/env python3
"""
測試小內容塊的分鏡生成
"""

import sys
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.board import generate_board_json

def main():
    print("開始測試小內容塊分鏡生成...")
    
    # 測試小內容
    test_content = """
鼻骨断了？我一下揪住了蚊子的衣服，说：「我还要打！你想办法！」

「别打了！西毒，再打下去你真就没命了！」李哥死死的握着我的手说：「认输吧，我对裁判说我们认输！」

「别！」我一下揪住了李哥的领子，死死的拉着，「李哥，别认输，别，我求你了！」
"""
    
    try:
        result = generate_board_json(test_content)
        if result:
            print(f"✅ 生成成功! 共 {len(result)} 個分鏡")
            for item in result:
                print(f"ID: {item.get('id')}, Text: {item.get('text', '')[:50]}...")
        else:
            print("❌ 生成失敗")
            
    except Exception as e:
        print(f"❌ 測試失敗: {str(e)}")

if __name__ == "__main__":
    main()
