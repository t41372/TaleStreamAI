# app/services/audio_provider.py
import edge_tts
from loguru import logger

from .base import AudioGenerator
from ..config import settings
from ..cache import cache


class EdgeTTSAudioGenerator(AudioGenerator):
    """使用 Microsoft Edge TTS 的音频生成器实现。"""

    @cache(settings.paths.cache_audio, "binary")
    async def generate(self, text: str, voice: str) -> bytes:
        try:
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as e:
            logger.error(f"Edge-TTS generation failed for text '{text[:30]}...': {e}")
            raise 