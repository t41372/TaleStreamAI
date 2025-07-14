# app/services/audio_provider.py
import edge_tts
from loguru import logger
from edge_tts import SubMaker

from .base import AudioGenerator
from ..config import settings
from ..cache import cache


class EdgeTTSAudioGenerator(AudioGenerator):
    """使用 Microsoft Edge TTS 的音频生成器实现。"""

    @cache(settings.paths.cache_audio, "pickle")
    async def generate(self, text: str, voice: str) -> tuple[bytes, str]:
        """
        生成音频数据和SRT格式的字幕字符串。
        :return: (音频二进制数据, SRT字幕字符串)
        """
        try:
            communicate = edge_tts.Communicate(text, voice)
            sub_maker = SubMaker()
            audio_data = b""
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
                elif chunk["type"] == "WordBoundary":
                    sub_maker.feed(chunk)

            srt_content = sub_maker.get_srt()
            return audio_data, srt_content
        except Exception as e:
            logger.error(f"Edge-TTS generation failed for text '{text[:30]}...': {e}")
            raise 