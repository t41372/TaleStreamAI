"""OpenAI Image API generator (async).

Uses the official `openai` Python SDK (already in deps) and supports       
automatic semaphore‑based concurrency + disk‑cache via the existing 
`cache` decorator.
"""

from __future__ import annotations

import asyncio
import base64

from loguru import logger
from openai import AsyncOpenAI

from .base import ImageGenerator
from ..config import settings
from ..cache import cache


class OpenAIImageGenerator(ImageGenerator):
    """Primary generator backed by OpenAI's images endpoint."""

    def __init__(self, client: AsyncOpenAI, model: str, semaphore: asyncio.Semaphore | None = None):
        self._client = client
        self._model = model
        # 如果没有提供semaphore，则使用OpenAI专用的并发设置创建一个
        if semaphore is None:
            from ..config import settings
            concurrent_limit = settings.openai_image_threads
            # 向后兼容：如果专用设置不存在，则使用通用设置
            if concurrent_limit == 3:  # 默认值，检查是否用户设置了IMAGE_THREADS
                concurrent_limit = settings.image_threads
            self._sem = asyncio.Semaphore(concurrent_limit)
            from loguru import logger
            logger.debug(f"OpenAIImageGenerator initialized with {concurrent_limit} concurrent threads")
        else:
            self._sem = semaphore

    @cache(settings.paths.cache_image, "binary")
    async def generate(self, prompt: str) -> bytes:  # noqa: D401 – concrete impl
        async with self._sem:
            logger.debug(f"OpenAIImageGenerator → {self._model}: {prompt[:60]}…")

            # Map size to valid OpenAI sizes
            size_mapping = {
                "1024x1024": "1024x1024",
                "1792x1024": "1792x1024", 
                "1024x1792": "1024x1792",
                "1536x1024": "1536x1024",
                "1024x1536": "1024x1536",
                "256x256": "256x256",
                "512x512": "512x512",
            }
            
            requested_size = f"{settings.image_width}x{settings.image_height}"
            valid_size = size_mapping.get(requested_size, "1024x1024")

            resp = await self._client.images.generate(
                model=self._model,
                prompt=prompt,
                n=1,
                size=valid_size,  # type: ignore
                response_format="b64_json",
            )

            try:
                if not resp.data or len(resp.data) == 0:
                    raise ValueError("No image data returned from API")
                b64_data = resp.data[0].b64_json
                if not b64_data:
                    raise ValueError("Image response missing `b64_json` field")
            except (IndexError, AttributeError):
                raise ValueError("Image response missing `b64_json` field")

            return base64.b64decode(b64_data)


class FallbackImageGenerator(ImageGenerator):
    """Wraps *two* generators → try primary, fallback to secondary on error."""

    def __init__(self, primary: ImageGenerator, secondary: ImageGenerator):
        self._primary = primary
        self._secondary = secondary

    async def generate(self, prompt: str) -> bytes:  # noqa: D401
        try:
            return await self._primary.generate(prompt)
        except Exception as e:  # pragma: no cover – runtime fallback
            from traceback import format_exception_only

            err = "".join(format_exception_only(type(e), e)).strip()
            logger.warning(f"Primary image gen failed → {err}. Falling back …")
            return await self._secondary.generate(prompt)
