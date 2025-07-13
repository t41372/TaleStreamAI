"""
Edge TTS implementation for TaleStreamAI.
Replaces CosyVoice with Microsoft Edge TTS for audio generation and subtitle creation.
"""

import asyncio
import os
import re
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import edge_tts
import srt
from tqdm import tqdm
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Chinese voices for edge-tts
DEFAULT_VOICE = "zh-CN-XiaoyiNeural"
FALLBACK_VOICES = [
    "zh-CN-YunjianNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-XiaohanNeural",
]


class EdgeTTSGenerator:
    """Edge TTS generator with subtitle support and punctuation restoration."""

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self.semaphore = asyncio.Semaphore(5)  # Limit concurrent requests

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def generate_audio_with_subtitles(
        self,
        text: str,
        audio_path: str,
        subtitle_path: Optional[str] = None,
        original_text: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Generate audio and subtitles using Edge TTS.

        Args:
            text: Text to convert to speech
            audio_path: Path to save audio file
            subtitle_path: Path to save subtitle file (optional)
            original_text: Original text with punctuation for restoration (optional)

        Returns:
            Tuple of (success, subtitle_path)
        """
        async with self.semaphore:
            try:
                # Create communication object
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    rate=self.rate,
                    volume=self.volume,
                    pitch=self.pitch,
                )

                # Ensure output directory exists
                os.makedirs(os.path.dirname(audio_path), exist_ok=True)

                # Generate metadata path for subtitles
                if subtitle_path is None:
                    subtitle_path = os.path.splitext(audio_path)[0] + ".srt"

                # Save audio and extract subtitles in one pass
                audio_data = bytearray()
                word_timings = []
                
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data.extend(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        # Extract word timing information
                        word_timings.append(
                            {
                                "word": chunk["text"],
                                "start": chunk["offset"] / 10_000_000,  # Convert to seconds
                                "duration": chunk["duration"] / 10_000_000,
                            }
                        )

                # Save audio data
                with open(audio_path, "wb") as f:
                    f.write(audio_data)

                # Generate subtitles from collected timings
                subtitle_content = self._generate_subtitles_from_timings(
                    word_timings, original_text
                )

                if subtitle_content and subtitle_path:
                    os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
                    with open(subtitle_path, "w", encoding="utf-8") as f:
                        f.write(subtitle_content)

                return True, subtitle_path

            except Exception as e:
                logger.error(f"Failed to generate audio with Edge TTS: {e}")
                return False, None

    def _generate_subtitles_from_timings(
        self, word_timings: List[Dict], original_text: Optional[str] = None
    ) -> str:
        """Generate subtitles from word timings and restore punctuation if possible."""
        if not word_timings:
            return ""

        # Group words into sentences and restore punctuation
        if original_text:
            subtitles = self._restore_punctuation_to_subtitles(
                word_timings, original_text
            )
        else:
            subtitles = self._group_words_into_subtitles(word_timings)

        # Convert to SRT format
        return self._format_as_srt(subtitles)

    def _restore_punctuation_to_subtitles(
        self, word_timings: List[Dict], original_text: str
    ) -> List[Dict]:
        """Restore punctuation by matching with original text."""
        # Split original text into sentences
        original_sentences = self._split_into_sentences(original_text)

        # Get words from timings
        tts_words = [timing["word"] for timing in word_timings]

        # Try to align words
        aligned_subtitles = []
        word_idx = 0

        for sentence in original_sentences:
            # Remove punctuation for word matching
            clean_sentence = re.sub(r"[^\w\s]", "", sentence)
            sentence_words = clean_sentence.split()

            if not sentence_words:
                continue

            sentence_start = None
            sentence_end = None
            words_matched = 0

            # Try to match words from the sentence with timing data
            while word_idx < len(word_timings) and words_matched < len(sentence_words):
                if sentence_start is None:
                    sentence_start = word_timings[word_idx]["start"]
                sentence_end = (
                    word_timings[word_idx]["start"] + word_timings[word_idx]["duration"]
                )
                word_idx += 1
                words_matched += 1

            if sentence_start is not None and sentence_end is not None:
                aligned_subtitles.append(
                    {
                        "start": sentence_start,
                        "end": sentence_end,
                        "text": sentence.strip(),
                    }
                )

        return aligned_subtitles

    def _group_words_into_subtitles(self, word_timings: List[Dict]) -> List[Dict]:
        """Group words into subtitle segments without punctuation restoration."""
        subtitles = []
        current_subtitle = {"words": [], "start": None, "end": None}
        words_per_subtitle = 10  # Adjust as needed

        for i, timing in enumerate(word_timings):
            if current_subtitle["start"] is None:
                current_subtitle["start"] = timing["start"]

            current_subtitle["words"].append(timing["word"])
            current_subtitle["end"] = timing["start"] + timing["duration"]

            # Create subtitle segment when we have enough words or reached end
            if (
                len(current_subtitle["words"]) >= words_per_subtitle
                or i == len(word_timings) - 1
            ):
                if current_subtitle["words"]:
                    subtitles.append(
                        {
                            "start": current_subtitle["start"],
                            "end": current_subtitle["end"],
                            "text": " ".join(current_subtitle["words"]),
                        }
                    )
                current_subtitle = {"words": [], "start": None, "end": None}

        return subtitles

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences using Chinese punctuation."""
        # Split on Chinese sentence endings, but preserve the punctuation
        sentences = re.split(r"([。！？!?.;；])", text)

        # Recombine sentences with their punctuation
        result = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i].strip()
            if i + 1 < len(sentences):
                punctuation = sentences[i + 1]
                sentence += punctuation
            if sentence:
                result.append(sentence)

        # Handle case where text doesn't end with punctuation
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            result.append(sentences[-1].strip())

        return result

    def _format_as_srt(self, subtitles: List[Dict]) -> str:
        """Format subtitles as SRT."""
        srt_subtitles = []

        for i, subtitle in enumerate(subtitles):
            start_time = self._seconds_to_srt_time(subtitle["start"])
            end_time = self._seconds_to_srt_time(subtitle["end"])

            srt_subtitles.append(
                srt.Subtitle(
                    index=i + 1,
                    start=start_time,
                    end=end_time,
                    content=subtitle["text"],
                )
            )

        return srt.compose(srt_subtitles)

    def _seconds_to_srt_time(self, seconds: float):
        """Convert seconds to SRT timedelta format."""
        import datetime

        return datetime.timedelta(seconds=seconds)


