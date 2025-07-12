import asyncio
import json
import os
import re
from pathlib import Path

import edge_tts
import srt
from dotenv import load_dotenv
from tqdm import tqdm

from word_srt_to_sentence import group_word_by_word_srt

load_dotenv(override=True)

VOICE = os.getenv("EDGE_VOICE", "zh-CN-YunxiNeural")
CONCURRENCY = int(os.getenv("AUDIO_CONCURRENCY", "4"))


def _split_sentences(text: str) -> list[str]:
    pattern = r"[^。！？!?]+[。！？!?]?"
    return [m.group(0) for m in re.finditer(pattern, text) if m.group(0).strip()]


def _align_with_original(text: str, subs: list[srt.Subtitle]) -> list[srt.Subtitle]:
    parts = _split_sentences(text)
    if len(parts) == len(subs):
        for sub, part in zip(subs, parts):
            sub.content = part.strip()
    return subs


async def synthesize(text: str, audio_path: Path, srt_path: Path) -> None:
    communicate = edge_tts.Communicate(text, VOICE)
    submaker = edge_tts.SubMaker()
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audio_path, "wb") as audio_f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
    word_srt = submaker.generate_subs()
    grouped = group_word_by_word_srt(srt.parse(word_srt))
    grouped = _align_with_original(text, grouped)
    srt_path.write_text(srt.compose(grouped), encoding="utf-8")


async def _process_item(item: dict, book_id: str, chapter_name: str, sem: asyncio.Semaphore, pbar: tqdm) -> None:
    item_id = item["id"]
    text = item["text"]
    audio_file = Path(f"data/book/{book_id}/audio/{chapter_name}/{item_id}.mp3")
    srt_file = Path(f"data/book/{book_id}/srt/{chapter_name}/{item_id}.srt")
    if not audio_file.exists():
        async with sem:
            await synthesize(text, audio_file, srt_file)
    item["audio_path"] = str(audio_file)
    item["srt_path"] = str(srt_file)
    pbar.update(1)


async def create_book_audio(book_id: str) -> None:
    storyboard_dir = Path(f"data/book/{book_id}/storyboard")
    if not storyboard_dir.exists():
        print(f"小说信息不存在{storyboard_dir}")
        return
    chapter_files = sorted(storyboard_dir.glob("*.json"), key=lambda p: int(p.stem))
    total = 0
    for path in chapter_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        total += len(data)
    sem = asyncio.Semaphore(CONCURRENCY)
    with tqdm(total=total, desc="TTS", unit="clip") as pbar:
        for path in chapter_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks = [
                _process_item(item, book_id, path.stem, sem, pbar)
                for item in data
            ]
            await asyncio.gather(*tasks)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(create_book_audio("1043294775"))
