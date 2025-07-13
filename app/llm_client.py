"""
統一的大模型客戶端管理模塊
支持OpenAI兼容的API接口，包含异步并发支持
"""

import sys
import asyncio
import json
import random
from typing import AsyncIterator, Any

import tiktoken
from httpx import RemoteProtocolError
from openai import (
    AsyncOpenAI,
    APIError,
    APIConnectionError,
    RateLimitError,
    AsyncStream,
)
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageParam

from .config import LLMConfig, settings
from loguru import logger
from .cache import cache


EMOJI_LIST = ["🚀", "💡", "✨", "🤖", "🧠", "✍️", "🎨", "🎬", "🎶", "💬"]


class UnifiedLLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        self.semaphore = asyncio.Semaphore(settings.max_llm_threads)

    @cache(settings.paths.cache_llm, "text")
    async def _cached_chat_completion(self, messages_json: str, system: str) -> str:
        """内部缓存方法，只用于非流式调用"""
        full_response = ""
        # The messages are passed as a JSON string to be hashable by the cache decorator.
        # We need to load them back into a list of dictionaries here.
        messages = json.loads(messages_json)
        async for chunk in self._stream_implementation(messages, system):
            full_response += chunk
        return full_response

    async def chat_completion(self, messages: list[dict[str, Any]], system: str = "") -> str:
        """
        执行非流式聊天补全，利用缓存。
        """
        logger.debug(f"Executing non-streamed chat completion for model {self.config.model}")
        # We dump the messages to a JSON string because a list of dicts is not hashable,
        # which is required by our caching decorator.
        messages_json = json.dumps(messages)
        return await self._cached_chat_completion(messages_json, system=system)

    async def chat_completion_stream(
        self, messages: list[dict[str, Any]], system: str = ""
    ) -> AsyncIterator[str]:
        """
        执行异步流式聊天补全，带信号量控制。
        """
        async with self.semaphore:
            logger.debug(f"Semaphore acquired for {self.config.model}. Executing stream...")
            async for chunk in self._stream_implementation(messages, system):
                yield chunk

    async def _stream_implementation(
        self, messages: list[dict[str, Any]], system: str
    ) -> AsyncIterator[str]:
        """
        核心流式实现，包含详细日志和用户反馈。
        """
        logger.debug(f"System prompt: {system}")

        # 为每个 LLM 调用创建一个独特的 emoji 和随机数
        random_emoji = random.choice(EMOJI_LIST)
        random_number = str(random.randint(0, 9))
        call_id = f"{random_emoji}{random_number}"

        # OpenAI的SDK类型检查很严格，这里进行转换
        final_messages: list[ChatCompletionMessageParam] = messages  # type: ignore
        if system:
            final_messages.insert(0, {"role": "system", "content": system})

        stream: AsyncStream[ChatCompletionChunk] | None = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                stream = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=final_messages,
                    stream=True,
                    temperature=0.5,
                )

                # 在输出前，打印最后一个 message 的前 100 个字符 到 dev null
                print(f"LLM ({self.config.model}) 开始输出 [{call_id}]:")
                print(f"\"\"\"{final_messages[-1]['content'][:50]}...\"\"\"")
                # 输出 message 的总 token 数 (用 tiktoken 计算)

                encoding = tiktoken.encoding_for_model("gpt-4o")
                total_tokens = sum(
                    len(encoding.encode(m["content"])) for m in final_messages if m.get("content")
                )
                print(f"⭐️ 总 token 数: {total_tokens}\n")

                sys.stdout.flush()

                # 每 4 个推理 chunk 打印一个点，每 4 个内容 chunk 打印一个星号
                reasoning_counter = 0
                content_counter = 0
                async for chunk in stream:
                    if not chunk or not chunk.choices:
                        print("~", end="", flush=True)
                        continue
                    # 检查是否有 'reasoning' (某些模型支持)
                    if (
                        hasattr(chunk.choices[0].delta, "reasoning_content")
                        and chunk.choices[0].delta.reasoning_content
                    ):
                        reasoning_counter += 1
                        if reasoning_counter % 4 == 0:
                            sys.stdout.write(random_number)
                            sys.stdout.flush()

                    if content := chunk.choices[0].delta.content:
                        content_counter += 1
                        if content_counter % 4 == 0:
                            sys.stdout.write(random_emoji)
                            sys.stdout.flush()
                        yield content

                # 用户反馈结束
                sys.stdout.write(f"\nLLM Call: {call_id} 运行完成\n")
                sys.stdout.flush()
                return  # 成功完成，退出重试循环

            except (APIConnectionError, RateLimitError, APIError, RemoteProtocolError) as e:
                logger.info(
                    f"LLM API Error on attempt {attempt + 1}/{max_retries} for model {self.config.model}: {e}"
                )
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"LLM call failed after {max_retries} attempts for model {self.config.model}."
                    )
                    yield f"ERROR: LLM call failed. {e}"
            finally:
                if stream:
                    await stream.close()
                    logger.debug(f"LLM Stream closed for call {call_id}.")

        # 如果所有重试都失败了，确保有一个最终的错误信息
        logger.error(f"LLM call {call_id} failed completely after all retries.")


# 全局客户端实例
storyboard_client = UnifiedLLMClient(settings.storyboard_llm)
prompt_client = UnifiedLLMClient(settings.prompt_llm)


async def test_llm_connections():
    logger.info("Testing LLM connections...")
    test_messages = [{"role": "user", "content": "Hello!"}]

    logger.info("Testing Storyboard Client...")
    storyboard_response = await storyboard_client.chat_completion(test_messages)
    if "ERROR" in storyboard_response:
        logger.error("Storyboard client test FAILED.")
    else:
        logger.info(f"Storyboard client test OK. Response: {storyboard_response[:50]}...")

    logger.info("Testing Prompt Client...")
    prompt_response = await prompt_client.chat_completion(test_messages)
    if "ERROR" in prompt_response:
        logger.error("Prompt client test FAILED.")
    else:
        logger.info(f"Prompt client test OK. Response: {prompt_response[:50]}...")
