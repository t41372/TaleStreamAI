#!/usr/bin/env python3
"""
測試流式分鏡生成功能
"""

import sys
from pathlib import Path

# 添加項目根目錄到路徑
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.board import generate_board_json

def main():
    print("🎬 開始測試流式分鏡生成...")
    print("=" * 60)
    
    # 測試內容
    test_content = """
鼻骨断了？我一下揪住了蚊子的衣服，说：「我还要打！你想办法！」

「别打了！西毒，再打下去你真就没命了！」李哥死死的握着我的手说：「认输吧，我对裁判说我们认输！」

「别！」我一下揪住了李哥的领子，死死的拉着，「李哥，别认输，别，我求你了！」

「你想死啊！」李哥喊了起来。

「别认输！」我狠狠的揪着李哥的领子不松手，扭头对蚊子说：「快想办法！」
"""
    
    print(f"📝 測試內容長度: {len(test_content)} 字符")
    print(f"📄 測試內容預覽:\n{test_content[:200]}...\n")
    
    try:
        # 測試流式請求
        print("🌊 測試流式請求:")
        result_stream = generate_board_json(test_content, use_stream=True)
        
        if result_stream:
            print(f"\n🎉 流式測試成功!")
            print(f"📊 總共生成 {len(result_stream)} 個分鏡項目")
            
            print("\n📋 生成的分鏡詳情:")
            for i, item in enumerate(result_stream):
                print(f"\n  📌 分鏡 {i+1}:")
                print(f"     ID: {item.get('id')}")
                print(f"     文本: {item.get('text', '')[:80]}...")
                print(f"     中文鏡頭語言: {item.get('lensLanguage_cn', '')[:60]}...")
                print(f"     英文鏡頭語言: {item.get('lensLanguage_en', '')[:60]}...")
        else:
            print("❌ 流式測試失敗")
            
        print("\n" + "=" * 60)
        print("🔄 測試非流式請求進行對比:")
        
        # 測試非流式請求
        result_normal = generate_board_json(test_content, use_stream=False)
        
        if result_normal:
            print(f"\n✅ 非流式測試成功!")
            print(f"📊 總共生成 {len(result_normal)} 個分鏡項目")
        else:
            print("❌ 非流式測試失敗")
            
    except Exception as e:
        print(f"❌ 測試失敗: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
