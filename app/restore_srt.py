#!/usr/bin/env python3
# restore_srt.py
"""
用『完整正文』恢復 SRT 標點，並依規則合併成句級字幕。

健壯對齊策略：
1. 優先使用 SequenceMatcher 全域對齊：自動處理前後多餘文字、中間插入/刪除
2. 失敗時降級至滑動搜尋：在局部範圍內尋找匹配位置
3. 部分對齊失敗時仍可輸出，並返回特殊退出碼

依賴：pip install srt
使用：python restore_srt.py raw.srt full.txt
      產出：raw.punct.srt  與  raw.sentence.srt

退出碼：
  0 - 完全成功
  1 - 嚴重錯誤
  2 - 參數錯誤
  100 - 部分對齊失敗但仍輸出（建議人工檢查）
"""

import re
import sys
import datetime as dt
import difflib
import warnings
from pathlib import Path
from typing import List

# ---------- 可調參數 ----------
GAP_THRESHOLD_MS = 250  # 同句內兩字最大間隔
MAX_CHARS = 7  # 同句最大字數
PUNCT = "，,。：:；;？?！!、…―—「」『』《》〈〉（）()""''"  # 常見中文標點

# ---------- 健壯對齊策略說明 ----------
"""
本腳本實現4種健壯對齊策略：

1. SequenceMatcher 全域對齊（主策略）：
   - 使用 difflib.SequenceMatcher 找出字幕串與全文的最長公共子序列
   - 自動處理前後多餘文字、中間插入/刪除的情況
   - 時間複雜度 O(N log N)，適用於大部分場景

2. 滑動搜尋對齊（降級策略）：
   - 當全域對齊失敗時，逐字幕在局部範圍內搜尋匹配位置
   - 容忍小幅度的字幕錯位和文字差異
   - 時間複雜度 O(N)，快速但可能有誤配

3. 退出碼機制：
   - 0: 完全成功
   - 100: 部分對齊失敗但仍輸出（建議人工檢查）
   - 1: 嚴重錯誤，2: 參數錯誤

4. 容錯處理：
   - 對齊失敗的字幕保持原樣輸出
   - 記錄詳細的警告信息供調試使用
"""
# ---------------------------


# ---------- utils ----------
def _ms(td: dt.timedelta) -> int:
    return int(td.total_seconds() * 1000)


def _strip_space(txt: str) -> str:
    return re.sub(r"\s+", "", txt)


def _safe_parse_time(t: str) -> dt.timedelta:
    h, m, s_ms = t.split(":")
    s, ms = s_ms.split(",")
    return dt.timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))


def _fmt_time(td: dt.timedelta) -> str:
    h, rem = divmod(int(td.total_seconds()), 3600)
    m, s = divmod(rem, 60)
    ms = td.microseconds // 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


# ---------------------------


def parse_srt(path: Path):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        import srt

        return list(srt.parse(raw))
    except Exception:
        # 簡單 fallback
        block_re = re.compile(
            r"(\d+)\s+([\d:,]+)\s+-->\s+([\d:,]+)\s+([\s\S]*?)(?=\n\n|\Z)",
            re.MULTILINE,
        )
        subs = []
        for idx, st, et, txt in block_re.findall(raw):
            subs.append(
                type(
                    "Subtitle",
                    (),
                    {
                        "index": int(idx),
                        "start": _safe_parse_time(st.strip()),
                        "end": _safe_parse_time(et.strip()),
                        "content": txt.strip(),
                    },
                )()
            )
        return subs


def compose_srt(subs: List):
    try:
        import srt

        return srt.compose(subs)
    except Exception:
        out = []
        for s in subs:
            out.append(str(s.index))
            out.append(f"{_fmt_time(s.start)} --> {_fmt_time(s.end)}")
            out.append(s.content)
            out.append("")  # blank line
        return "\n".join(out)


