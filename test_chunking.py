#!/usr/bin/env python3

import sys
from pathlib import Path
from chonkie import SentenceChunker

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.stages.storyboard import _create_semantic_chunks

def test_chunking():
    # Read the test novel
    with open("test_novel.txt", "r", encoding="utf-8") as f:
        content = f.read()
    
    print("=" * 50)
    print("原始文本开头 (前200个字符):")
    print(content[:200])
    print("=" * 50)
    
    # Test our chunking function
    chunks = _create_semantic_chunks(content, max_tokens=2500, model_name="gpt-4o")
    
    print(f"\n生成了 {len(chunks)} 个分块")
    print("=" * 50)
    
    for i, chunk in enumerate(chunks):
        print(f"分块 {i+1}:")
        print(f"长度: {len(chunk)} 字符")
        print(f"开头: {chunk[:100]}...")
        print(f"结尾: ...{chunk[-100:]}")
        print("-" * 30)
    
    # Test direct chonkie usage
    print("\n" + "=" * 50)
    print("直接使用 chonkie 测试:")
    
    chunker = SentenceChunker(
        tokenizer_or_token_counter="cl100k_base",
        chunk_size=2500,
        chunk_overlap=min(100, 2500 // 4),
        min_sentences_per_chunk=1
    )
    
    chunk_objects = chunker(content)
    direct_chunks = [chunk.text for chunk in chunk_objects]
    
    print(f"直接使用 chonkie 生成了 {len(direct_chunks)} 个分块")
    for i, chunk in enumerate(direct_chunks):
        print(f"分块 {i+1}:")
        print(f"长度: {len(chunk)} 字符")
        print(f"开头: {chunk[:100]}...")
        print(f"结尾: ...{chunk[-100:]}")
        print("-" * 30)
    
    # Compare first chunks
    print("\n" + "=" * 50)
    print("比较第一个分块:")
    print(f"我们的函数结果开头: {chunks[0][:50]}...")
    print(f"直接 chonkie 结果开头: {direct_chunks[0][:50]}...")
    
    # Check if there's any content loss
    combined_chunks = "".join(chunks)
    combined_direct = "".join(direct_chunks)
    
    print(f"\n原始文本长度: {len(content)}")
    print(f"我们的函数合并后长度: {len(combined_chunks)}")
    print(f"直接 chonkie 合并后长度: {len(combined_direct)}")
    
    if len(combined_chunks) != len(content):
        print("⚠️  警告：我们的函数可能丢失了内容！")
    
    if len(combined_direct) != len(content):
        print("⚠️  警告：直接 chonkie 可能丢失了内容！")
    
    # Check overlaps
    print(f"\n检查重叠:")
    for i in range(len(chunks) - 1):
        overlap_start = chunks[i][-50:]
        overlap_end = chunks[i+1][:50]
        print(f"分块 {i+1} 末尾: ...{overlap_start}")
        print(f"分块 {i+2} 开头: {overlap_end}...")
        print("-" * 20)

if __name__ == "__main__":
    test_chunking() 