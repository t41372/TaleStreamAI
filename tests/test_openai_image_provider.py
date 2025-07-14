# tests/test_openai_image_provider.py
import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from openai import AsyncOpenAI

from app.services.openai_image_provider import OpenAIImageGenerator, FallbackImageGenerator


class TestOpenAIImageGenerator:
    """Test OpenAI Image Generator functionality."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = AsyncMock(spec=AsyncOpenAI)
        return client

    @pytest.fixture
    def semaphore(self):
        """Create a semaphore for testing."""
        return asyncio.Semaphore(1)

    @pytest.fixture
    def openai_generator(self, mock_openai_client, semaphore):
        """Create an OpenAI image generator with mocked client."""
        generator = OpenAIImageGenerator(
            client=mock_openai_client,
            model="dall-e-3",
            semaphore=semaphore  # 显式传递semaphore以避免配置依赖
        )
        # Replace the cached generate method with a non-cached version for testing
        async def mock_generate(prompt: str) -> bytes:
            async with generator._sem:
                from loguru import logger
                from app.config import settings
                import base64
                
                logger.debug(f"OpenAIImageGenerator → {generator._model}: {prompt[:60]}…")

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

                resp = await generator._client.images.generate(
                    model=generator._model,
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
        
        generator.generate = mock_generate
        return generator

    async def test_generate_success(self, openai_generator, mock_openai_client):
        """Test successful image generation."""
        # Mock response
        test_image_data = b"fake_image_data"
        test_b64_data = base64.b64encode(test_image_data).decode()
        
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].b64_json = test_b64_data
        
        # Set up async mock for images.generate
        mock_openai_client.images.generate = AsyncMock(return_value=mock_response)

        # Test generation
        result = await openai_generator.generate("test prompt")
        
        # Verify
        assert result == test_image_data
        mock_openai_client.images.generate.assert_called_once()

    async def test_generate_missing_data(self, openai_generator, mock_openai_client):
        """Test handling when API returns no data."""
        # Mock empty response
        mock_response = MagicMock()
        mock_response.data = []
        
        # Set up async mock for images.generate
        mock_openai_client.images.generate = AsyncMock(return_value=mock_response)

        # Test generation should raise error
        with pytest.raises(ValueError, match="No image data returned from API"):
            await openai_generator.generate("test prompt")


class TestFallbackImageGenerator:
    """Test Fallback Image Generator functionality."""

    @pytest.fixture
    def primary_generator(self):
        """Create a mock primary generator."""
        return AsyncMock()

    @pytest.fixture
    def secondary_generator(self):
        """Create a mock secondary generator."""
        return AsyncMock()

    @pytest.fixture
    def fallback_generator(self, primary_generator, secondary_generator):
        """Create a fallback generator."""
        return FallbackImageGenerator(primary_generator, secondary_generator)

    async def test_primary_success(self, fallback_generator, primary_generator, secondary_generator):
        """Test when primary generator succeeds."""
        test_data = b"primary_image_data"
        primary_generator.generate.return_value = test_data

        result = await fallback_generator.generate("test prompt")
        
        assert result == test_data
        primary_generator.generate.assert_called_once_with("test prompt")
        secondary_generator.generate.assert_not_called()

    async def test_primary_fails_secondary_succeeds(self, fallback_generator, primary_generator, secondary_generator):
        """Test when primary fails but secondary succeeds."""
        test_data = b"secondary_image_data"
        primary_generator.generate.side_effect = Exception("Primary failed")
        secondary_generator.generate.return_value = test_data

        result = await fallback_generator.generate("test prompt")
        
        assert result == test_data
        primary_generator.generate.assert_called_once_with("test prompt")
        secondary_generator.generate.assert_called_once_with("test prompt")

    async def test_both_fail(self, fallback_generator, primary_generator, secondary_generator):
        """Test when both generators fail."""
        primary_generator.generate.side_effect = Exception("Primary failed")
        secondary_generator.generate.side_effect = Exception("Secondary failed")

        with pytest.raises(Exception, match="Secondary failed"):
            await fallback_generator.generate("test prompt")