# ---------- 核心 ①：健壯的標點注入（支援全域對齊） ----------
def inject_punct_robust(subs: List, full_text: str):
    """使用 SequenceMatcher 進行全域對齊，自動處理前後多餘文字"""
    # 1. 去掉所有空白，只留下字和標點
    full = _strip_space(full_text)
    srt_plain = "".join(s.content for s in subs)  # 字幕串（純文字）
    punct_set = set(PUNCT)
    
    # 2. 全域對齊
    sm = difflib.SequenceMatcher(None, srt_plain, full, autojunk=False)
    blocks = sm.get_matching_blocks()  # (a_idx, b_idx, size)
    
    # 3. 為每條字幕找對應 slice，並插回標點
    b_cursor = 0
    sub_idx = 0
    
    for a, b, size in blocks:
        # 跳過不匹配的片段，直接處理匹配塊
        b_cursor = b
        
        # 對齊 len=size 的共同片段
        chars_processed = 0
        while chars_processed < size and sub_idx < len(subs):
            word = subs[sub_idx].content
            wlen = len(word)
            
            # 從 full[b_cursor:] 收集前置標點
            prefix = ""
            while b_cursor < len(full) and full[b_cursor] in punct_set:
                prefix += full[b_cursor]
                b_cursor += 1
            
            # 檢驗字幕文字是否匹配
            if b_cursor + wlen > len(full) or full[b_cursor:b_cursor+wlen] != word:
                # 對齊失敗，嘗試降級到滑動搜尋
                warnings.warn(f"SequenceMatcher 對齊失敗於字幕 {sub_idx+1}: '{word}'，嘗試滑動搜尋")
                return inject_punct_sliding(subs, full_text)
            
            b_cursor += wlen
            chars_processed += wlen
            
            # 收集後置標點
            postfix = ""
            while b_cursor < len(full) and full[b_cursor] in punct_set:
                postfix += full[b_cursor]
                b_cursor += 1
            
            subs[sub_idx].content = prefix + word + postfix
            sub_idx += 1
    
    # 4. 處理剩餘未對齊的字幕（保持原樣）
    if sub_idx < len(subs):
        warnings.warn(f"部分字幕未能對齊：從第 {sub_idx+1} 條開始")
    
    return subs


def inject_punct_sliding(subs: List, full_text: str):
    """滑動搜尋對齊策略（降級方案）"""
    full = _strip_space(full_text)
    punct_set = set(PUNCT)
    cursor = 0
    
    for i, s in enumerate(subs):
        word = s.content
        
        # 在接下來 500 字內搜尋
        search_end = min(len(full), cursor + 500)
        pos = full.find(word, cursor, search_end)
        
        if pos == -1:
            # 找不到，保持原樣並記錄警告
            warnings.warn(f"字幕 {i+1} 無法對齊: '{word}'")
            continue
        
        # 收集前置標點
        prefix = ""
        p = pos
        while p > cursor and full[p-1] in punct_set:
            p -= 1
            prefix = full[p] + prefix
        
        # 收集後置標點
        postfix = ""
        p = pos + len(word)
        while p < len(full) and full[p] in punct_set:
            postfix += full[p]
            p += 1
        
        s.content = prefix + word + postfix
        cursor = pos + len(word)
    
    return subs


def inject_punct(subs: List, full_text: str):
    """標點注入主函數，優先使用健壯對齊，失敗時降級"""
    try:
        return inject_punct_robust(subs, full_text)
    except Exception as e:
        warnings.warn(f"健壯對齊失敗: {e}，降級至滑動搜尋")
        return inject_punct_sliding(subs, full_text)


# ---------- 核心 ②：合併為句 ----------
def merge_to_sentence(subs: List):
    merged = []
    cur = subs[0]
    cur_len = len(_strip_space(cur.content))

    for nxt in subs[1:]:
        gap = _ms(nxt.start - cur.end)
        nxt_len = len(_strip_space(nxt.content))
        # 強制斷句：遇到。？！ 或不符規則
        force_break = any(ch in cur.content for ch in "。？！?！")
        can_merge = (
            (gap <= GAP_THRESHOLD_MS) and (cur_len + nxt_len <= MAX_CHARS) and not force_break
        )

        if can_merge:
            cur.content += nxt.content
            cur.end = nxt.end
            cur_len += nxt_len
        else:
            merged.append(cur)
            cur = nxt
            cur_len = nxt_len
    merged.append(cur)

    # 重新編號
    for i, s in enumerate(merged, 1):
        s.index = i
    return merged


# ---------- main ----------
def main(srt_path: str, txt_path: str):
    srt_file = Path(srt_path)
    txt_file = Path(txt_path)
    subs = parse_srt(srt_file)
    full_text = txt_file.read_text(encoding="utf-8", errors="ignore")
    
    # 記錄警告數量
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # ① 標點恢復（使用健壯對齊策略）
        subs_with_punct = inject_punct(subs, full_text)
        (srt_file.with_suffix(".punct.srt").write_text(compose_srt(subs_with_punct), encoding="utf-8"))

        # ② 句級合併
        sentence_subs = merge_to_sentence(subs_with_punct)
        out_path = srt_file.with_suffix(".sentence.srt")
        out_path.write_text(compose_srt(sentence_subs), encoding="utf-8")

        print(f"✅ 已輸出：\n  • {srt_file.with_suffix('.punct.srt').name}\n  • {out_path.name}")
        
        # 如果有警告，返回特殊退出碼
        if w:
            print(f"⚠️  處理過程中有 {len(w)} 個警告：", file=sys.stderr)
            for warning in w:
                print(f"  - {warning.message}", file=sys.stderr)
            return 100  # 部分對齊失敗但仍輸出
        
        return 0  # 完全成功


# ---------- CLI ----------
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python restore_srt.py raw.srt full.txt", file=sys.stderr)
        sys.exit(2)
    try:
        exit_code = main(sys.argv[1], sys.argv[2])
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ 失敗：{e}", file=sys.stderr)
        sys.exit(1)