async def generate_audio_with_edge_tts(
    text: str,
    audio_path: str,
    voice: str = DEFAULT_VOICE,
    subtitle_path: Optional[str] = None,
    original_text: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to generate audio with Edge TTS.

    Args:
        text: Text to convert to speech
        audio_path: Path to save audio file
        voice: Voice to use for TTS
        subtitle_path: Path to save subtitle file (optional)
        original_text: Original text with punctuation for restoration (optional)

    Returns:
        Tuple of (success, subtitle_path)
    """
    generator = EdgeTTSGenerator(voice=voice)
    return await generator.generate_audio_with_subtitles(
        text, audio_path, subtitle_path, original_text
    )


def sync_generate_audio_with_edge_tts(
    text: str,
    audio_path: str,
    voice: str = DEFAULT_VOICE,
    subtitle_path: Optional[str] = None,
    original_text: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Synchronous wrapper for async Edge TTS generation.
    """
    return asyncio.run(
        generate_audio_with_edge_tts(
            text, audio_path, voice, subtitle_path, original_text
        )
    )


if __name__ == "__main__":
    # Test the implementation
    test_text = "这是一个测试文本。我们要生成音频和字幕。"
    test_audio = "/tmp/test_edge_tts.mp3"
    test_subtitle = "/tmp/test_edge_tts.srt"

    print("Testing Edge TTS implementation...")
    success, subtitle_path = sync_generate_audio_with_edge_tts(
        test_text, test_audio, subtitle_path=test_subtitle, original_text=test_text
    )

    if success:
        print(f"✓ Audio generated: {test_audio}")
        print(f"✓ Subtitles generated: {subtitle_path}")
    else:
        print("✗ Failed to generate audio/subtitles")
