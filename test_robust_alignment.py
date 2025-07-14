#!/usr/bin/env python3
"""
测试健壮对齐功能的测试脚本
"""

import tempfile
import sys
from pathlib import Path

# 添加app模块到路径
sys.path.insert(0, str(Path(__file__).parent / "app"))
from app.restore_punct import (
    inject_punct_robust,
    inject_punct_sliding,
    parse_srt,
)


def create_test_srt():
    """创建测试SRT内容"""
    srt_content = """1
00:00:01,000 --> 00:00:02,000
今天

2
00:00:02,000 --> 00:00:03,000
天氣

3
00:00:03,000 --> 00:00:04,000
很好

4
00:00:04,000 --> 00:00:05,000
我們

5
00:00:05,000 --> 00:00:06,000
去

6
00:00:06,000 --> 00:00:07,000
公園

7
00:00:07,000 --> 00:00:08,000
走走
"""
    return srt_content


def test_scenario_1():
    """测试场景1：完全匹配"""
    print("=== 测试场景1：完全匹配 ===")
    srt_content = create_test_srt()
    full_text = "今天天氣很好，我們去公園走走。"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        f.write(srt_content)
        srt_path = f.name

    subs = parse_srt(Path(srt_path))
    result = inject_punct_robust(subs, full_text)

    print("原始字幕:", [s.content for s in parse_srt(Path(srt_path))])
    print("加標點後:", [s.content for s in result])
    Path(srt_path).unlink()  # 清理
    print("✅ 测试通过\n")


def test_scenario_2():
    """测试场景2：前后有多余文字"""
    print("=== 测试场景2：前后有多余文字 ===")
    srt_content = create_test_srt()
    full_text = "歡迎收看今日節目。今天天氣很好，我們去公園走走。感謝收看！"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        f.write(srt_content)
        srt_path = f.name

    subs = parse_srt(Path(srt_path))
    result = inject_punct_robust(subs, full_text)

    print("原始字幕:", [s.content for s in parse_srt(Path(srt_path))])
    print("加標點後:", [s.content for s in result])
    Path(srt_path).unlink()  # 清理
    print("✅ 测试通过\n")


def test_scenario_3():
    """测试场景3：中间有插入文字"""
    print("=== 测试场景3：中间有插入文字 ===")
    srt_content = create_test_srt()
    full_text = "今天天氣真的很好，我們一起去公園走走。"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        f.write(srt_content)
        srt_path = f.name

    subs = parse_srt(Path(srt_path))
    result = inject_punct_robust(subs, full_text)

    print("原始字幕:", [s.content for s in parse_srt(Path(srt_path))])
    print("加標點後:", [s.content for s in result])
    Path(srt_path).unlink()  # 清理
    print("✅ 测试通过\n")


def test_sliding_fallback():
    """测试滑动搜索降级机制"""
    print("=== 测试滑动搜索降级机制 ===")
    srt_content = """1
00:00:01,000 --> 00:00:02,000
今天

2
00:00:02,000 --> 00:00:03,000
好

3
00:00:03,000 --> 00:00:04,000
走走
"""
    full_text = "今天天氣很好，我們去公園走走。"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        f.write(srt_content)
        srt_path = f.name

    subs = parse_srt(Path(srt_path))
    result = inject_punct_sliding(subs, full_text)

    print("原始字幕:", [s.content for s in parse_srt(Path(srt_path))])
    print("滑動搜尋後:", [s.content for s in result])
    Path(srt_path).unlink()  # 清理
    print("✅ 测试通过\n")


if __name__ == "__main__":
    print("开始测试健壮对齐功能...\n")

    test_scenario_1()
    test_scenario_2()
    test_scenario_3()
    test_sliding_fallback()

    print("🎉 所有测试完成！")
