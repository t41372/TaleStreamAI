"""
統一的大模型客戶端管理模塊
支持OpenAI兼容的API接口，包含异步并发支持
"""

import sys
import asyncio
import json
from typing import AsyncIterator, Any

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError, AsyncStream
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageParam

from .config import LLMConfig, settings
from .logger import log_error, log_info, log_debug
from .cache import llm_cache

class UnifiedLLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        self.semaphore = asyncio.Semaphore(settings.max_llm_threads)

    @llm_cache
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
        log_debug(f"Executing non-streamed chat completion for model {self.config.model}")
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
            log_debug(f"Semaphore acquired for {self.config.model}. Executing stream...")
            async for chunk in self._stream_implementation(messages, system):
                yield chunk

    async def _stream_implementation(
        self, messages: list[dict[str, Any]], system: str
    ) -> AsyncIterator[str]:
        """
        核心流式实现，包含详细日志和用户反馈。
        """
        log_debug(f"System prompt: {system}")
        
        # OpenAI的SDK类型检查很严格，这里进行转换
        final_messages: list[ChatCompletionMessageParam] = messages # type: ignore
        if system:
            final_messages.insert(0, {"role": "system", "content": system})

        stream: AsyncStream[ChatCompletionChunk] | None = None
        try:
            stream = await self.client.chat.completions.create(
                model=self.config.model,
                messages=final_messages,
                stream=True,
                temperature=0.5,
            )
            # 用户反馈开始
            sys.stdout.write(f"LLM ({self.config.model}): ")
            sys.stdout.flush()

            async for chunk in stream:
                # 检查是否有 'reasoning' (某些模型支持)
                if (
                    hasattr(chunk.choices[0].delta, "tool_calls") # Groq/OpenAI reasoning in tool_calls
                    and chunk.choices[0].delta.tool_calls
                ):
                    sys.stdout.write('.')
                    sys.stdout.flush()

                if content := chunk.choices[0].delta.content:
                    sys.stdout.write('*')
                    sys.stdout.flush()
                    yield content
            
            # 用户反馈结束
            sys.stdout.write("\n")
            sys.stdout.flush()

        except (APIConnectionError, RateLimitError, APIError) as e:
            log_error(f"LLM API Error for model {self.config.model}: {e}")
            # 在流中产生一个错误信息，让下游知道
            yield f"ERROR: LLM call failed. {e}"
        finally:
            if stream:
                await stream.close()
                log_debug("LLM Stream closed.")

# 全局客户端实例
storyboard_client = UnifiedLLMClient(settings.storyboard_llm)
prompt_client = UnifiedLLMClient(settings.prompt_llm)

async def test_llm_connections():
    log_info("Testing LLM connections...")
    test_messages = [{"role": "user", "content": "Hello!"}]
    
    log_info("Testing Storyboard Client...")
    storyboard_response = await storyboard_client.chat_completion(test_messages)
    if "ERROR" in storyboard_response:
        log_error("Storyboard client test FAILED.")
    else:
        log_info(f"Storyboard client test OK. Response: {storyboard_response[:50]}...")

    log_info("Testing Prompt Client...")
    prompt_response = await prompt_client.chat_completion(test_messages)
    if "ERROR" in prompt_response:
        log_error("Prompt client test FAILED.")
    else:
        log_info(f"Prompt client test OK. Response: {prompt_response[:50]}...")
