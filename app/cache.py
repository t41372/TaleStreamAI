# app/cache.py
import hashlib
import json
import pickle
from functools import wraps
from pathlib import Path
from typing import Callable, Any

from .config import settings
from .logger import log_debug

def _generate_cache_key(func: Callable, *args, **kwargs) -> str:
    """根据函数和参数生成一个确定性的哈希键"""
    # 将args和kwargs合并并排序，以确保确定性
    # 使用json.dumps进行序列化，可以处理大部分内置类型
    # sort_keys=True保证了字典键的顺序
    # default=str处理了无法直接序列化为JSON的对象（如Path对象）
    try:
        payload = {
            "args": args,
            "kwargs": kwargs,
        }
        serialized_data = json.dumps(payload, sort_keys=True, default=str).encode('utf-8')
    except TypeError:
        # 对于更复杂或不可序列化为JSON的对象，使用pickle作为后备方案
        # 注意：pickle的输出可能因Python版本而异，但对于一个稳定环境是可靠的
        payload = (args, kwargs)
        serialized_data = pickle.dumps(payload)

    # 使用SHA256生成哈希值
    return hashlib.sha256(serialized_data).hexdigest()

def cache(cache_path: Path, result_type: str = 'text'):
    """
    一个通用的缓存装饰器，可缓存函数结果到文件。
    支持文本和二进制两种模式。

    :param cache_path: 缓存文件的存储目录 (e.g., settings.paths.cache_llm)
    :param result_type: 'text' 或 'binary'
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = _generate_cache_key(func, *args, **kwargs)
            cache_file = cache_path / f"{func.__name__}_{cache_key}"

            # 检查缓存是否存在
            if cache_file.exists():
                log_debug(f"✅ 缓存命中: {func.__name__} (key: {cache_key[:8]}...), 从 {cache_file} 读取")
                if result_type == 'binary':
                    return cache_file.read_bytes()
                else:
                    return cache_file.read_text(encoding='utf-8')

            # 执行函数并获取结果
            log_debug(f"❌ 缓存未命中: {func.__name__} (key: {cache_key[:8]}...), 执行函数")
            result = func(*args, **kwargs)

            # 保存结果到缓存
            if result is not None:
                cache_path.mkdir(parents=True, exist_ok=True)
                if result_type == 'binary':
                    cache_file.write_bytes(result)
                else:
                    cache_file.write_text(str(result), encoding='utf-8')
                log_debug(f"📝 结果已缓存至: {cache_file}")

            return result
        return wrapper
    return decorator

# 预先定义好的缓存装饰器实例
llm_cache = cache(settings.paths.cache_llm, 'text')
image_cache = cache(settings.paths.cache_image, 'binary')
audio_cache = cache(settings.paths.cache_audio, 'binary') 