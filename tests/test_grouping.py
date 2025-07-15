import sys
from pathlib import Path
import srt

sys.path.append(str(Path(__file__).resolve().parents[1]))
from word_srt_to_sentence import group_word_by_word_srt


def test_group_word_by_word_srt():
    with open("test.srt", "r", encoding="utf-8") as f:
        words = list(srt.parse(f.read()))
    grouped = group_word_by_word_srt(words, max_line_length=20, max_pause_seconds=0.5)
    assert len(grouped) < len(words)
