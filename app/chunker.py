"""Split multilingual text into non‑overlapping chunks near a token limit.

默认针对 **中文**，亦兼容英文及其他语言。
"""

from __future__ import annotations

import re
import sys
import pathlib
import subprocess
from typing import Iterable, List, Iterator, Tuple

import tiktoken

# +++ 引入我们自己的数据模型 +++
from .models import TextChunk

try:
    import spacy
except ImportError as err:  # pragma: no cover
    raise RuntimeError("spaCy is required: `pip install spacy`") from err

__all__ = [
    "chunk_text",
    "chunk_file",
    "DEFAULT_TOKEN_LIMIT",
    "DEFAULT_ENCODING",
]

DEFAULT_TOKEN_LIMIT = 1000
DEFAULT_ENCODING = "o200k_base"

_SENT_PUNCTS = re.compile(r"(?<=[.!?。！？；;])\s+")  # fallback splitter


def _ensure_spacy_model() -> "spacy.language.Language":
    """Load a spaCy model; auto‑download if missing.

    Preference order:
      1. zh_core_web_sm (better sentence segmentation for中文)
      2. xx_sent_ud_sm (universal UD sentence model)
    """
    for model in ("zh_core_web_sm", "xx_sent_ud_sm"):
        try:
            return spacy.load(model, disable=["tokenizer", "tagger", "parser", "ner", "lemmatizer"])
        except OSError:
            # auto download
            try:
                subprocess.run(
                    [sys.executable, "-m", "spacy", "download", model],
                    check=True,
                    capture_output=True,
                )
                return spacy.load(
                    model, disable=["tokenizer", "tagger", "parser", "ner", "lemmatizer"]
                )
            except subprocess.CalledProcessError:
                continue
    raise RuntimeError("无法加载或下载 spaCy 语言模型 (zh_core_web_sm / xx_sent_ud_sm)")


_NLP = None  # lazy‑loaded


def _get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = _ensure_spacy_model()
    return _NLP


def _sentences(text: str) -> Iterable[str]:
    """Yield sentences using spaCy; fallback to naive splitting if spaCy fails."""
    try:
        nlp = _get_nlp()
        for sent in nlp(text).sents:
            yield sent.text
    except Exception:  # pragma: no cover – fallback path
        # naive split by punctuation with keeping delimiter
        parts = re.split(r"([.!?。！？；;]+)", text)
        sent = ""
        for piece in parts:
            sent += piece
            if _SENT_PUNCTS.match(piece) or piece.strip() in "。！？.!?;；":
                yield sent
                sent = ""
        if sent:
            yield sent


def _num_tokens(text: str, enc) -> int:
    return len(enc.encode(text))


# +++ Step 1: 将原 chunk_text 重构为内部生成器，返回块和索引 +++
def _iter_chunks(
    text: str,
    token_limit: int,
    enc,
) -> Iterator[Tuple[str, int, int]]:
    """
    内部生成器，yields (chunk_text, start_char_index, end_char_index).
    这部分是纯粹的分块逻辑。
    """
    current: List[str] = []
    current_tokens = 0
    char_start_index = 0

    def flush(current_char_end_index: int) -> Tuple[str, int, int]:
        nonlocal current, current_tokens, char_start_index
        chunk_text = "".join(current)
        chunk_indices = (chunk_text, char_start_index, current_char_end_index)
        char_start_index = current_char_end_index
        current = []
        current_tokens = 0
        return chunk_indices

    char_cursor = 0
    for sentence in _sentences(text):
        sent_len = len(sentence)
        sent_tokens = _num_tokens(sentence, enc)

        if sent_tokens > token_limit:
            # 尝试子分割
            subs = re.split(r"([,，、;；])", sentence)
            combined = (
                ["".join(pair) for pair in zip(subs[0::2], subs[1::2] + [""])]
                if len(subs) > 1
                else [sentence]
            )

            for sub in combined:
                sub_len = len(sub)
                sub_tokens = _num_tokens(sub, enc)
                if current_tokens + sub_tokens > token_limit and current:
                    yield flush(char_cursor)
                
                current.append(sub)
                current_tokens += sub_tokens
                char_cursor += sub_len
        else:
            if current_tokens + sent_tokens > token_limit and current:
                yield flush(char_cursor)
            
            current.append(sentence)
            current_tokens += sent_tokens
            char_cursor += sent_len

    if current:
        yield flush(len(text))


# +++ Step 2: 创建新的公共函数，返回流水线所需的数据模型 +++
def chunk_text(
    text: str,
    token_limit: int = DEFAULT_TOKEN_LIMIT,
    encoding_name: str = DEFAULT_ENCODING,
) -> List[TextChunk]:
    """
    将文本分割成 TextChunk 对象列表，每个对象的token数约等于 token_limit。
    这是提供给应用程序其他部分的公共API。
    """
    if not text:
        return []

    enc = tiktoken.get_encoding(encoding_name)
    chunks = []
    chunk_id_counter = 0

    for chunk_text, start_idx, end_idx in _iter_chunks(text, token_limit, enc):
        chunks.append(
            TextChunk(
                chunk_id=chunk_id_counter,
                text=chunk_text,
                char_start_index=start_idx,
                char_end_index=end_idx,
            )
        )
        chunk_id_counter += 1

    # 完整性检查：确保所有块连接起来等于原始文本
    reconstructed_text = "".join(c.text for c in chunks)
    if reconstructed_text != text:
        # 在开发中，这是一个关键的断言，确保我们的逻辑没有引入间隙或重叠
        raise AssertionError("分块后合并文本与原始文本不一致；请检查 _iter_chunks 实现")

    return chunks


def chunk_file(
    path: str | pathlib.Path, token_limit: int = DEFAULT_TOKEN_LIMIT
) -> List[pathlib.Path]:
    """Chunk a file and write chunk_<idx>.txt next to it. Return list of chunk paths."""
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")
    # 注意: 这里返回的是 TextChunk 对象，而不是字符串。
    # chunk_file 的原始目的（写入 chunk_*.txt）可能需要重新审视，
    # 但我们暂时保持其行为，只写入文本部分。
    chunk_objects = chunk_text(text, token_limit)
    out_paths: List[pathlib.Path] = []
    for idx, ch_obj in enumerate(chunk_objects):
        out_path = path.with_name(f"chunk_{idx}.txt")
        out_path.write_text(ch_obj.text, encoding="utf-8")
        out_paths.append(out_path)
    return out_paths


if __name__ == "__main__":
    import argparse, textwrap

    parser = argparse.ArgumentParser(
        description="Split text file into non‑overlapping chunks near token limit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """示例:
              uv run -m app.chunker test_novel.txt -l 1024
            """,
        ),
    )
    parser.add_argument("file", help="文本文件路径")
    parser.add_argument("-l", "--limit", type=int, default=DEFAULT_TOKEN_LIMIT, help="token limit")
    args = parser.parse_args()
    paths = chunk_file(args.file, args.limit)
    print("生成 chunk 文件:")
    for p in paths:
        print("  ", p)
