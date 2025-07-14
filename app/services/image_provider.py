# app/services/image_provider.py
import urllib.parse
import aiohttp
import asyncio
from loguru import logger

from .base import ImageGenerator
from ..config import settings
from ..cache import cache


class PollinationsImageGenerator(ImageGenerator):
    """使用 Pollinations.ai API 的图像生成器实现。"""

    def __init__(self, session: aiohttp.ClientSession):
        self.semaphore = asyncio.Semaphore(settings.image_threads)
        self._session = session

    @cache(settings.paths.cache_image, "binary")
    async def generate(self, prompt: str) -> bytes:
        async with self.semaphore:
            encoded_prompt = urllib.parse.quote(prompt)
            url = (
                f"https://image.pollinations.ai/prompt/{encoded_prompt}"
                f"?width={settings.image_width}&height={settings.image_height}&nologo=true&model=flux"
            )

            try:
                logger.debug(f"Requesting image from URL: {url.split('?')[0]}...")
                async with self._session.get(url, timeout=300) as response:
                    response.raise_for_status()
                    return await response.read()
            except aiohttp.ClientError as e:
                logger.error(
                    f"Image generation API request failed for prompt '{prompt[:30]}...': {e}"
                )
                raise 