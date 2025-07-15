#!/usr/bin/env python3
"""
测试字幕处理流程
用于验证 restore_punct.py -> merge_srt.py -> burn-in 流程
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.stages.finalizer import _post_process_subtitles


async def test_subtitle_processing():
    """测试字幕处理流程"""
    # 创建测试目录
    test_dir = Path("test_subtitles")
    test_dir.mkdir(exist_ok=True)
    
    # 创建模拟的完整文本
    full_text = """这是一个测试小说。
    主人公小明走在路上，遇到了很多有趣的事情。
    他看到了美丽的风景，听到了鸟儿的歌声。
    这真是一个美好的一天。"""
    
    (test_dir / "full_text.txt").write_text(full_text, encoding="utf-8")
    
    # 创建模拟的 word-level SRT
    srt_content = """1
00:00:00,000 --> 00:00:01,000
这

2
00:00:01,000 --> 00:00:02,000
是

3
00:00:02,000 --> 00:00:03,000
一

4
00:00:03,000 --> 00:00:04,000
个

5
00:00:04,000 --> 00:00:05,000
测

6
00:00:05,000 --> 00:00:06,000
试

7
00:00:06,000 --> 00:00:07,000
小

8
00:00:07,000 --> 00:00:08,000
说"""
    
    test_srt = test_dir / "test.srt"
    test_srt.write_text(srt_content, encoding="utf-8")
    
    print("测试输入文件:")
    print(f"  - 完整文本: {test_dir / 'full_text.txt'}")
    print(f"  - 原始SRT: {test_srt}")
    
    try:
        # 运行字幕处理流程
        result_srt = await _post_process_subtitles(test_dir, test_srt)
        
        print("\n处理结果:")
        print(f"  - 句级SRT: {result_srt}")
        
        if result_srt.exists():
            print("\n句级SRT内容:")
            print(result_srt.read_text(encoding="utf-8"))
        else:
            print("❌ 句级SRT文件不存在")
            
        # 检查中间文件
        punct_srt = test_srt.with_suffix(".punct.srt")
        if punct_srt.exists():
            print("\n标点恢复SRT内容:")
            print(punct_srt.read_text(encoding="utf-8"))
        else:
            print("⚠️ 标点恢复SRT文件不存在")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_subtitle_processing())
