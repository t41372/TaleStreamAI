"""
統一的大模型客戶端管理模塊
支持OpenAI兼容的API接口
"""

import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any

load_dotenv(override=True)


class LLMClient:
    """統一的大模型客戶端類"""
    
    def __init__(self, 
                 api_key: Optional[str] = None, 
                 base_url: Optional[str] = None, 
                 model: Optional[str] = None,
                 client_type: str = "default"):
        """
        初始化LLM客戶端
        
        Args:
            api_key: API密鑰
            base_url: API基礎URL
            model: 模型名稱
            client_type: 客戶端類型，用於從環境變量獲取配置
        """
        self.client_type = client_type
        self.api_key = api_key or self._get_env_key()
        self.base_url = base_url or self._get_env_url()
        self.model = model or self._get_env_model()
        
        if not self.api_key:
            raise ValueError(f"API Key not found for client type: {client_type}")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=120.0  # 設置2分鐘超時
        )
    
    def _get_env_key(self) -> Optional[str]:
        """從環境變量獲取API密鑰"""
        if self.client_type == "storyboard":
            return (os.getenv("STORYBOARD_API_KEY") or 
                   os.getenv("GEMINI_API_KEY") or 
                   os.getenv("AL_API_KEY"))
        elif self.client_type == "prompt":
            return (os.getenv("PROMPT_API_KEY") or 
                   os.getenv("AL_API_KEY") or 
                   os.getenv("GEMINI_API_KEY"))
        else:
            return (os.getenv("AL_API_KEY") or 
                   os.getenv("GEMINI_API_KEY") or
                   os.getenv("STORYBOARD_API_KEY"))
    
    def _get_env_url(self) -> Optional[str]:
        """從環境變量獲取API URL"""
        if self.client_type == "storyboard":
            return (os.getenv("STORYBOARD_API_URL") or 
                   os.getenv("GEMINI_API_URL") or
                   os.getenv("AL_API_URL"))
        elif self.client_type == "prompt":
            return (os.getenv("PROMPT_API_URL") or 
                   os.getenv("AL_API_URL") or
                   os.getenv("GEMINI_API_URL"))
        else:
            return (os.getenv("AL_API_URL") or 
                   os.getenv("GEMINI_API_URL") or
                   os.getenv("STORYBOARD_API_URL"))
    
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
    
    def chat_completion(self, 
                       messages: list, 
                       model: Optional[str] = None,
                       stream: bool = False,
                       **kwargs) -> Any:
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
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            **kwargs
        )
    
    def chat_completion_stream(self, 
                              messages: list, 
                              model: Optional[str] = None,
                              **kwargs) -> Any:
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
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
    
    def test_connection(self) -> bool:
        """測試API連接"""
        try:
            response = self.chat_completion(
                messages=[
                    {"role": "user", "content": "測試連接，請回復：{\"test\": \"success\"}"}
                ]
            )
            content = response.choices[0].message.content
            return "test" in content.lower() and "success" in content.lower()
        except Exception as e:
            print(f"API連接測試失敗 ({self.client_type}): {str(e)}")
            return False


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
    results = {}
    
    try:
        storyboard_client = get_storyboard_client()
        results["storyboard"] = storyboard_client.test_connection()
    except Exception as e:
        print(f"分鏡模型客戶端初始化失敗: {e}")
        results["storyboard"] = False
    
    try:
        prompt_client = get_prompt_client()
        results["prompt"] = prompt_client.test_connection()
    except Exception as e:
        print(f"提示詞模型客戶端初始化失敗: {e}")
        results["prompt"] = False
    
    return results
