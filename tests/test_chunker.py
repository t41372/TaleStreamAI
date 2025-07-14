# -----------------------
# File: tests/test_chunker.py
"""Pytest test‑suite for text_chunker."""

import pathlib
from app.chunker import chunk_file, chunk_text, DEFAULT_TOKEN_LIMIT

TEST_DATA = pathlib.Path(__file__).parent / "test_novel.txt"


def test_roundtrip_default_limit():
    text = TEST_DATA.read_text(encoding="utf-8")
    chunks = chunk_text(text, DEFAULT_TOKEN_LIMIT)
    assert "".join(c.text for c in chunks) == text, "chunking produced gaps or overlaps"
    assert all(len(c.text) > 0 for c in chunks)


def test_various_limits():
    text = "这是一段中文。这是第二句。This is an English sentence. 这是第三句。"
    for limit in (128, 256, 512):
        chunks = chunk_text(text, limit)
        assert "".join(c.text for c in chunks) == text
        # ensure each chunk roughly <= limit (allow a small slack of 10%)
        import tiktoken

        enc = tiktoken.get_encoding("o200k_base")
        assert all(len(enc.encode(c.text)) <= limit * 1.1 for c in chunks)


def test_chunk_file_generation(tmp_path):
    temp_file = tmp_path / "sample.txt"
    temp_file.write_text("这是一句。" * 100, encoding="utf-8")
    out_paths = chunk_file(temp_file, 128)
    # ensure chunk files exist and reconstruct original
    assert out_paths
    recon = "".join(p.read_text(encoding="utf-8") for p in out_paths)
    assert recon == temp_file.read_text(encoding="utf-8")


# Clean up any chunk_*.txt accidentally left by manual runs


def teardown_module(module):  # noqa: D401  # pylint: disable=missing-function-docstring
    for f in TEST_DATA.parent.glob("chunk_*.txt"):
        try:
            f.unlink()
        except Exception:  # pragma: no cover
            pass
