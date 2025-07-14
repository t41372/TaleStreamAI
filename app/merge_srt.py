"""
把「字級」SRT 轉成「句級」SRT
規則：
  1. 與前一字幕間隔 ≤ 250 ms 才能併入同句
  2. 同句總字數 ≤ 7
輸出：原檔名 + '.sentence.srt'
"""

import re
import sys
import datetime as dt
from pathlib import Path
from typing import List
import srt

GAP_THRESHOLD_MS = 250
MAX_CHARS = 9


# ------------------------------------------------------------
def _ms(td: dt.timedelta) -> int:
    """timedelta 轉毫秒"""
    return int(td.total_seconds() * 1000)


def _stripped_len(txt: str) -> int:
    """計算字數（去掉空格與換行）"""
    return len(re.sub(r"\s+", "", txt))


def merge_subs(subs) -> List:
    merged = []
    if not subs:
        return merged

    current = subs[0]
    cur_len = _stripped_len(current.content)

    for nxt in subs[1:]:
        gap = _ms(nxt.start - current.end)
        nxt_len = _stripped_len(nxt.content)

        can_merge = (gap <= GAP_THRESHOLD_MS) and (cur_len + nxt_len <= MAX_CHARS)

        if can_merge:
            # 合併文字與時間
            current.content += nxt.content
            current.end = nxt.end
            cur_len += nxt_len
        else:
            merged.append(current)
            current = nxt
            cur_len = nxt_len

    merged.append(current)
    # 重新編號
    for i, s in enumerate(merged, 1):
        s.index = i
    return merged


def compose_srt(subs) -> str:
    try:
        import srt

        return srt.compose(subs)
    except Exception:
        # fallback: 手動組裝
        out_lines = []
        for s in subs:
            out_lines.append(str(s.index))

            def _fmt(td):
                h, rem = divmod(int(td.total_seconds()), 3600)
                m, s2 = divmod(rem, 60)
                ms = td.microseconds // 1000
                return f"{h:02}:{m:02}:{s2:02},{ms:03}"

            out_lines.append(f"{_fmt(s.start)} --> {_fmt(s.end)}")
            out_lines.append(s.content)
            out_lines.append("")  # blank line
        return "\n".join(out_lines)


# ------------------------------------------------------------
def main(path: str):
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    try:
        subs = list(srt.parse(raw))
        new_subs = merge_subs(subs)
        out_text = compose_srt(new_subs)
        out_path = Path(path).with_suffix(".sentence.srt")
        out_path.write_text(out_text, encoding="utf-8")
        print(f"✅ Success!  Output: {out_path}")
    except Exception as e:
        # 讓外部系統可據此重跑
        sys.stderr.write(f"❌ Failed: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: python merge_srt.py <subtitle.srt>\n")
        sys.exit(2)
    main(sys.argv[1])
