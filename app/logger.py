"""
統一的日誌記錄模塊
提供詳細的進度追蹤和狀態記錄
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv()


class TaleStreamLogger:
    """TaleStream專用日誌記錄器"""
    
    def __init__(self, name: str = "TaleStreamAI"):
        self.name = name
        self.verbose = os.getenv("VERBOSE_LOGGING", "true").lower() == "true"
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """設置日誌記錄器"""
        logger = logging.getLogger(self.name)
        
        # 避免重複添加處理器
        if logger.handlers:
            return logger
            
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # 創建控制台處理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # 創建格式化器
        if self.verbose:
            formatter = logging.Formatter(
                '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
                datefmt='%H:%M:%S'
            )
        else:
            formatter = logging.Formatter('%(levelname)s | %(message)s')
        
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        return logger
    
    def info(self, message: str, **kwargs):
        """記錄信息日誌"""
        self.logger.info(message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """記錄調試日誌"""
        if self.verbose:
            self.logger.debug(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """記錄警告日誌"""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """記錄錯誤日誌"""
        self.logger.error(message, **kwargs)
    
    def progress(self, step: str, current: int, total: int, description: str = ""):
        """記錄進度信息"""
        percentage = (current / total) * 100 if total > 0 else 0
        progress_bar = "█" * int(percentage // 5) + "░" * (20 - int(percentage // 5))
        
        if description:
            message = f"📊 {step} | [{progress_bar}] {current}/{total} ({percentage:.1f}%) | {description}"
        else:
            message = f"📊 {step} | [{progress_bar}] {current}/{total} ({percentage:.1f}%)"
        
        self.info(message)
    
    def api_call_start(self, api_name: str, endpoint: str = "", model: str = ""):
        """記錄API調用開始"""
        if model and endpoint:
            self.info(f"🔄 開始調用 {api_name} API | 模型: {model} | 端點: {endpoint}")
        elif model:
            self.info(f"🔄 開始調用 {api_name} API | 模型: {model}")
        else:
            self.info(f"🔄 開始調用 {api_name} API")
    
    def api_call_success(self, api_name: str, duration: float = 0, details: str = ""):
        """記錄API調用成功"""
        if duration > 0:
            if details:
                self.info(f"✅ {api_name} API 調用成功 | 耗時: {duration:.2f}s | {details}")
            else:
                self.info(f"✅ {api_name} API 調用成功 | 耗時: {duration:.2f}s")
        else:
            if details:
                self.info(f"✅ {api_name} API 調用成功 | {details}")
            else:
                self.info(f"✅ {api_name} API 調用成功")
    
    def api_call_error(self, api_name: str, error: str, retry_count: int = 0):
        """記錄API調用失敗"""
        if retry_count > 0:
            self.error(f"❌ {api_name} API 調用失敗 | 重試次數: {retry_count} | 錯誤: {error}")
        else:
            self.error(f"❌ {api_name} API 調用失敗 | 錯誤: {error}")
    
    def step_start(self, step_name: str, description: str = ""):
        """記錄步驟開始"""
        if description:
            self.info(f"🚀 開始執行: {step_name} | {description}")
        else:
            self.info(f"🚀 開始執行: {step_name}")
    
    def step_complete(self, step_name: str, duration: float = 0, details: str = ""):
        """記錄步驟完成"""
        if duration > 0:
            if details:
                self.info(f"✅ 完成: {step_name} | 耗時: {duration:.2f}s | {details}")
            else:
                self.info(f"✅ 完成: {step_name} | 耗時: {duration:.2f}s")
        else:
            if details:
                self.info(f"✅ 完成: {step_name} | {details}")
            else:
                self.info(f"✅ 完成: {step_name}")
    
    def file_operation(self, operation: str, file_path: str, success: bool = True):
        """記錄文件操作"""
        file_name = Path(file_path).name
        if success:
            self.info(f"📁 {operation}: {file_name}")
        else:
            self.error(f"📁 {operation}失敗: {file_name}")
    
    def concurrent_operation(self, operation: str, current: int, total: int, 
                           worker_id: Optional[str] = None):
        """記錄並發操作進度"""
        if worker_id:
            self.debug(f"⚡ 併發 {operation} | 工作者: {worker_id} | 進度: {current}/{total}")
        else:
            self.info(f"⚡ 併發 {operation} | 進度: {current}/{total}")
    
    def resource_usage(self, operation: str, **metrics):
        """記錄資源使用情況"""
        metric_strs = [f"{k}={v}" for k, v in metrics.items()]
        self.debug(f"📈 {operation} 資源使用 | {' | '.join(metric_strs)}")


# 全局日誌記錄器實例
logger = TaleStreamLogger()

# 便捷函數
def log_info(message: str, **kwargs):
    """記錄信息"""
    logger.info(message, **kwargs)

def log_debug(message: str, **kwargs):
    """記錄調試信息"""
    logger.debug(message, **kwargs)

def log_warning(message: str, **kwargs):
    """記錄警告"""
    logger.warning(message, **kwargs)

def log_error(message: str, **kwargs):
    """記錄錯誤"""
    logger.error(message, **kwargs)

def log_progress(step: str, current: int, total: int, description: str = ""):
    """記錄進度"""
    logger.progress(step, current, total, description)

def log_api_start(api_name: str, endpoint: str = "", model: str = ""):
    """記錄API調用開始"""
    logger.api_call_start(api_name, endpoint, model)

def log_api_success(api_name: str, duration: float = 0, details: str = ""):
    """記錄API調用成功"""
    logger.api_call_success(api_name, duration, details)

def log_api_error(api_name: str, error: str, retry_count: int = 0):
    """記錄API調用失敗"""
    logger.api_call_error(api_name, error, retry_count)

def log_step_start(step_name: str, description: str = ""):
    """記錄步驟開始"""
    logger.step_start(step_name, description)

def log_step_complete(step_name: str, duration: float = 0, details: str = ""):
    """記錄步驟完成"""
    logger.step_complete(step_name, duration, details)

def log_file_operation(operation: str, file_path: str, success: bool = True):
    """記錄文件操作"""
    logger.file_operation(operation, file_path, success)

def log_concurrent(operation: str, current: int, total: int, worker_id: Optional[str] = None):
    """記錄並發操作"""
    logger.concurrent_operation(operation, current, total, worker_id)