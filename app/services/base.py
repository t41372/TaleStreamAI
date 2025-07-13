# app/services/base.py
from abc import ABC, abstractmethod
from pathlib import Path


class ImageGenerator(ABC):
    """图像生成器的抽象基类接口。"""

    @abstractmethod
    async def generate(self, prompt: str) -> bytes:
        """
        根据给定的提示词生成图像数据。

        :param prompt: 图像生成的提示词。
        :return: 图像的二进制数据 (e.g., JPEG, PNG)。
        :raises Exception: 如果生成失败。
        """
        pass


class AudioGenerator(ABC):
    """音频生成器的抽象基类接口。"""

    @abstractmethod
    async def generate(self, text: str, voice: str) -> bytes:
        """
        根据给定的文本和语音生成音频数据。

        :param text: 要转换为语音的文本。
        :param voice: 使用的语音名称。
        :return: 音频的二进制数据 (e.g., MP3)。
        :raises Exception: 如果生成失败。
        """
        pass 