"""
統一的大模型客戶端管理模塊
支持OpenAI兼容的API接口，包含异步并发支持
"""

import os
import time
import asyncio
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from .logger import log_api_start, log_api_success, log_api_error, log_debug, log_info

load_dotenv(override=True)


class LLMClient:
    """統一的大模型客戶端類，支持同步和異步調用"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client_type: str = "default",
        timeout: Optional[float] = None,
    ):
        """
        初始化LLM客戶端

        Args:
            api_key: API密鑰
            base_url: API基礎URL
            model: 模型名稱
            client_type: 客戶端類型，用於從環境變量獲取配置
            timeout: 請求超時時間
        """
        self.client_type = client_type
        self.api_key = api_key or self._get_env_key()
        self.base_url = base_url or self._get_env_url()
        self.model = model or self._get_env_model()
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT", "120"))
        self.retry_attempts = int(os.getenv("LLM_RETRY_ATTEMPTS", "3"))

        if not self.api_key:
            raise ValueError(f"API Key not found for client type: {client_type}")

        log_debug(
            f"初始化 {client_type} 客戶端",
            extra={"model": self.model, "base_url": self.base_url},
        )

        # 同步客戶端
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

        # 異步客戶端
        self.async_client = AsyncOpenAI(
            api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
        )

    def _get_env_key(self) -> Optional[str]:
        """從環境變量獲取API密鑰"""
        if self.client_type == "storyboard":
            return (
                os.getenv("STORYBOARD_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("AL_API_KEY")
            )
        elif self.client_type == "prompt":
            return (
                os.getenv("PROMPT_API_KEY")
                or os.getenv("AL_API_KEY")
                or os.getenv("GEMINI_API_KEY")
            )
        else:
            return (
                os.getenv("AL_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("STORYBOARD_API_KEY")
            )

    def _get_env_url(self) -> Optional[str]:
        """從環境變量獲取API URL"""
        if self.client_type == "storyboard":
            return (
                os.getenv("STORYBOARD_API_URL")
                or os.getenv("GEMINI_API_URL")
                or os.getenv("AL_API_URL")
            )
        elif self.client_type == "prompt":
            return (
                os.getenv("PROMPT_API_URL")
                or os.getenv("AL_API_URL")
                or os.getenv("GEMINI_API_URL")
            )
        else:
            return (
                os.getenv("AL_API_URL")
                or os.getenv("GEMINI_API_URL")
                or os.getenv("STORYBOARD_API_URL")
            )

    def _get_env_model(self) -> str:
        """從環境變量獲取模型名稱"""
        if self.client_type == "storyboard":
            return os.getenv("STORYBOARD_MODEL", "gemini-2.0-flash")
        elif self.client_type == "prompt":
            # 根據API URL自動選擇合適的模型
            url = self._get_env_url()
            if url and "dashscope.aliyuncs.com" in url:
                return os.getenv("PROMPT_MODEL", "deepseek-v3")
            elif url and "generativelanguage.googleapis.com" in url:
                return os.getenv("PROMPT_MODEL", "gemini-2.0-flash")
            else:
                return os.getenv("PROMPT_MODEL", "gemini-2.0-flash")
        else:
            return os.getenv("STORYBOARD_MODEL", "gemini-2.0-flash")

    def chat_completion(
        self,
        messages: list,
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        """
        執行聊天完成請求

        Args:
            messages: 消息列表
            model: 模型名稱，如果不提供則使用默認模型
            stream: 是否使用流式響應
            **kwargs: 其他參數

        Returns:
            API響應或流式響應生成器
        """
        model = model or self.model

        log_api_start(f"{self.client_type.upper()}_LLM", endpoint=self.base_url, model=model)

        start_time = time.time()

        for attempt in range(self.retry_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=model, messages=messages, stream=stream, **kwargs
                )

                duration = time.time() - start_time
                log_api_success(
                    f"{self.client_type.upper()}_LLM",
                    duration=duration,
                    details=f"嘗試次數: {attempt + 1}",
                )

                return response

            except Exception as e:
                log_api_error(f"{self.client_type.upper()}_LLM", str(e), retry_count=attempt + 1)

                if attempt == self.retry_attempts - 1:
                    raise

                # 指數退避重試
                wait_time = 2**attempt
                log_debug(f"等待 {wait_time}s 後重試...")
                time.sleep(wait_time)

        raise Exception(f"LLM API調用失敗，已重試 {self.retry_attempts} 次")

    async def async_chat_completion(
        self,
        messages: list,
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> Any:
        """
        異步執行聊天完成請求

        Args:
            messages: 消息列表
            model: 模型名稱，如果不提供則使用默認模型
            stream: 是否使用流式響應
            **kwargs: 其他參數

        Returns:
            API響應或流式響應生成器
        """
        model = model or self.model

        log_api_start(f"ASYNC_{self.client_type.upper()}_LLM", endpoint=self.base_url, model=model)

        start_time = time.time()

        for attempt in range(self.retry_attempts):
            try:
                response = await self.async_client.chat.completions.create(
                    model=model, messages=messages, stream=stream, **kwargs
                )

                duration = time.time() - start_time
                log_api_success(
                    f"ASYNC_{self.client_type.upper()}_LLM",
                    duration=duration,
                    details=f"嘗試次數: {attempt + 1}",
                )

                return response

            except Exception as e:
                log_api_error(
                    f"ASYNC_{self.client_type.upper()}_LLM",
                    str(e),
                    retry_count=attempt + 1,
                )

                if attempt == self.retry_attempts - 1:
                    raise

                # 異步指數退避重試
                wait_time = 2**attempt
                log_debug(f"異步等待 {wait_time}s 後重試...")
                await asyncio.sleep(wait_time)

        raise Exception(f"異步LLM API調用失敗，已重試 {self.retry_attempts} 次")

    def chat_completion_stream(self, messages: list, model: Optional[str] = None, **kwargs) -> Any:
        """
        執行流式聊天完成請求

        Args:
            messages: 消息列表
            model: 模型名稱，如果不提供則使用默認模型
            **kwargs: 其他參數

        Returns:
            流式響應生成器
        """
        model = model or self.model
        return self.client.chat.completions.create(
            model=model, messages=messages, stream=True, **kwargs
        )

    def test_connection(self) -> bool:
        """測試API連接"""
        try:
            log_api_start(f"{self.client_type.upper()}_CONNECTION_TEST")
            start_time = time.time()

            response = self.chat_completion(
                messages=[{"role": "user", "content": '測試連接，請回復：{"test": "success"}'}]
            )
            content = response.choices[0].message.content

            duration = time.time() - start_time
            success = "test" in content.lower() and "success" in content.lower()

            if success:
                log_api_success(f"{self.client_type.upper()}_CONNECTION_TEST", duration)
            else:
                log_api_error(
                    f"{self.client_type.upper()}_CONNECTION_TEST",
                    f"響應內容不符合預期: {content}",
                )

            return success

        except Exception as e:
            log_api_error(f"{self.client_type.upper()}_CONNECTION_TEST", str(e))
            return False

    async def async_test_connection(self) -> bool:
        """異步測試API連接"""
        try:
            log_api_start(f"ASYNC_{self.client_type.upper()}_CONNECTION_TEST")
            start_time = time.time()

            response = await self.async_chat_completion(
                messages=[{"role": "user", "content": '測試連接，請回復：{"test": "success"}'}]
            )
            content = response.choices[0].message.content

            duration = time.time() - start_time
            success = "test" in content.lower() and "success" in content.lower()

            if success:
                log_api_success(f"ASYNC_{self.client_type.upper()}_CONNECTION_TEST", duration)
            else:
                log_api_error(
                    f"ASYNC_{self.client_type.upper()}_CONNECTION_TEST",
                    f"響應內容不符合預期: {content}",
                )

            return success

        except Exception as e:
            log_api_error(f"ASYNC_{self.client_type.upper()}_CONNECTION_TEST", str(e))
            return False


# 並發信號量控制
_llm_semaphore = None


def get_llm_semaphore():
    """獲取LLM並發控制信號量"""
    global _llm_semaphore
    if _llm_semaphore is None:
        max_concurrent = int(os.getenv("LLM_THREADS", "3"))
        _llm_semaphore = asyncio.Semaphore(max_concurrent)
        log_info(f"初始化LLM並發控制，最大並發數: {max_concurrent}")
    return _llm_semaphore


async def async_chat_with_semaphore(
    client: LLMClient, messages: list, worker_id: Optional[str] = None, **kwargs
) -> Any:
    """
    使用信號量控制的異步聊天完成請求

    Args:
        client: LLM客戶端
        messages: 消息列表
        worker_id: 工作者ID（用於日誌追蹤）
        **kwargs: 其他參數

    Returns:
        API響應
    """
    semaphore = get_llm_semaphore()

    log_debug(f"等待 LLM 並發許可 | 工作者: {worker_id or 'unknown'}")

    async with semaphore:
        log_debug(f"獲得 LLM 並發許可 | 工作者: {worker_id or 'unknown'}")

        try:
            response = await client.async_chat_completion(messages=messages, **kwargs)

            log_debug(f"釋放 LLM 並發許可 | 工作者: {worker_id or 'unknown'}")
            return response

        except Exception as e:
            log_debug(f"LLM 調用失敗，釋放並發許可 | 工作者: {worker_id or 'unknown'}")
            raise


async def batch_async_chat_completion(
    client: LLMClient,
    messages_list: List[list],
    worker_prefix: str = "worker",
    **kwargs,
) -> List[Any]:
    """
    批量異步執行聊天完成請求

    Args:
        client: LLM客戶端
        messages_list: 消息列表的列表
        worker_prefix: 工作者ID前綴
        **kwargs: 其他參數

    Returns:
        API響應列表
    """
    log_info(f"開始批量異步LLM調用，任務數量: {len(messages_list)}")

    tasks = []
    for i, messages in enumerate(messages_list):
        worker_id = f"{worker_prefix}_{i + 1}"
        task = async_chat_with_semaphore(
            client=client, messages=messages, worker_id=worker_id, **kwargs
        )
        tasks.append(task)

    # 執行所有任務
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start_time

    # 處理結果
    successful_results = []
    failed_count = 0

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log_api_error(f"BATCH_LLM", f"任務 {i + 1} 失敗: {str(result)}")
            failed_count += 1
        else:
            successful_results.append(result)

    success_count = len(successful_results)
    log_info(
        f"批量LLM調用完成 | 成功: {success_count} | 失敗: {failed_count} | 總耗時: {duration:.2f}s"
    )

    return successful_results


def get_storyboard_client() -> LLMClient:
    """獲取分鏡生成客戶端"""
    return LLMClient(client_type="storyboard")


def get_prompt_client() -> LLMClient:
    """獲取提示詞生成客戶端"""
    return LLMClient(client_type="prompt")


def get_default_client() -> LLMClient:
    """獲取默認客戶端"""
    return LLMClient(client_type="default")


def test_all_connections() -> Dict[str, bool]:
    """測試所有配置的API連接"""
    log_info("開始測試所有LLM API連接...")
    results = {}

    try:
        storyboard_client = get_storyboard_client()
        results["storyboard"] = storyboard_client.test_connection()
    except Exception as e:
        log_api_error("STORYBOARD_INIT", f"分鏡模型客戶端初始化失敗: {e}")
        results["storyboard"] = False

    try:
        prompt_client = get_prompt_client()
        results["prompt"] = prompt_client.test_connection()
    except Exception as e:
        log_api_error("PROMPT_INIT", f"提示詞模型客戶端初始化失敗: {e}")
        results["prompt"] = False

    success_count = sum(results.values())
    total_count = len(results)
    log_info(f"API連接測試完成 | 成功: {success_count}/{total_count}")

    return results


async def async_test_all_connections() -> Dict[str, bool]:
    """異步測試所有配置的API連接"""
    log_info("開始異步測試所有LLM API連接...")
    results = {}

    tasks = []
    clients = {}

    try:
        storyboard_client = get_storyboard_client()
        clients["storyboard"] = storyboard_client
        tasks.append(("storyboard", storyboard_client.async_test_connection()))
    except Exception as e:
        log_api_error("ASYNC_STORYBOARD_INIT", f"分鏡模型客戶端初始化失敗: {e}")
        results["storyboard"] = False

    try:
        prompt_client = get_prompt_client()
        clients["prompt"] = prompt_client
        tasks.append(("prompt", prompt_client.async_test_connection()))
    except Exception as e:
        log_api_error("ASYNC_PROMPT_INIT", f"提示詞模型客戶端初始化失敗: {e}")
        results["prompt"] = False

    # 執行異步測試
    if tasks:
        test_results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)

        for i, (client_type, _) in enumerate(tasks):
            result = test_results[i]
            if isinstance(result, Exception):
                log_api_error(f"ASYNC_{client_type.upper()}_TEST", str(result))
                results[client_type] = False
            else:
                results[client_type] = result

    success_count = sum(results.values())
    total_count = len(results)
    log_info(f"異步API連接測試完成 | 成功: {success_count}/{total_count}")

    return results
