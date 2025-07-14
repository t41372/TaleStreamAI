"""
統一的大模型客戶端管理模塊
支持OpenAI兼容的API接口，包含异步并发、自动重试和JSON修复机制
"""

import sys
import asyncio
import json
import random
import re
from typing import AsyncIterator, Any, Optional, Union
from pathlib import Path

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
from json_repair import repair_json

from .config import LLMConfig, settings
from loguru import logger

EMOJI_LIST = ["🚀", "💡", "✨", "🤖", "🧠", "✍️", "🎨", "🎬", "🎶", "💬"]

# +++ 新增 JSON 修复器 Prompt +++
JSON_REPAIR_SYSTEM_PROMPT = """
你是一个专家级的 JSON 语法检查和自动修复工具。你的唯一功能是接收一段意图成为 JSON 对象的文本，识别并纠正其中所有的语法错误，然后输出一个格式完美的、可被程序直接解析的、有效的 JSON 对象。

在处理实际输入之前，请先学习以下几个范例，理解你的工作模式：

--- 范例 1 ---
输入:
{ 'name': 'John Doe', 'age': 30, }

输出:
{"name": "John Doe", "age": 30}
--- 范例 2 ---
输入:
{
// 用户信息
"username": "testuser"
"is_active": true
}

输出:
{"username": "testuser", "is_active": true}
--- 范例 3 ---
输入:
[
{
    "item": "Book",
    'price': 19.99
},
{
    "item": "Pen",
    "price": 1.50
}

输出:
[{"item": "Book", "price": 19.99}, {"item": "Pen", "price": 1.50}]
--- 范例结束 ---

现在，请严格遵守以下输出规则来处理真实的输入：
1.  分析输入内容，查找所有常见的 JSON 错误，包括但不限于：缺失或多余的逗号、不正确的引号（例如单引号应替换为双引号）、未闭合的括号或花括号、非法的注释等。
2.  纠正所有识别出的错误。
3.  你最终的输出【必须】是且【仅是】修正后、有效的 JSON 对象的原始文本。
4.  【绝对不要】在你的回复中包含任何解释、注释、道歉或任何介绍性文字。
5.  【绝对不要】将你的输出用 Markdown 代码块（```json ... ``` 或 ``` ... ```）包裹起来。
6.  输出的 JSON 对象前后不能有任何空格、换行符或其他任何字符。
"""

class UnifiedLLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )
        # 信号量现在从独立的LLM配置中获取，而不是全局settings
        self.semaphore = asyncio.Semaphore(settings.max_llm_threads)

    async def _repair_json(self, corrupt_json_str: str, original_asset_path: Optional[Path] = None) -> str:
        """使用专用的LLM尝试修复损坏的JSON字符串，并缓存修复结果"""
        logger.warning("JSON parsing failed. Attempting to repair with an LLM...")
        repair_messages = [{"role": "user", "content": corrupt_json_str}]
        
        # 基于原始路径派生一个修复缓存路径
        repair_asset_path = None
        if original_asset_path:
            repair_asset_path = original_asset_path.with_name(f"_repaired_{original_asset_path.name}")
        
        # 使用全局的 json_repair_client 实例，并传递缓存路径
        repaired_str = await json_repair_client.chat_completion(
            repair_messages, system=JSON_REPAIR_SYSTEM_PROMPT, output_path=repair_asset_path
        )
        
        # chat_completion现在也返回错误字符串，所以我们可以直接检查
        if "ERROR" in repaired_str:
             logger.error(f"JSON repair failed: {repaired_str}")
             return f"ERROR: JSON repair also failed. Original error: {corrupt_json_str}"

        logger.info("✅ JSON successfully repaired!")
        return repaired_str

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        output_path: Optional[Path] = None,
        expect_json: bool = False
    ) -> str:
        """
        执行非流式聊天补全，内置缓存和重试逻辑。
        通过 `expect_json` 参数控制是否执行JSON解析和修复。
        如果提供了 output_path，它将作为项目资产进行缓存/读取。
        """
        if output_path and output_path.exists():
            logger.debug(f"✅ LLM 资产命中: 从 {output_path} 读取")
            return output_path.read_text("utf-8")
        
        # 检查是否有损坏的旧文件（仅在期望JSON时）
        corrupt_path = output_path.with_name(f"_corrupt_{output_path.name}") if output_path and expect_json else None
        if corrupt_path and corrupt_path.exists():
             logger.warning(f"发现之前损坏的资产文件: {corrupt_path}. 将直接尝试修复它。")
             full_response = await self._repair_json(corrupt_path.read_text("utf-8"), output_path)
             if "ERROR" in full_response:
                 return full_response # 修复失败，直接返回错误
             # 修复成功，继续下面的保存逻辑
        else:
            logger.debug(f"❌ LLM 资产未命中: 为 {output_path or 'ad-hoc call'} 执行API调用")
            full_response = ""
            async with self.semaphore:
                # 将重试逻辑移至此处
                for attempt in range(self.config.retry_attempts):
                    try:
                        stream_content = self._stream_implementation(messages, system)
                        response_chunks = [chunk async for chunk in stream_content]
                        
                        # 检查流实现是否返回了错误
                        if response_chunks and "ERROR" in response_chunks[0]:
                            full_response = "".join(response_chunks)
                            raise APIError(message=full_response, request=None, body=None)

                        full_response = "".join(response_chunks)
                        
                        if expect_json:
                            # --- 这是 JSON 处理路径 ---
                            # 清理LLM可能添加的Markdown代码块
                            full_response = re.sub(r"```json\s*|\s*```", "", full_response).strip()
                            
                            # 尝试解析JSON以验证其完整性
                            json.loads(full_response)
                            
                            logger.debug(f"API调用成功并在第 {attempt + 1} 次尝试时获得有效JSON。")
                            break # 成功，跳出重试循环
                        else:
                            # --- 这是纯文本处理路径 ---
                            logger.debug(f"API调用成功并在第 {attempt + 1} 次尝试时获得纯文本。")
                            break # 成功，跳出重试循环

                    except (APIError, APIConnectionError, RateLimitError, RemoteProtocolError) as e:
                        logger.warning(f"API Error on attempt {attempt + 1}/{self.config.retry_attempts}: {e}")
                        if attempt < self.config.retry_attempts - 1:
                            wait_time = 2 ** attempt
                            logger.info(f"Retrying in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            full_response = f"ERROR: API call failed after {self.config.retry_attempts} attempts. Last error: {e}"
                    
                    except json.JSONDecodeError as e:
                        # 这个异常只会在 expect_json=True 时被触发
                        logger.warning(f"JSON解析失败 on attempt {attempt + 1}. Error: {e}. 内容: {full_response[:200]}...")
                        original_corrupt_response = full_response

                        # 阶段1: 尝试使用轻量级本地库修复
                        try:
                            logger.info("尝试使用 json-repair 本地库修复...")
                            repaired_str = repair_json(original_corrupt_response)
                            
                            # 检查修复是否成功：repair_json 失败时返回空字符串或原始字符串
                            if repaired_str and repaired_str != original_corrupt_response:
                                json.loads(repaired_str)  # 再次验证
                                logger.info("✅ 本地库 json-repair 修复成功！")
                                full_response = repaired_str
                                break  # 修复成功，跳出重试循环
                            else:
                                raise json.JSONDecodeError("repair_json returned empty or unchanged string", repaired_str, 0)
                                
                        except json.JSONDecodeError as repair_err:
                            logger.warning(f"本地库 json-repair 修复失败: {repair_err}")
                            # 本地库修复失败，进入下一阶段
                            if attempt < self.config.retry_attempts - 1:
                                logger.warning("将重试API调用以获取有效的JSON...")
                                await asyncio.sleep(2)
                                # continue at the end of the block
                            else:
                                # 阶段2: 回退到LLM修复
                                logger.error("所有API重试均失败，回退到LLM进行修复。")
                                repaired_response = await self._repair_json(original_corrupt_response, output_path)
                                full_response = repaired_response  # 无论修复成功与否，都用修复结果覆盖

                # for loop结束后，检查最终结果
                # 只有在期望JSON且最终失败时，才写入_corrupt_文件
                if expect_json and "ERROR" in full_response and output_path:
                    corrupt_path = output_path.with_name(f"_corrupt_{output_path.name}")
                    logger.error(f"所有尝试和修复均失败。将原始错误响应保存到 {corrupt_path}")
                    
                    # 如果我们有原始的损坏响应，就保存它；否则保存最终的错误信息
                    content_to_save = original_corrupt_response if 'original_corrupt_response' in locals() else full_response
                    corrupt_path.write_text(content_to_save, "utf-8")
                    return full_response # 返回最终的错误信息

        # 保存成功的结果
        if output_path and "ERROR" not in full_response:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(full_response, "utf-8")
            
            if expect_json:
                logger.debug(f"📝 LLM JSON资产已保存至: {output_path}")
                # 如果存在，删除旧的损坏文件
                corrupt_path = output_path.with_name(f"_corrupt_{output_path.name}")
                if corrupt_path.exists():
                    corrupt_path.unlink()
                    logger.info(f"已删除旧的损坏文件: {corrupt_path}")
            else:
                logger.debug(f"📝 LLM 纯文本资产已保存至: {output_path}")

        return full_response

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
        """核心流式实现，现仅关注API调用和流处理。错误将在上层处理。"""
        logger.debug(f"System prompt: {system}")
        random_emoji = random.choice(EMOJI_LIST)
        random_number = str(random.randint(0, 9))
        call_id = f"{random_emoji}{random_number}"

        # 创建一个新的列表，而不是修改原始列表，以避免副作用
        final_messages: list[ChatCompletionMessageParam] = []
        if system:
            # 类型转换在这里是明确的
            final_messages.append({"role": "system", "content": system})
        
        # 将原始消息追加进去，确保类型兼容
        final_messages.extend(messages) # type: ignore
        # 我们使用 type: ignore 是因为我们知道 messages 的结构兼容，
        # 但这比直接赋值更明确地告诉类型检查器我们的意图。

        try:
            stream = await self.client.chat.completions.create(
                model=self.config.model,
                messages=final_messages,
                stream=True,
                temperature=0.5,
            )
            
            # 在输出前，打印最后一个 message 的前 50 个字符
            last_message_content = final_messages[-1].get('content', '')
            print(f"LLM ({self.config.model}) 开始输出 [{call_id}]:")
            print(f"\"\"\"{last_message_content[:50]}...\"\"\"")
            
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
            
            sys.stdout.write(f"\nLLM Call: {call_id} 运行完成\n")
            sys.stdout.flush()

        except (APIError, APIConnectionError, RateLimitError, RemoteProtocolError) as e:
            logger.error(f"Stream implementation caught an exception: {e}")
            yield f"ERROR: {e}"


# 全局客户端实例
storyboard_client = UnifiedLLMClient(settings.storyboard_llm)
prompt_client = UnifiedLLMClient(settings.prompt_llm)
# +++ 新增 JSON 修复器客户端实例 +++
json_repair_client = UnifiedLLMClient(settings.json_repair_llm)


async def test_llm_connections():
    """测试所有LLM客户端连接"""
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

    logger.info("Testing JSON Repair Client...")
    json_repair_response = await json_repair_client.chat_completion(test_messages)
    if "ERROR" in json_repair_response:
        logger.error("JSON Repair client test FAILED.")
    else:
        logger.info(f"JSON Repair client test OK. Response: {json_repair_response[:50]}...")
