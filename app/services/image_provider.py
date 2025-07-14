# app/services/image_provider.py
import urllib.parse
import aiohttp
import asyncio
from loguru import logger

from .base import ImageGenerator
from ..config import settings
from ..cache import cache

# expose OpenAI classes when imported via this module
from .openai_image_provider import OpenAIImageGenerator, FallbackImageGenerator

# Export all classes for external use
__all__ = ["PollinationsImageGenerator", "OpenAIImageGenerator", "FallbackImageGenerator"]


class PollinationsImageGenerator(ImageGenerator):
    """使用 Pollinations.ai API 的图像生成器实现。"""

    def __init__(self, session: aiohttp.ClientSession, max_concurrent: int | None = None):
        # 使用专用的并发设置，如果没有提供则使用配置中的值
        concurrent_limit = max_concurrent or settings.pollinations_image_threads
        # 向后兼容：如果专用设置不存在，则使用通用设置
        if concurrent_limit == settings.pollinations_image_threads and concurrent_limit == 8:
            # 这意味着用户没有设置POLLINATIONS_IMAGE_THREADS，检查是否设置了IMAGE_THREADS
            concurrent_limit = settings.image_threads
        
        self.semaphore = asyncio.Semaphore(concurrent_limit)
        self._session = session
        logger.debug(f"PollinationsImageGenerator initialized with {concurrent_limit} concurrent threads")

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
                timeout = aiohttp.ClientTimeout(total=300)
                async with self._session.get(url, timeout=timeout) as response:
                    response.raise_for_status()
                    return await response.read()
            except aiohttp.ClientError as e:
                logger.error(
                    f"Image generation API request failed for prompt '{prompt[:30]}...': {e}"
                )
                raise 